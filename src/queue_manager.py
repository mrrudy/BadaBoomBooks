"""
Queue management for parallel audiobook processing.

Uses Huey task queue with SQLite backend for persistence and parallelization.
"""

import os
import uuid
import json
import sqlite3
import logging as log
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Callable
from dataclasses import asdict

from huey import SqliteHuey

from .models import BookMetadata, ProcessingArgs, ProcessingResult
from .config import root_path


def _get_database_path() -> Path:
    """
    Get the database path, respecting environment variable override for tests.

    Returns:
        Path: Database file path (production or test)
    """
    env_db_path = os.environ.get('BADABOOMBOOKS_DB_PATH')
    if env_db_path:
        return Path(env_db_path)
    return root_path / 'badaboombooksqueue.db'


# Initialize Huey with SQLite backend
# Use environment variable for test isolation
db_path = _get_database_path()
huey = SqliteHuey(
    name='badaboombooks',
    filename=str(db_path),
    immediate=False,  # Use actual workers (not immediate mode)
    results=True,
    store_none=True,
    utc=False
)


class QueueManager:
    """Manages job and task queue for audiobook processing."""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize queue manager with database connection."""
        self.db_path = db_path or _get_database_path()
        self.connection = None
        self._initialize_database()

    def _initialize_database(self):
        """Create database tables if they don't exist."""
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row

        # Enable read_uncommitted to avoid WAL isolation issues across processes
        # This allows workers in different processes to see each other's updates immediately
        cursor = self.connection.cursor()
        cursor.execute('PRAGMA read_uncommitted = 1')
        cursor.execute('PRAGMA wal_checkpoint(PASSIVE)')  # Ensure WAL is checkpointed

        # Jobs table: One per processing request (CLI run or web job)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                status TEXT NOT NULL,
                total_tasks INTEGER DEFAULT 0,
                completed_tasks INTEGER DEFAULT 0,
                failed_tasks INTEGER DEFAULT 0,
                skipped_tasks INTEGER DEFAULT 0,
                user_id TEXT,
                args_json TEXT NOT NULL,
                error TEXT,
                CONSTRAINT valid_status CHECK (status IN ('pending', 'planning', 'processing', 'completed', 'failed', 'cancelled'))
            )
        ''')

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON jobs(user_id)')

        # Tasks table: One per audiobook
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                folder_path TEXT NOT NULL,
                url TEXT,
                status TEXT NOT NULL,
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 2,
                error TEXT,
                result_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                worker_id TEXT,
                FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
                CONSTRAINT valid_task_status CHECK (status IN ('pending', 'running', 'completed', 'failed', 'skipped'))
            )
        ''')

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_job_id ON tasks(job_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)')

        # Schema migration: Add enqueued_at column if it doesn't exist
        cursor.execute("PRAGMA table_info(tasks)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'enqueued_at' not in columns:
            log.info("Adding enqueued_at column to tasks table")
            cursor.execute('ALTER TABLE tasks ADD COLUMN enqueued_at TIMESTAMP')
            self.connection.commit()

        # File locks table: Tracks directory creation locks
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS file_locks (
                lock_path TEXT PRIMARY KEY,
                locked_by_task TEXT NOT NULL,
                acquired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (locked_by_task) REFERENCES tasks(id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_file_locks_task ON file_locks(locked_by_task)')

        # Schema versioning
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Insert initial version if table is empty
        cursor.execute('SELECT COUNT(*) FROM schema_version')
        if cursor.fetchone()[0] == 0:
            cursor.execute('INSERT INTO schema_version (version) VALUES (1)')

        self.connection.commit()
        log.debug(f"Database initialized at {self.db_path}")

    def refresh_connection(self):
        """
        Refresh the connection's view of the database.

        In WAL mode, even with read_uncommitted, explicit checkpointing
        ensures the latest writes from other processes are visible.
        """
        cursor = self.connection.cursor()
        cursor.execute('PRAGMA wal_checkpoint(PASSIVE)')
        # Force a simple read to refresh the connection's snapshot
        cursor.execute('SELECT 1')
        cursor.fetchone()

    def create_job(self, args: ProcessingArgs, user_id: Optional[str] = None) -> str:
        """
        Create a new processing job.

        Args:
            args: ProcessingArgs with configuration
            user_id: Optional user identifier for web interface

        Returns:
            job_id: UUID of created job
        """
        job_id = str(uuid.uuid4())
        args_json = json.dumps(asdict(args), default=str)

        cursor = self.connection.cursor()
        cursor.execute("""
            INSERT INTO jobs (id, status, user_id, args_json)
            VALUES (?, 'pending', ?, ?)
        """, (job_id, user_id, args_json))
        self.connection.commit()

        log.info(f"Created job {job_id}")
        return job_id

    def create_task(self, job_id: str, folder_path: Path, url: str) -> str:
        """
        Create a task for a single audiobook.

        Args:
            job_id: Parent job ID
            folder_path: Source folder path
            url: Source URL or 'OPF' marker

        Returns:
            task_id: UUID of created task
        """
        task_id = str(uuid.uuid4())

        cursor = self.connection.cursor()
        cursor.execute("""
            INSERT INTO tasks (id, job_id, folder_path, url, status)
            VALUES (?, ?, ?, ?, 'pending')
        """, (task_id, job_id, str(folder_path.resolve()), url))
        self.connection.commit()

        log.debug(f"Created task {task_id} for {folder_path.name}")
        return task_id

    def get_job(self, job_id: str) -> Optional[Dict]:
        """Retrieve job by ID."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_task(self, task_id: str) -> Optional[Dict]:
        """Retrieve task by ID."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def update_job_status(self, job_id: str, status: str, **kwargs):
        """Update job status and optional fields."""
        set_clauses = ["status = ?"]
        values = [status]

        for key, value in kwargs.items():
            set_clauses.append(f"{key} = ?")
            values.append(value)

        values.append(job_id)

        cursor = self.connection.cursor()
        cursor.execute(f"""
            UPDATE jobs SET {', '.join(set_clauses)} WHERE id = ?
        """, values)
        self.connection.commit()

    def delete_job(self, job_id: str):
        """
        Delete a job and all its associated tasks.

        Args:
            job_id: Job ID to delete
        """
        cursor = self.connection.cursor()

        # Delete tasks first (due to foreign key)
        cursor.execute("DELETE FROM tasks WHERE job_id = ?", (job_id,))
        tasks_deleted = cursor.rowcount

        # Delete job
        cursor.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

        self.connection.commit()
        log.info(f"Deleted job {job_id[:8]} and {tasks_deleted} associated task(s)")

    def update_task_status(self, task_id: str, status: str, **kwargs):
        """Update task status and optional fields."""
        set_clauses = ["status = ?"]
        values = [status]

        for key, value in kwargs.items():
            set_clauses.append(f"{key} = ?")
            values.append(value)

        values.append(task_id)

        cursor = self.connection.cursor()
        cursor.execute(f"""
            UPDATE tasks SET {', '.join(set_clauses)} WHERE id = ?
        """, values)
        self.connection.commit()

    def get_job_progress(self, job_id: str) -> Dict:
        """Get progress statistics for a job."""
        # Refresh connection to see latest updates from other processes
        self.refresh_connection()

        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COALESCE(SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END), 0) as completed,
                COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0) as failed,
                COALESCE(SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END), 0) as skipped,
                COALESCE(SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END), 0) as running,
                COALESCE(SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END), 0) as pending
            FROM tasks WHERE job_id = ?
        """, (job_id,))

        row = cursor.fetchone()
        if row:
            result = dict(row)
            # Ensure all values are integers, not None
            for key in result:
                if result[key] is None:
                    result[key] = 0
            return result
        return {'total': 0, 'completed': 0, 'failed': 0, 'skipped': 0, 'running': 0, 'pending': 0}

    def get_incomplete_jobs(self) -> List[Dict]:
        """
        Find jobs that were interrupted or have unfinished tasks (for resume logic).

        Returns jobs that either:
        1. Have status != 'completed' (interrupted mid-run)
        2. Have status = 'completed' but still have pending tasks (race condition during shutdown)
        """
        # Refresh connection to see latest updates from other processes
        self.refresh_connection()

        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT DISTINCT jobs.* FROM jobs
            WHERE jobs.status IN ('pending', 'planning', 'processing')
               OR EXISTS (
                   SELECT 1 FROM tasks
                   WHERE tasks.job_id = jobs.id
                     AND tasks.status IN ('pending', 'running')
               )
            ORDER BY jobs.created_at DESC
        """)
        return [dict(row) for row in cursor.fetchall()]

    def get_pending_tasks(self, job_id: str, only_not_enqueued: bool = False) -> List[Dict]:
        """
        Get all pending tasks for a job.

        Args:
            job_id: Job ID to get tasks for
            only_not_enqueued: If True, only return tasks that haven't been enqueued yet

        Returns:
            List of task dictionaries
        """
        # Refresh connection to see latest updates from other processes
        self.refresh_connection()

        cursor = self.connection.cursor()

        if only_not_enqueued:
            # Only get tasks that haven't been enqueued to Huey yet
            cursor.execute("""
                SELECT * FROM tasks
                WHERE job_id = ? AND status = 'pending' AND enqueued_at IS NULL
                ORDER BY created_at
            """, (job_id,))
        else:
            # Get all pending tasks
            cursor.execute("""
                SELECT * FROM tasks
                WHERE job_id = ? AND status = 'pending'
                ORDER BY created_at
            """, (job_id,))

        return [dict(row) for row in cursor.fetchall()]

    def enqueue_all_tasks(self, job_id: str, progress_callback: Optional[Callable] = None):
        """
        Enqueue all pending tasks for a job to Huey.

        Only enqueues tasks that haven't been enqueued before (enqueued_at IS NULL).
        This prevents duplicate tasks in Huey's queue.

        Args:
            job_id: Job ID to enqueue tasks for
            progress_callback: Optional callback for progress updates
        """
        # Only get tasks that haven't been enqueued yet
        tasks = self.get_pending_tasks(job_id, only_not_enqueued=True)

        if not tasks:
            log.debug(f"No new tasks to enqueue for job {job_id[:8]}")
            return

        log.info(f"Enqueueing {len(tasks)} new pending tasks for job {job_id[:8]}...")

        enqueued_count = 0
        cursor = self.connection.cursor()

        for task in tasks:
            task_id = task['id']
            folder_path = task['folder_path']
            url = task['url']

            try:
                # Enqueue to Huey
                result = process_audiobook_task.schedule(
                    args=(task_id, job_id, folder_path, url),
                    delay=0
                )

                # Mark as enqueued to prevent duplicates
                cursor.execute("""
                    UPDATE tasks SET enqueued_at = ? WHERE id = ?
                """, (datetime.now().isoformat(), task_id))
                self.connection.commit()

                log.debug(f"Enqueued task {task_id[:8]}... ({Path(folder_path).name}) to Huey, result: {result}")
                enqueued_count += 1

            except Exception as e:
                log.error(f"Failed to enqueue task {task_id[:8]}: {e}", exc_info=True)

            if progress_callback:
                progress_callback(job_id, len(tasks))

        log.info(f"Successfully enqueued {enqueued_count}/{len(tasks)} new tasks")

    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()


