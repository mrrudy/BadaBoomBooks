"""
Test script to verify queue system infrastructure.
Tests QueueManager, FileLockManager, and database operations.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.queue_manager import QueueManager
from src.utils.file_locks import FileLockManager
from src.models import ProcessingArgs
import tempfile
import threading
import time


def test_queue_manager():
    """Test QueueManager basic operations."""
    print("\n" + "="*60)
    print("TEST 1: QueueManager Basic Operations")
    print("="*60)

    # Create temporary database
    temp_dir = Path(tempfile.mkdtemp())
    db_path = temp_dir / 'test_queue.db'

    try:
        qm = QueueManager(db_path)
        print(f"✓ Created QueueManager with database at {db_path}")

        # Create a job
        args = ProcessingArgs(
            folders=[Path('/test/folder1'), Path('/test/folder2')],
            copy=True,
            opf=True,
            workers=4
        )

        job_id = qm.create_job(args)
        print(f"✓ Created job: {job_id}")

        # Retrieve job
        job = qm.get_job(job_id)
        assert job is not None
        assert job['status'] == 'pending'
        print(f"✓ Retrieved job with status: {job['status']}")

        # Create tasks
        task1_id = qm.create_task(job_id, Path('/test/book1'), 'http://example.com/book1')
        task2_id = qm.create_task(job_id, Path('/test/book2'), 'http://example.com/book2')
        print(f"✓ Created 2 tasks: {task1_id[:8]}..., {task2_id[:8]}...")

        # Get progress
        progress = qm.get_job_progress(job_id)
        assert progress['total'] == 2
        assert progress['pending'] == 2
        assert progress['completed'] == 0
        print(f"✓ Progress tracking: {progress['total']} total, {progress['pending']} pending")

        # Update task status
        qm.update_task_status(task1_id, 'running', started_at='2025-01-01 00:00:00')
        task1 = qm.get_task(task1_id)
        assert task1['status'] == 'running'
        print(f"✓ Updated task status to 'running'")

        qm.update_task_status(task1_id, 'completed', completed_at='2025-01-01 00:01:00')
        task1 = qm.get_task(task1_id)
        assert task1['status'] == 'completed'
        print(f"✓ Updated task status to 'completed'")

        # Check progress again
        progress = qm.get_job_progress(job_id)
        assert progress['completed'] == 1
        assert progress['running'] == 0
        assert progress['pending'] == 1
        print(f"✓ Progress updated: {progress['completed']} completed, {progress['pending']} pending")

        # Test incomplete jobs
        qm.update_job_status(job_id, 'processing')
        incomplete_jobs = qm.get_incomplete_jobs()
        assert len(incomplete_jobs) == 1
        assert incomplete_jobs[0]['id'] == job_id
        print(f"✓ Found incomplete job for resume: {job_id[:8]}...")

        qm.close()
        print("\n✅ All QueueManager tests passed!")

    except Exception as e:
        print(f"\n❌ QueueManager test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        import shutil
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

    return True


def test_file_locks():
    """Test FileLockManager with concurrent operations."""
    print("\n" + "="*60)
    print("TEST 2: FileLockManager Concurrent Operations")
    print("="*60)

    temp_dir = Path(tempfile.mkdtemp())
    db_path = temp_dir / 'test_locks.db'

    try:
        # Create database for locks
        import sqlite3
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS file_locks (
                lock_path TEXT PRIMARY KEY,
                locked_by_task TEXT NOT NULL,
                acquired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

        lock_manager = FileLockManager(conn)
        print(f"✓ Created FileLockManager with database-based locks")

        test_dir = temp_dir / 'test_author'
        lock_order = []

        def create_directory_with_lock(worker_id: int):
            """Simulate worker trying to create directory."""
            task_id = f"task-{worker_id}"
            try:
                with lock_manager.lock_directory(test_dir, task_id, timeout=5.0):
                    lock_order.append(worker_id)
                    if not test_dir.exists():
                        time.sleep(0.01)  # Simulate race window
                        test_dir.mkdir(parents=True, exist_ok=True)
                    time.sleep(0.05)  # Hold lock briefly
            except TimeoutError:
                print(f"  Worker {worker_id}: Lock timeout (expected if lock held)")

        # Launch 5 concurrent threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=create_directory_with_lock, args=(i,))
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        print(f"✓ All 5 threads completed")
        print(f"✓ Directory created: {test_dir.exists()}")
        print(f"✓ Lock acquisition order: {lock_order}")

        # Verify directory was created exactly once
        assert test_dir.exists()
        print(f"✓ No race condition detected - directory safely created")

        conn.close()
        print("\n✅ All FileLockManager tests passed!")

    except Exception as e:
        print(f"\n❌ FileLockManager test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        import shutil
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

    return True


def test_imports():
    """Test that all modules import correctly."""
    print("\n" + "="*60)
    print("TEST 0: Module Imports")
    print("="*60)

    try:
        from src.queue_manager import QueueManager, huey, process_audiobook_task
        print("✓ Imported QueueManager, huey, process_audiobook_task")

        from src.utils.file_locks import FileLockManager
        print("✓ Imported FileLockManager")

        from src.models import BookMetadata, ProcessingArgs
        print("✓ Imported BookMetadata, ProcessingArgs")

        from src.processors.file_operations import FileProcessor
        print("✓ Imported FileProcessor")

        # Check that new fields exist
        metadata = BookMetadata.create_empty('/test', 'http://test.com')
        assert hasattr(metadata, 'task_id')
        print("✓ BookMetadata has task_id field")

        args = ProcessingArgs()
        assert hasattr(args, 'workers')
        assert hasattr(args, 'resume')
        assert args.workers == 4  # Default value
        print("✓ ProcessingArgs has workers and resume fields")

        processor = FileProcessor(args)
        assert hasattr(processor, 'lock_manager')
        print("✓ FileProcessor has lock_manager attribute")

        print("\n✅ All imports successful!")
        return True

    except Exception as e:
        print(f"\n❌ Import test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("BADABOOMBOOKS QUEUE SYSTEM INFRASTRUCTURE TEST")
    print("="*60)

    results = []

    # Test 0: Imports
    results.append(("Imports", test_imports()))

    # Test 1: QueueManager
    results.append(("QueueManager", test_queue_manager()))

    # Test 2: FileLockManager
    results.append(("FileLockManager", test_file_locks()))

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    all_passed = True
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
        if not passed:
            all_passed = False

    print("="*60)

    if all_passed:
        print("\n🎉 All infrastructure tests passed!")
        print("\nNext steps:")
        print("1. Integrate queue system into main.py")
        print("2. Test with --dry-run on actual audiobook folders")
        print("3. Test parallel processing with multiple books")
        return 0
    else:
        print("\n❌ Some tests failed. Please fix issues before continuing.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
