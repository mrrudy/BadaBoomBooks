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
                CONSTRAINT valid_task_status CHECK (status IN ('pending', 'running', 'completed', 'failed', 'skipped', 'waiting_for_user'))
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

        # Schema migration: Add user input tracking columns if they don't exist
        cursor.execute("PRAGMA table_info(tasks)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'user_input_type' not in columns:
            log.info("Adding user_input_type column to tasks table")
            cursor.execute('ALTER TABLE tasks ADD COLUMN user_input_type TEXT')
            self.connection.commit()

        if 'user_input_prompt' not in columns:
            log.info("Adding user_input_prompt column to tasks table")
            cursor.execute('ALTER TABLE tasks ADD COLUMN user_input_prompt TEXT')
            self.connection.commit()

        if 'user_input_options' not in columns:
            log.info("Adding user_input_options column to tasks table")
            cursor.execute('ALTER TABLE tasks ADD COLUMN user_input_options TEXT')
            self.connection.commit()

        if 'user_input_context' not in columns:
            log.info("Adding user_input_context column to tasks table")
            cursor.execute('ALTER TABLE tasks ADD COLUMN user_input_context TEXT')
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

    def flush_huey_queue(self):
        """
        Flush all pending tasks from Huey's task queue.

        This is used when resuming a job to ensure stale tasks from previous
        runs don't interfere with the new execution mode (e.g., switching from
        daemon mode to interactive mode).

        WARNING: This affects ALL jobs, not just the current one. Use carefully.
        """
        try:
            # Huey stores tasks in its SqliteStorage
            # flush_queue() removes all pending tasks from the queue table
            huey.storage.flush_queue()
            log.info(f"Flushed Huey task queue successfully")
            return True
        except Exception as e:
            log.error(f"Failed to flush Huey queue: {e}", exc_info=True)
            return False

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
        """, (task_id, job_id, str(folder_path), url))
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
                COALESCE(SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END), 0) as pending,
                COALESCE(SUM(CASE WHEN status = 'waiting_for_user' THEN 1 ELSE 0 END), 0) as waiting_for_user
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
        return {'total': 0, 'completed': 0, 'failed': 0, 'skipped': 0, 'running': 0, 'pending': 0, 'waiting_for_user': 0}

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

    def get_pending_tasks(self, job_id: str, only_not_enqueued: bool = False,
                         interactive: bool = False) -> List[Dict]:
        """
        Get all pending tasks for a job.

        Args:
            job_id: Job ID to get tasks for
            only_not_enqueued: If True, only return tasks that haven't been enqueued yet
            interactive: If True, include 'waiting_for_user' tasks. If False (daemon mode),
                        only return 'pending' tasks (excludes user input tasks)

        Returns:
            List of task dictionaries
        """
        # Refresh connection to see latest updates from other processes
        self.refresh_connection()

        cursor = self.connection.cursor()

        # Build status filter based on interactive mode
        if interactive:
            # Interactive: include both 'pending' and 'waiting_for_user'
            status_filter = "status IN ('pending', 'waiting_for_user')"
        else:
            # Daemon/non-interactive: only 'pending' (skip user input tasks)
            status_filter = "status = 'pending'"

        if only_not_enqueued:
            # Only get tasks that haven't been enqueued to Huey yet
            cursor.execute(f"""
                SELECT * FROM tasks
                WHERE job_id = ? AND {status_filter} AND enqueued_at IS NULL
                ORDER BY created_at
            """, (job_id,))
        else:
            # Get all pending tasks
            cursor.execute(f"""
                SELECT * FROM tasks
                WHERE job_id = ? AND {status_filter}
                ORDER BY created_at
            """, (job_id,))

        return [dict(row) for row in cursor.fetchall()]

    def enqueue_first_task(self, job_id: str, interactive: bool = False) -> bool:
        """
        Enqueue only the first pending task for a job to Huey.
        Used in interactive mode to process tasks one at a time.

        Args:
            job_id: Job ID to enqueue task for
            interactive: If True, include 'waiting_for_user' tasks. If False, only 'pending' tasks.

        Returns:
            True if a task was enqueued, False if no tasks available
        """
        # Get only one task that hasn't been enqueued yet
        # In interactive mode, include waiting_for_user tasks
        # In daemon mode, only include pending tasks
        tasks = self.get_pending_tasks(job_id, only_not_enqueued=True, interactive=interactive)

        if not tasks:
            log.debug(f"No new tasks to enqueue for job {job_id[:8]}")
            return False

        # Take only the first task
        task = tasks[0]
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
            cursor = self.connection.cursor()
            cursor.execute("""
                UPDATE tasks SET enqueued_at = ? WHERE id = ?
            """, (datetime.now().isoformat(), task_id))
            self.connection.commit()

            log.info(f"Enqueued task {task_id[:8]}... ({Path(folder_path).name}) to Huey")
            return True

        except Exception as e:
            log.error(f"Failed to enqueue task {task_id[:8]}: {e}", exc_info=True)
            return False

    def enqueue_all_tasks(self, job_id: str, progress_callback: Optional[Callable] = None,
                         interactive: bool = False):
        """
        Enqueue all pending tasks for a job to Huey.

        Only enqueues tasks that haven't been enqueued before (enqueued_at IS NULL).
        This prevents duplicate tasks in Huey's queue.

        Args:
            job_id: Job ID to enqueue tasks for
            progress_callback: Optional callback for progress updates
            interactive: If True, include 'waiting_for_user' tasks. If False (daemon mode),
                        only enqueue 'pending' tasks (excludes user input tasks)
        """
        # Only get tasks that haven't been enqueued yet
        tasks = self.get_pending_tasks(job_id, only_not_enqueued=True, interactive=interactive)

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

    def get_jobs_for_user(self, user_id: str, status: Optional[List[str]] = None) -> List[Dict]:
        """
        Get all jobs for a specific user.

        Args:
            user_id: User ID to filter by
            status: Optional list of statuses to filter by

        Returns:
            List of job dictionaries
        """
        # Refresh connection to see latest updates from other processes
        self.refresh_connection()

        cursor = self.connection.cursor()

        if status:
            placeholders = ','.join(['?' for _ in status])
            query = f"""
                SELECT * FROM jobs
                WHERE user_id = ? AND status IN ({placeholders})
                ORDER BY created_at DESC
            """
            cursor.execute(query, [user_id] + status)
        else:
            cursor.execute("""
                SELECT * FROM jobs
                WHERE user_id = ?
                ORDER BY created_at DESC
            """, (user_id,))

        return [dict(row) for row in cursor.fetchall()]

    def get_tasks_for_job(self, job_id: str, status: Optional[List[str]] = None) -> List[Dict]:
        """
        Get all tasks for a specific job.

        Args:
            job_id: Job ID to get tasks for
            status: Optional list of statuses to filter by

        Returns:
            List of task dictionaries
        """
        # Refresh connection to see latest updates from other processes
        self.refresh_connection()

        cursor = self.connection.cursor()

        if status:
            placeholders = ','.join(['?' for _ in status])
            query = f"""
                SELECT * FROM tasks
                WHERE job_id = ? AND status IN ({placeholders})
                ORDER BY created_at
            """
            cursor.execute(query, [job_id] + status)
        else:
            cursor.execute("""
                SELECT * FROM tasks
                WHERE job_id = ?
                ORDER BY created_at
            """, (job_id,))

        return [dict(row) for row in cursor.fetchall()]

    def set_task_waiting_for_user(
        self,
        task_id: str,
        input_type: str,
        prompt: str,
        options: Optional[List[str]] = None,
        context: Optional[Dict] = None
    ):
        """
        Mark task as waiting for user input.

        Args:
            task_id: Task UUID
            input_type: Type of input needed:
                - 'llm_confirmation': Confirm LLM-selected candidate
                - 'manual_selection': Select from multiple candidates
                - 'manual_url': Enter URL in manual search mode
            prompt: User-facing prompt text
            options: Optional list of available options/candidates
            context: Optional context data (book info, candidates, etc.)
        """
        cursor = self.connection.cursor()
        cursor.execute("""
            UPDATE tasks
            SET status = 'waiting_for_user',
                user_input_type = ?,
                user_input_prompt = ?,
                user_input_options = ?,
                user_input_context = ?
            WHERE id = ?
        """, (
            input_type,
            prompt,
            json.dumps(options) if options else None,
            json.dumps(context, default=str) if context else None,
            task_id
        ))
        self.connection.commit()
        log.debug(f"Task {task_id[:8]} waiting for user input: {input_type}")

    def get_tasks_waiting_for_user(self, job_id: Optional[str] = None) -> List[Dict]:
        """
        Get all tasks waiting for user input.

        Args:
            job_id: Optional job ID to filter by

        Returns:
            List of task dictionaries with parsed user_input fields
        """
        self.refresh_connection()
        cursor = self.connection.cursor()

        if job_id:
            cursor.execute("""
                SELECT * FROM tasks
                WHERE job_id = ? AND status = 'waiting_for_user'
                ORDER BY created_at
            """, (job_id,))
        else:
            cursor.execute("""
                SELECT * FROM tasks
                WHERE status = 'waiting_for_user'
                ORDER BY created_at
            """)

        tasks = []
        for row in cursor.fetchall():
            task = dict(row)
            # Parse JSON fields for convenience
            if task.get('user_input_options'):
                try:
                    task['user_input_options'] = json.loads(task['user_input_options'])
                except json.JSONDecodeError:
                    pass
            if task.get('user_input_context'):
                try:
                    task['user_input_context'] = json.loads(task['user_input_context'])
                except json.JSONDecodeError:
                    pass
            tasks.append(task)

        return tasks

    def resume_task_from_user_input(
        self,
        task_id: str,
        user_response: str,
        clear_input_fields: bool = True
    ):
        """
        Resume a task after receiving user input.

        Args:
            task_id: Task UUID
            user_response: User's response (selection, URL, confirmation, etc.)
            clear_input_fields: Whether to clear user_input_* fields (default: True)
        """
        cursor = self.connection.cursor()

        if clear_input_fields:
            cursor.execute("""
                UPDATE tasks
                SET status = 'pending',
                    user_input_type = NULL,
                    user_input_prompt = NULL,
                    user_input_options = NULL,
                    user_input_context = NULL,
                    url = CASE
                        WHEN ? != '' THEN ?
                        ELSE url
                    END
                WHERE id = ?
            """, (user_response, user_response, task_id))
        else:
            # Keep input fields for debugging/auditing
            cursor.execute("""
                UPDATE tasks
                SET status = 'pending',
                    url = CASE
                        WHEN ? != '' THEN ?
                        ELSE url
                    END
                WHERE id = ?
            """, (user_response, user_response, task_id))

        self.connection.commit()
        log.debug(f"Task {task_id[:8]} resumed with user input")

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

        # Check if task was marked as waiting_for_user (daemon mode + needs interaction)
        # In this case, the status was already set, don't overwrite it
        # IMPORTANT: Check this FIRST before processing success/skip/failure
        cursor = queue_manager.connection.cursor()
        cursor.execute("SELECT status FROM tasks WHERE id = ?", (task_id,))
        current_status = cursor.fetchone()[0]

        if current_status == 'waiting_for_user':
            # Task is waiting for user input, preserve status and don't mark as completed
            # This prevents the task from being counted as done and allows next task to start
            log.info(f"[Worker {worker_id}] Task {task_id[:8]} is waiting_for_user, preserving status")
            # Clear the completed_at timestamp to prevent it from being counted as done
            cursor.execute("""
                UPDATE tasks SET completed_at = NULL WHERE id = ?
            """, (task_id,))
            queue_manager.connection.commit()
        elif success and not metadata.failed and not metadata.skip:
            # Success
            result_json = json.dumps(metadata.to_dict(), default=str)
            queue_manager.update_task_status(
                task_id,
                'completed',
                completed_at=datetime.now().isoformat(),
                result_json=result_json
            )
            log.info(f"[Worker {worker_id}] Completed task {task_id[:8]}")
        elif metadata.skip:
            # Skipped (user explicitly skipped, NOT waiting for input)
            queue_manager.update_task_status(
                task_id,
                'skipped',
                completed_at=datetime.now().isoformat(),
                error="Skipped by user"
            )
            log.info(f"[Worker {worker_id}] Skipped task {task_id[:8]}")
        else:
            # Failed
            queue_manager.update_task_status(
                task_id,
                'failed',
                completed_at=datetime.now().isoformat(),
                error=metadata.failed_exception or "Unknown error"
            )
            log.error(f"[Worker {worker_id}] Failed task {task_id[:8]}: {metadata.failed_exception}")

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
                            metadata_processor, log, task_id: Optional[str] = None) -> Optional[str]:
    """
    Discover URL for a folder using auto-search or manual search.

    This function is called by workers when processing tasks with url=None.
    It performs the same logic as BadaBoomBooksApp._get_url_for_folder().

    Args:
        folder_path: Path to the audiobook folder
        args: ProcessingArgs with search configuration
        metadata_processor: MetadataProcessor for reading OPF files
        log: Logger instance
        task_id: Optional task ID for queue tracking

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

        # If force_refresh AND from_opf are BOTH set, use OPF's source URL for re-scraping
        # If only force_refresh (without from_opf), ignore OPF and perform fresh search
        if args.force_refresh and args.from_opf:
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
            # Extract book info for context
            book_info = _extract_book_info_for_discovery(folder_path, metadata_processor, log, args.book_root, args)

            # Generate search term(s) - parallel alternatives if no OPF
            from .utils.metadata_cleaning import generate_search_alternatives

            if book_info.get('opf_exists'):
                # OPF exists - use single trusted source
                if book_info.get('title') and book_info.get('author'):
                    search_term = f"{book_info['title']} by {book_info['author']}"
                elif book_info.get('title'):
                    search_term = book_info['title']
                else:
                    search_term = generate_search_term(folder_path)
                search_alternatives = None
            else:
                # No OPF - generate parallel search alternatives from multiple sources
                if 'sources' in book_info:
                    search_alternatives = generate_search_alternatives(book_info['sources'])
                    # Use best alternative as primary search term for display
                    if search_alternatives:
                        search_term = search_alternatives[0]['term']
                        log.info(f"[WORKER] Using search term: {search_term} (from {search_alternatives[0]['source']})")
                    else:
                        search_term = generate_search_term(folder_path)
                        search_alternatives = None
                else:
                    # Fallback to legacy behavior
                    if book_info.get('title') and book_info.get('author'):
                        search_term = f"{book_info['title']} by {book_info['author']}"
                    elif book_info.get('title'):
                        search_term = book_info['title']
                    elif book_info.get('author'):
                        search_term = f"{folder_path.name} by {book_info['author']}"
                    else:
                        search_term = generate_search_term(folder_path)
                    search_alternatives = None

            # Determine sites to search
            if args.site == 'all':
                site_keys = list(SCRAPER_REGISTRY.keys())
            else:
                site_keys = [args.site]

            # Perform search
            # Note: We're always in worker context when this function is called from worker thread
            # Set in_worker_context=True to prevent blocking on input() calls
            auto_search = AutoSearchEngine(
                debug_enabled=args.debug,
                enable_ai_selection=args.llm_select,
                yolo=args.yolo,
                task_id=task_id,
                in_worker_context=True
            )
            site_key, url, html = auto_search.search_and_select_with_context(
                search_term, site_keys, book_info, args.search_limit, args.download_limit, args.search_delay,
                search_alternatives=search_alternatives
            )

            if site_key and url:
                log.info(f"Auto-search found {SCRAPER_REGISTRY[site_key]['domain']}: {url}")
                return url
            else:
                log.info(f"Auto-search failed for {folder_path.name}, skipping")
                return None

        else:
            # Manual search
            # Check if we're in daemon mode (non-interactive) and not YOLO
            if not args.interactive and not args.yolo and task_id:
                from .queue_manager import QueueManager
                queue_mgr = QueueManager()

                # Mark task as waiting for user input
                queue_mgr.set_task_waiting_for_user(
                    task_id=task_id,
                    input_type='manual_url',
                    prompt='Manual search requires user input (daemon mode - skipped)',
                    options=[],
                    context={'folder': str(folder_path), 'mode': 'daemon', 'reason': 'interactive_mode_disabled'}
                )
                queue_mgr.close()

                log.info(f"Daemon mode: Marking {folder_path.name} as waiting_for_user (manual search requires interaction)")
                return None  # Skip for now, will be picked up by interactive worker later

            book_info = _extract_book_info_for_discovery(folder_path, metadata_processor, log, args.book_root, args)
            manual_search = ManualSearchHandler(task_id=task_id)
            site_key, url = manual_search.handle_manual_search_with_context(folder_path, book_info, args.site)

            if site_key and url:
                return url
            else:
                return None

    except Exception as e:
        log.error(f"Error discovering URL for {folder_path.name}: {e}", exc_info=True)
        return None


def _extract_book_info_for_discovery(folder_path: Path, metadata_processor, log, book_root: Optional[Path] = None, args: Optional[ProcessingArgs] = None) -> dict:
    """
    Extract book information for URL discovery context.

    Returns multi-source metadata when no OPF exists, allowing parallel search strategies.

    Args:
        folder_path: Path to audiobook folder
        metadata_processor: MetadataProcessor for reading OPF
        log: Logger instance
        book_root: If provided (when using -R flag), will attempt to extract
                  author from parent directory when no author is found in metadata
        args: Optional ProcessingArgs to check force_refresh/from_opf flags

    Returns:
        Dictionary with book info (folder_name, title, author, source)
        If no OPF: includes 'sources' key with both folder and ID3 metadata
    """
    from .utils.helpers import find_metadata_opf, find_audio_files
    from .utils.metadata_cleaning import extract_metadata_from_sources
    from xml.etree import ElementTree as ET

    book_info = {
        'folder_name': folder_path.name,
        'source': 'folder name'
    }

    try:
        # Check if we should read OPF file
        # Skip OPF if force_refresh is set WITHOUT from_opf (user wants fresh search)
        should_read_opf = True
        if args and args.force_refresh and not args.from_opf:
            should_read_opf = False
            log.debug(f"Ignoring OPF for {folder_path.name} (force_refresh without from_opf)")

        # Try to read existing OPF file first (if allowed)
        # OPF is trusted completely - if it exists, use it exclusively
        if should_read_opf:
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
                    book_info['opf_exists'] = True
                    # OPF data is trusted - return immediately
                    return book_info
                except Exception as e:
                    log.debug(f"Error reading OPF for {folder_path.name}: {e}")

        # No OPF - extract from both ID3 and folder name as equal sources
        book_info['opf_exists'] = False

        # Read ID3 tags
        id3_title = None
        id3_author = None
        id3_album = None
        try:
            import mutagen

            audio_files = find_audio_files(folder_path)
            audio_file = audio_files[0] if audio_files else None
            if audio_file:
                audio = mutagen.File(audio_file, easy=True)
                if audio:
                    if 'title' in audio and audio['title']:
                        id3_title = audio['title'][0]
                    if 'artist' in audio and audio['artist']:
                        id3_author = audio['artist'][0]
                    if 'album' in audio and audio['album']:
                        id3_album = audio['album'][0]
        except Exception as e:
            log.debug(f"Error reading ID3 tags for {folder_path.name}: {e}")

        # Get cleaned metadata from both sources
        metadata_sources = extract_metadata_from_sources(
            folder_path=folder_path,
            id3_title=id3_title,
            id3_author=id3_author,
            id3_album=id3_album
        )

        # Store multi-source data for parallel search
        book_info['sources'] = metadata_sources

        # For backward compatibility, populate main fields with best available data
        # Prefer ID3 if valid and not garbage, otherwise use folder
        id3_data = metadata_sources['id3']
        folder_data = metadata_sources['folder']

        if id3_data['valid'] and not id3_data['garbage_detected']:
            # Use ID3 data for primary fields
            if id3_data['title']:
                book_info['title'] = id3_data['title']
            if id3_data['author']:
                book_info['author'] = id3_data['author']
            if id3_data['album']:
                book_info['series'] = id3_data['album']
            book_info['source'] = 'ID3 tags'
            log.debug(f"Using ID3 metadata for {folder_path.name}: {id3_data['title']} by {id3_data['author']}")
        elif folder_data['valid']:
            # Fallback to folder name
            book_info['title'] = folder_data['cleaned']
            book_info['source'] = 'folder name (cleaned)'
            log.debug(f"Using folder name for {folder_path.name}: {folder_data['cleaned']}")
            if id3_data['garbage_detected']:
                log.warning(f"Garbage detected in ID3 tags for {folder_path.name}, using folder name instead")

        # If -R flag was used and no author was found, try parent directory
        if book_root is not None and 'author' not in book_info:
            try:
                parent_dir = folder_path.parent

                # Resolve both paths to handle UNC vs drive letter issues
                # Convert book_root to Path if it's a string (from JSON deserialization)
                if isinstance(book_root, str):
                    from pathlib import Path as PathType
                    book_root = PathType(book_root)

                parent_resolved = parent_dir.resolve()
                root_resolved = book_root.resolve()

                # Extract author from parent if parent is book_root or within book_root
                # This handles structures like: -R "Author/" discovers "Author/Book"
                # or -R "Root/" discovers "Root/Author/Book"
                try:
                    is_within_root = parent_resolved.is_relative_to(root_resolved)
                except AttributeError:
                    # Python < 3.9 compatibility
                    is_within_root = root_resolved in parent_resolved.parents or parent_resolved == root_resolved

                if is_within_root:
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
            task_id = getattr(metadata, 'task_id', None)
            url_or_marker = _discover_url_for_folder(folder_path, args, metadata_processor, log, task_id)

            if url_or_marker is None:
                # Check if task was marked as waiting_for_user by checking the database
                # This happens in both daemon mode and interactive mode when worker needs user input
                if task_id:
                    from .queue_manager import QueueManager
                    qm = QueueManager()
                    try:
                        cursor = qm.connection.cursor()
                        cursor.execute("SELECT status FROM tasks WHERE id = ?", (task_id,))
                        task_status = cursor.fetchone()
                        if task_status and task_status[0] == 'waiting_for_user':
                            # Task is waiting for user input, don't mark as failed
                            log.info(f"Task {folder_path.name} is waiting_for_user, pausing processing")
                            metadata.skip = True  # Use skip status to indicate it's not a failure
                            return True  # Return success so task isn't marked as failed
                    finally:
                        qm.close()

                # Normal failure case (user skipped, URL discovery failed, or no task_id)
                metadata.mark_as_failed("URL discovery failed or skipped by user")
                return False

            log.info(f"Discovered URL: {url_or_marker}")

        # Step 1: Scrape metadata
        if url_or_marker == "OPF":
            opf_file = find_metadata_opf(folder_path)
            if not opf_file:
                metadata.mark_as_failed("No metadata.opf found")
                return False

            opf_metadata = metadata_processor.read_opf_metadata(opf_file)
            opf_metadata.task_id = metadata.task_id  # Preserve task_id

            # If URL is present in OPF, try to scrape missing fields (cover_url, summary, etc.)
            if opf_metadata.url:
                log.info(f"Re-scraping from OPF source URL to supplement metadata: {opf_metadata.url}")
                site_key = detect_url_site(opf_metadata.url)
                if site_key:
                    try:
                        # Preprocess URL if needed
                        if site_key == 'audible':
                            preprocess_audible_url(opf_metadata)

                        # Make HTTP request
                        if site_key == 'audible':
                            scraped_metadata, response = http_request_audible_api(opf_metadata, log)
                        else:
                            scraped_metadata, response = http_request_generic(opf_metadata, log)

                        if not scraped_metadata.failed:
                            # Scrape metadata
                            if site_key == 'audible':
                                scraper = AudibleScraper()
                            elif site_key == 'goodreads':
                                scraper = GoodreadsScraper()
                            elif site_key == 'lubimyczytac':
                                scraper = LubimyczytacScraper()
                            else:
                                log.warning(f"Unknown site for supplemental scraping: {site_key}")
                                scraper = None

                            if scraper:
                                scraped_metadata = scraper.scrape_metadata(scraped_metadata, response, log)

                                # Merge scraped data into OPF data (OPF takes precedence)
                                for field in ['summary', 'genres', 'cover_url', 'language']:
                                    if not getattr(opf_metadata, field) and getattr(scraped_metadata, field):
                                        setattr(opf_metadata, field, getattr(scraped_metadata, field))
                                        log.debug(f"Supplemented {field} from scraping")
                    except Exception as e:
                        log.warning(f"Failed to supplement OPF metadata from source URL: {e}")

            metadata = opf_metadata
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