@huey.task(retries=2, retry_delay=60)
def process_audiobook_task(task_id: str, job_id: str, folder_path: str, url: str):
    """
    Huey task: Process a single audiobook through complete pipeline.

    This runs in a worker process/thread. Each worker processes one book
    independently, with file locks protecting shared directory creation.

    Args:
        task_id: Task UUID
        job_id: Parent job UUID
        folder_path: Source folder absolute path
        url: Source URL or 'OPF' marker
    """
    import threading
    import os
    from .models import BookMetadata, ProcessingArgs
    from .processors.file_operations import FileProcessor
    from .processors.metadata_operations import MetadataProcessor
    from .processors.audio_operations import AudioProcessor
    from .utils.file_locks import FileLockManager
    from .utils.helpers import find_metadata_opf
    from .scrapers import AudibleScraper, GoodreadsScraper, LubimyczytacScraper
    from .utils.helpers import detect_url_site
    from .scrapers.base import preprocess_audible_url, http_request_audible_api, http_request_generic

    queue_manager = QueueManager()

    # Create unique worker ID using PID and thread name
    # This ensures workers from different processes don't collide
    process_id = os.getpid()
    thread_name = threading.current_thread().name
    worker_id = f"pid{process_id}-{thread_name}"

    try:
        # Update task status
        queue_manager.update_task_status(
            task_id,
            'running',
            started_at=datetime.now().isoformat(),
            worker_id=worker_id
        )

        log.info(f"[Worker {worker_id}] Starting task {task_id}: {Path(folder_path).name}")

        # Retrieve job args
        job = queue_manager.get_job(job_id)
        args_dict = json.loads(job['args_json'])
        args = ProcessingArgs(**args_dict)

        # Create metadata object
        metadata = BookMetadata.create_empty(folder_path, url)
        metadata.task_id = task_id  # Add task_id to metadata for lock tracking

        # Initialize processors with lock manager
        lock_manager = FileLockManager(queue_manager.connection)
        file_processor = FileProcessor(args)
        file_processor.lock_manager = lock_manager  # Inject lock manager

        metadata_processor = MetadataProcessor(args.dry_run, use_llm=args.llm_select)
        audio_processor = AudioProcessor(args.dry_run)

        # Execute processing pipeline
        success = _execute_processing_pipeline(
            metadata, Path(folder_path), url, args,
            file_processor, metadata_processor, audio_processor, log
        )

        if success and not metadata.failed and not metadata.skip:
            # Success
            result_json = json.dumps(metadata.to_dict(), default=str)
            queue_manager.update_task_status(
                task_id,
                'completed',
                completed_at=datetime.now().isoformat(),
                result_json=result_json
            )
            log.info(f"[Worker {worker_id}] Completed task {task_id}")
        elif metadata.skip:
            # Skipped
            queue_manager.update_task_status(
                task_id,
                'skipped',
                completed_at=datetime.now().isoformat(),
                error="Skipped by user"
            )
        else:
            # Failed
            queue_manager.update_task_status(
                task_id,
                'failed',
                completed_at=datetime.now().isoformat(),
                error=metadata.failed_exception or "Unknown error"
            )
            log.error(f"[Worker {worker_id}] Failed task {task_id}: {metadata.failed_exception}")

    except Exception as e:
        # Task exception
        log.error(f"[Worker {worker_id}] Exception in task {task_id}: {e}", exc_info=True)
        queue_manager.update_task_status(
            task_id,
            'failed',
            completed_at=datetime.now().isoformat(),
            error=str(e)
        )
    finally:
        queue_manager.close()


