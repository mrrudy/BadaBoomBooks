"""
Thread-safe file locking for parallel processing.

Uses portalocker library for cross-platform file locks.
Fallback to database-based locks if file locking unavailable.
"""

import time
import logging as log
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

# Try to import portalocker for OS-level locks
try:
    import portalocker
    HAS_PORTALOCKER = True
except ImportError:
    HAS_PORTALOCKER = False
    log.warning("portalocker not available, using database-based locks")


class FileLockManager:
    """Manages file system locks for directory creation."""

    def __init__(self, db_connection=None):
        """
        Initialize lock manager.

        Args:
            db_connection: SQLite connection for database-based locks
        """
        self.db_connection = db_connection
        self.use_db_locks = not HAS_PORTALOCKER or db_connection is not None

    @contextmanager
    def lock_directory(self, directory_path: Path, task_id: str,
                      timeout: float = 30.0, poll_interval: float = 0.1):
        """
        Context manager for directory creation lock.

        Args:
            directory_path: Path to lock (author or series directory)
            task_id: Task ID requesting lock
            timeout: Maximum seconds to wait for lock
            poll_interval: Seconds between lock attempts

        Yields:
            True when lock acquired

        Raises:
            TimeoutError: If lock not acquired within timeout

        Example:
            with lock_mgr.lock_directory(author_dir, task_id):
                author_dir.mkdir(parents=True, exist_ok=True)
        """
        if self.use_db_locks:
            yield from self._db_lock(directory_path, task_id, timeout, poll_interval)
        else:
            yield from self._file_lock(directory_path, timeout)

    def _file_lock(self, directory_path: Path, timeout: float):
        """OS-level file lock using portalocker."""
        lock_file_path = directory_path.parent / f".{directory_path.name}.lock"
        lock_file_path.parent.mkdir(parents=True, exist_ok=True)

        lock_file = None
        try:
            lock_file = open(lock_file_path, 'w')
            portalocker.lock(lock_file, portalocker.LOCK_EX, timeout=timeout)
            log.debug(f"Acquired file lock: {lock_file_path}")
            yield True
        finally:
            if lock_file:
                portalocker.unlock(lock_file)
                lock_file.close()
                try:
                    lock_file_path.unlink()
                except:
                    pass

    def _db_lock(self, directory_path: Path, task_id: str,
                 timeout: float, poll_interval: float):
        """Database-based lock for cross-process coordination."""
        normalized_path = str(directory_path.resolve())
        start_time = time.time()

        while True:
            try:
                # Attempt to acquire lock
                cursor = self.db_connection.cursor()
                cursor.execute(
                    "INSERT INTO file_locks (lock_path, locked_by_task) VALUES (?, ?)",
                    (normalized_path, task_id)
                )
                self.db_connection.commit()
                log.debug(f"Acquired DB lock: {normalized_path} for task {task_id}")
                break
            except Exception as e:
                # Lock already held
                if time.time() - start_time > timeout:
                    raise TimeoutError(f"Could not acquire lock for {normalized_path} within {timeout}s")
                time.sleep(poll_interval)

        try:
            yield True
        finally:
            # Release lock
            cursor = self.db_connection.cursor()
            cursor.execute(
                "DELETE FROM file_locks WHERE lock_path = ? AND locked_by_task = ?",
                (normalized_path, task_id)
            )
            self.db_connection.commit()
            log.debug(f"Released DB lock: {normalized_path}")
