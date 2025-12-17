"""
Queue management for parallel audiobook processing.

Uses Huey task queue with SQLite backend for persistence and parallelization.
"""

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


# Initialize Huey with SQLite backend
db_path = root_path / 'badaboombooksqueue.db'
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
        self.db_path = db_path or (root_path / 'badaboombooksqueue.db')
        self.connection = None
        self._initialize_database()

    def _initialize_database(self):
        """Create database tables if they don't exist."""
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row

        cursor = self.connection.cursor()

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
        """Find jobs that were interrupted (for resume logic)."""
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT * FROM jobs
            WHERE status IN ('pending', 'planning', 'processing')
            ORDER BY created_at DESC
        """)
        return [dict(row) for row in cursor.fetchall()]

    def get_pending_tasks(self, job_id: str) -> List[Dict]:
        """Get all pending tasks for a job."""
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT * FROM tasks
            WHERE job_id = ? AND status = 'pending'
            ORDER BY created_at
        """, (job_id,))
        return [dict(row) for row in cursor.fetchall()]

    def enqueue_all_tasks(self, job_id: str, progress_callback: Optional[Callable] = None):
        """
        Enqueue all pending tasks for a job to Huey.

        Args:
            job_id: Job ID to enqueue tasks for
            progress_callback: Optional callback for progress updates
        """
        tasks = self.get_pending_tasks(job_id)

        log.info(f"Enqueueing {len(tasks)} tasks for job {job_id}")

        for task in tasks:
            task_id = task['id']
            folder_path = task['folder_path']
            url = task['url']

            # Enqueue to Huey
            process_audiobook_task.schedule(
                args=(task_id, job_id, folder_path, url),
                delay=0
            )

            log.debug(f"Enqueued task {task_id} to Huey")

            if progress_callback:
                progress_callback(job_id, len(tasks))

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
    worker_id = f"{threading.current_thread().name}"

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


def _execute_processing_pipeline(metadata: BookMetadata, folder_path: Path, url_or_marker: str,
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