def _discover_url_for_folder(folder_path: Path, args: ProcessingArgs,
                            metadata_processor, log) -> Optional[str]:
    """
    Discover URL for a folder using auto-search or manual search.

    This function is called by workers when processing tasks with url=None.
    It performs the same logic as BadaBoomBooksApp._get_url_for_folder().

    Args:
        folder_path: Path to the audiobook folder
        args: ProcessingArgs with search configuration
        metadata_processor: MetadataProcessor for reading OPF files
        log: Logger instance

    Returns:
        URL string, 'OPF' marker, or None if skipped/failed
    """
    from .config import SCRAPER_REGISTRY
    from .utils.helpers import find_metadata_opf, generate_search_term
    from .search import AutoSearchEngine, ManualSearchHandler

    try:
        # Check for existing OPF file if requested (but not if force refresh)
        if args.from_opf and not args.force_refresh:
            opf_file = find_metadata_opf(folder_path)
            if opf_file:
                log.info(f"Using existing OPF for {folder_path.name}")
                return 'OPF'

        # If force_refresh is set, treat OPF as search source
        if args.force_refresh:
            opf_file = find_metadata_opf(folder_path)
            if opf_file:
                # Read OPF to get title/author/source for searching
                temp_metadata = metadata_processor.read_opf_metadata(opf_file)

                if temp_metadata.url:
                    # Use source URL from OPF for re-scraping
                    log.info(f"Force refreshing from source URL: {temp_metadata.url}")
                    return temp_metadata.url
                else:
                    # No source URL - fall through to normal search
                    log.warning(f"No source URL in OPF for {folder_path.name}, performing search")

        # Use auto-search or manual search
        if args.auto_search:
            # Extract book info for context (simplified version - no book_root support in workers)
            book_info = _extract_book_info_for_discovery(folder_path, metadata_processor, log)

            # Generate search term
            if book_info.get('title') and book_info.get('author'):
                search_term = f"{book_info['title']} by {book_info['author']}"
            elif book_info.get('title'):
                search_term = book_info['title']
            elif book_info.get('author'):
                search_term = f"{folder_path.name} by {book_info['author']}"
            else:
                search_term = generate_search_term(folder_path)

            # Determine sites to search
            if args.site == 'all':
                site_keys = list(SCRAPER_REGISTRY.keys())
            else:
                site_keys = [args.site]

            # Perform search
            auto_search = AutoSearchEngine(
                debug_enabled=args.debug,
                enable_ai_selection=args.llm_select,
                yolo=args.yolo
            )
            site_key, url, html = auto_search.search_and_select_with_context(
                search_term, site_keys, book_info, args.search_limit, args.download_limit, args.search_delay
            )

            if site_key and url:
                log.info(f"Auto-search found {SCRAPER_REGISTRY[site_key]['domain']}: {url}")
                return url
            else:
                log.info(f"Auto-search failed for {folder_path.name}, skipping")
                return None

        else:
            # Manual search
            book_info = _extract_book_info_for_discovery(folder_path, metadata_processor, log)
            manual_search = ManualSearchHandler()
            site_key, url = manual_search.handle_manual_search_with_context(folder_path, book_info, args.site)

            if site_key and url:
                return url
            else:
                return None

    except Exception as e:
        log.error(f"Error discovering URL for {folder_path.name}: {e}", exc_info=True)
        return None


def _extract_book_info_for_discovery(folder_path: Path, metadata_processor, log) -> dict:
    """
    Extract book information for URL discovery context.

    Simplified version without book_root support (used in workers).

    Args:
        folder_path: Path to audiobook folder
        metadata_processor: MetadataProcessor for reading OPF
        log: Logger instance

    Returns:
        Dictionary with book info (folder_name, title, author, source)
    """
    from .utils.helpers import find_metadata_opf
    from xml.etree import ElementTree as ET

    book_info = {
        'folder_name': folder_path.name,
        'source': 'folder name'
    }

    try:
        # Try to read existing OPF file first
        opf_file = find_metadata_opf(folder_path)
        if opf_file:
            try:
                tree = ET.parse(opf_file)
                root = tree.getroot()
                ns = {'dc': 'http://purl.org/dc/elements/1.1/'}

                title_elem = root.find('.//dc:title', ns)
                if title_elem is not None and title_elem.text:
                    book_info['title'] = title_elem.text

                author_elem = root.find('.//dc:creator', ns)
                if author_elem is not None and author_elem.text:
                    book_info['author'] = author_elem.text

                book_info['source'] = 'existing OPF file'
            except Exception as e:
                log.debug(f"Error reading OPF for {folder_path.name}: {e}")

        # Try ID3 tags if no author found yet
        if 'author' not in book_info:
            try:
                from .utils.helpers import get_first_audio_file
                import mutagen

                audio_file = get_first_audio_file(folder_path)
                if audio_file:
                    audio = mutagen.File(audio_file, easy=True)
                    if audio:
                        if 'title' in audio and audio['title']:
                            book_info['title'] = audio['title'][0]
                        if 'artist' in audio and audio['artist']:
                            book_info['author'] = audio['artist'][0]
                        book_info['source'] = 'ID3 tags'
            except Exception as e:
                log.debug(f"Error reading ID3 tags for {folder_path.name}: {e}")

        # Try parent directory for author if still not found
        if 'author' not in book_info:
            try:
                parent_dir = folder_path.parent
                if parent_dir and parent_dir.name:
                    book_info['author'] = parent_dir.name
                    log.debug(f"Extracted author '{parent_dir.name}' from parent directory for {folder_path.name}")
            except Exception as e:
                log.debug(f"Error extracting author from parent directory for {folder_path.name}: {e}")

    except Exception as e:
        log.debug(f"Error extracting book info from {folder_path}: {e}")

    return book_info


def _execute_processing_pipeline(metadata: BookMetadata, folder_path: Path, url_or_marker: Optional[str],
                                 args: ProcessingArgs, file_processor, metadata_processor,
                                 audio_processor, log):
    """
    Execute the complete processing pipeline for one book.

    This is extracted from BadaBoomBooksApp._process_single_book() to be
    callable from Huey tasks.

    Returns:
        bool: True if processing succeeded, False otherwise
    """
    from .utils.helpers import find_metadata_opf, detect_url_site
    from .scrapers.base import preprocess_audible_url, http_request_audible_api, http_request_generic
    from .scrapers import AudibleScraper, GoodreadsScraper, LubimyczytacScraper

    metadata.input_folder = str(folder_path)

    try:
        # Step 0: URL Discovery (if URL is None)
        if url_or_marker is None:
            log.info(f"Discovering URL for {folder_path.name}...")
            url_or_marker = _discover_url_for_folder(folder_path, args, metadata_processor, log)

            if url_or_marker is None:
                metadata.mark_as_failed("URL discovery failed or skipped by user")
                return False

            log.info(f"Discovered URL: {url_or_marker}")

        # Step 1: Scrape metadata
        if url_or_marker == "OPF":
            opf_file = find_metadata_opf(folder_path)
            if not opf_file:
                metadata.mark_as_failed("No metadata.opf found")
                return False
            metadata = metadata_processor.read_opf_metadata(opf_file)
            metadata.task_id = metadata.task_id  # Preserve task_id
        else:
            metadata.url = url_or_marker
            site_key = detect_url_site(metadata.url)
            if not site_key:
                metadata.mark_as_failed(f"Unsupported URL: {metadata.url}")
                return False

            # Preprocess URL if needed
            if site_key == 'audible':
                preprocess_audible_url(metadata)

            # Make HTTP request
            if site_key == 'audible':
                metadata, response = http_request_audible_api(metadata, log)
            else:
                metadata, response = http_request_generic(metadata, log)

            if metadata.failed:
                return False

            # Scrape metadata
            if site_key == 'audible':
                scraper = AudibleScraper()
            elif site_key == 'goodreads':
                scraper = GoodreadsScraper()
            elif site_key == 'lubimyczytac':
                scraper = LubimyczytacScraper()
            else:
                metadata.mark_as_failed(f"Unknown site: {site_key}")
                return False

            metadata = scraper.scrape_metadata(metadata, response, log)

        if metadata.failed or metadata.skip:
            return False

        # Step 2: Organize files (with locks)
        if args.copy or args.move:
            if not file_processor.process_folder_organization(metadata):
                return False
        else:
            metadata.final_output = folder_path

        # Step 3: Process files
        if args.flatten:
            if not file_processor.flatten_folder(metadata):
                return False

        if args.rename:
            if not file_processor.rename_audio_tracks(metadata):
                return False

        # Step 4: Generate metadata files
        if args.opf:
            from .config import opf_template
            if not metadata_processor.create_opf_file(metadata, opf_template):
                return False

        if args.infotxt:
            if not metadata_processor.create_info_file(metadata):
                return False

        if args.cover:
            metadata_processor.download_cover_image(metadata)

        # Step 5: Update audio tags
        if args.id3_tag:
            if not audio_processor.update_id3_tags(metadata):
                return False

        return True

    except Exception as e:
        log.error(f"Error processing {metadata.input_folder}: {e}", exc_info=True)
        metadata.mark_as_failed(str(e))
        return False
