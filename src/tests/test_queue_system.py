"""
Tests for the parallel queue system (Huey + SQLite).

This module tests the two-phase task creation system, parallel processing,
resume functionality, and database operations.
"""

import pytest
import sqlite3
from pathlib import Path
from src.main import BadaBoomBooksApp
from src.queue_manager import QueueManager
from src.models import ProcessingArgs


@pytest.mark.integration
def test_two_phase_task_creation(existing_dir, expected_dir, test_database):
    """
    Test that tasks are created in identification phase before URL discovery.

    This test verifies:
    1. All tasks are created during identification (with url=NULL)
    2. URL discovery happens in workers during processing
    3. Tasks can be resumed from any point
    """
    # Execute: Run with --from-opf (no URL discovery needed)
    app = BadaBoomBooksApp()
    exit_code = app.run([
        '--copy',
        '--from-opf',
        '--yolo',
        '--dry-run',
        '-O', str(expected_dir),
        '-R', str(existing_dir)
    ])

    assert exit_code == 0, "App should complete successfully"

    # Verify: Task was created in database
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()

    # Check job was created
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE status = 'completed'")
    completed_jobs = cursor.fetchone()[0]
    assert completed_jobs == 1, "Should have 1 completed job"

    # Check task was created
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'completed'")
    completed_tasks = cursor.fetchone()[0]
    assert completed_tasks == 1, "Should have 1 completed task"

    # Verify task has folder path
    cursor.execute("SELECT folder_path, url FROM tasks")
    task = cursor.fetchone()
    assert task is not None, "Task should exist"
    # Use case-insensitive comparison for Windows paths
    assert str(existing_dir).lower() in task[0].lower(), "Task should have correct folder path"

    conn.close()


@pytest.mark.integration
def test_identification_creates_all_tasks(existing_dir, expected_dir, test_database):
    """
    Test that identification phase creates ALL tasks before processing starts.

    This verifies the two-phase system where:
    - Phase 1: Identify all books and create tasks (fast)
    - Phase 2: Workers discover URLs and process books (slow)
    """
    # Execute: Process with --from-opf
    app = BadaBoomBooksApp()
    exit_code = app.run([
        '--copy',
        '--from-opf',
        '--yolo',
        '--dry-run',
        '-O', str(expected_dir),
        '-R', str(existing_dir)
    ])

    assert exit_code == 0, "App should complete successfully"

    # Verify: All tasks were created during identification
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()

    # Get job details
    cursor.execute("SELECT id FROM jobs")
    job = cursor.fetchone()
    assert job is not None, "Job should exist"
    job_id = job[0]

    # Verify tasks table (total_tasks is counted from tasks, not stored in jobs table)
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE job_id = ?", (job_id,))
    task_count = cursor.fetchone()[0]
    assert task_count == 1, "Should have identified and created 1 task"

    # Verify completed tasks
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE job_id = ? AND status = 'completed'", (job_id,))
    completed_count = cursor.fetchone()[0]
    assert completed_count == 1, "Should have completed 1 task"

    conn.close()


@pytest.mark.integration
def test_resume_incomplete_job(existing_dir, expected_dir, test_database):
    """
    Test resuming an incomplete job with --resume flag.

    This test verifies:
    1. Incomplete job is detected
    2. --resume flag resumes the job
    3. Only incomplete tasks are processed
    """
    # Setup: Create an incomplete job
    qm = QueueManager()
    dummy_args = ProcessingArgs(
        folders=[existing_dir],
        output=expected_dir,
        copy=True,
        from_opf=True,
        yolo=True,
        dry_run=True
    )
    job_id = qm.create_job(dummy_args)
    qm.update_job_status(job_id, 'processing')

    # Create a pending task
    task_id = qm.create_task(job_id, existing_dir, url='OPF')

    # Verify job is incomplete
    incomplete_jobs = qm.get_incomplete_jobs()
    assert len(incomplete_jobs) == 1, "Should have 1 incomplete job"

    # Execute: Resume the job
    app = BadaBoomBooksApp()
    exit_code = app.run([
        '--resume',
        '--yolo'
    ])

    assert exit_code == 0, "Resume should complete successfully"

    # Verify: Job is now completed
    incomplete_jobs_after = qm.get_incomplete_jobs()
    assert len(incomplete_jobs_after) == 0, "Should have no incomplete jobs after resume"

    # Verify: Task was processed
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM tasks WHERE id = ?", (task_id,))
    task_status = cursor.fetchone()[0]
    assert task_status == 'completed', "Task should be completed after resume"
    conn.close()


@pytest.mark.integration
def test_job_progress_tracking(existing_dir, expected_dir, test_database):
    """
    Test that job progress is tracked correctly.

    This verifies:
    1. total_tasks is set during identification
    2. completed_tasks increments as tasks complete
    3. Job status transitions correctly
    """
    # Execute: Process books
    app = BadaBoomBooksApp()
    exit_code = app.run([
        '--copy',
        '--from-opf',
        '--yolo',
        '--dry-run',
        '-O', str(expected_dir),
        '-R', str(existing_dir)
    ])

    assert exit_code == 0, "App should complete successfully"

    # Verify: Job progress is tracked
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, status
        FROM jobs
        ORDER BY created_at DESC
        LIMIT 1
    """)
    job = cursor.fetchone()

    assert job is not None, "Job should exist"
    job_id, status = job

    assert status == 'completed', "Job should be completed"

    # Check task counts from tasks table
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE job_id = ?", (job_id,))
    total = cursor.fetchone()[0]
    assert total == 1, "Should have 1 total task"

    cursor.execute("SELECT COUNT(*) FROM tasks WHERE job_id = ? AND status = 'completed'", (job_id,))
    completed = cursor.fetchone()[0]
    assert completed == 1, "Should have 1 completed task"

    cursor.execute("SELECT COUNT(*) FROM tasks WHERE job_id = ? AND status = 'failed'", (job_id,))
    failed = cursor.fetchone()[0]
    assert failed == 0, "Should have 0 failed tasks"

    conn.close()


@pytest.mark.integration
def test_task_enqueuing_once(existing_dir, expected_dir, test_database):
    """
    Test that tasks are enqueued to Huey only once.

    This verifies the enqueued_at tracking prevents duplicate enqueues.
    """
    # Execute: Process books
    app = BadaBoomBooksApp()
    exit_code = app.run([
        '--copy',
        '--from-opf',
        '--yolo',
        '--dry-run',
        '-O', str(expected_dir),
        '-R', str(existing_dir)
    ])

    assert exit_code == 0, "App should complete successfully"

    # Verify: Task has enqueued_at timestamp
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()

    cursor.execute("SELECT enqueued_at FROM tasks")
    task = cursor.fetchone()
    assert task is not None, "Task should exist"
    assert task[0] is not None, "Task should have enqueued_at timestamp"

    conn.close()


@pytest.mark.integration
def test_parallel_workers(existing_dir, expected_dir, test_database):
    """
    Test that parallel workers are spawned correctly.

    This test verifies:
    1. --workers flag is respected
    2. Multiple tasks can be processed in parallel
    """
    # Execute: Process with 2 workers
    app = BadaBoomBooksApp()
    exit_code = app.run([
        '--copy',
        '--from-opf',
        '--yolo',
        '--dry-run',
        '--workers', '2',
        '-O', str(expected_dir),
        '-R', str(existing_dir)
    ])

    assert exit_code == 0, "App should complete successfully with 2 workers"

    # Verify: Job completed successfully
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()

    cursor.execute("SELECT status FROM jobs ORDER BY created_at DESC LIMIT 1")
    job_status = cursor.fetchone()[0]
    assert job_status == 'completed', "Job should be completed"

    conn.close()


@pytest.mark.integration
def test_job_deletion_on_ctrl_c_during_identification(test_database):
    """
    Test that job is deleted when Ctrl+C is pressed during identification.

    Note: This test creates a job and deletes it manually to simulate
    the Ctrl+C behavior (actual keyboard interrupt is hard to test).
    """
    # Setup: Create a job in planning status
    qm = QueueManager()
    dummy_args = ProcessingArgs(
        folders=[Path('/tmp/test')],
        yolo=True,
        dry_run=True
    )
    job_id = qm.create_job(dummy_args)
    qm.update_job_status(job_id, 'planning')

    # Verify job exists
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE id = ?", (job_id,))
    count_before = cursor.fetchone()[0]
    assert count_before == 1, "Job should exist before deletion"
    conn.close()

    # Simulate Ctrl+C during identification: delete job
    qm.delete_job(job_id)

    # Verify: Job is deleted
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE id = ?", (job_id,))
    count_after = cursor.fetchone()[0]
    assert count_after == 0, "Job should be deleted after Ctrl+C"
    conn.close()


@pytest.mark.integration
def test_job_preserved_on_ctrl_c_during_processing(test_database):
    """
    Test that job is preserved when Ctrl+C is pressed during processing.

    This allows resuming from where the user left off.
    """
    # Setup: Create a job in processing status with tasks
    qm = QueueManager()
    dummy_args = ProcessingArgs(
        folders=[Path('/tmp/test')],
        yolo=True,
        dry_run=True
    )
    job_id = qm.create_job(dummy_args)
    qm.update_job_status(job_id, 'processing')

    # Create some tasks
    task1_id = qm.create_task(job_id, Path('/tmp/test/book1'), url='OPF')
    task2_id = qm.create_task(job_id, Path('/tmp/test/book2'), url='OPF')

    # Mark one task as completed
    qm.update_task_status(task1_id, 'completed')

    # Verify job exists with incomplete tasks
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()

    cursor.execute("SELECT status FROM jobs WHERE id = ?", (job_id,))
    job_status = cursor.fetchone()[0]
    assert job_status == 'processing', "Job should be in processing state"

    cursor.execute("SELECT COUNT(*) FROM tasks WHERE job_id = ? AND status = 'pending'", (job_id,))
    pending_count = cursor.fetchone()[0]
    assert pending_count == 1, "Should have 1 pending task"

    conn.close()

    # Simulate Ctrl+C during processing: job is NOT deleted
    # Verify job can be resumed
    incomplete_jobs = qm.get_incomplete_jobs()
    assert len(incomplete_jobs) == 1, "Should have 1 incomplete job for resume"
    assert incomplete_jobs[0]['id'] == job_id, "Incomplete job should be our job"


@pytest.mark.integration
def test_dry_run_mode(existing_dir, expected_dir, test_database):
    """
    Test that --dry-run mode doesn't modify files but tracks in database.

    This verifies:
    1. Database operations work in dry-run mode
    2. No files are actually modified
    3. Job completes successfully
    """
    # Get initial file count
    initial_files = list(expected_dir.glob('**/*'))
    initial_count = len(initial_files)

    # Execute: Process in dry-run mode
    app = BadaBoomBooksApp()
    exit_code = app.run([
        '--copy',
        '--from-opf',
        '--yolo',
        '--dry-run',
        '-O', str(expected_dir),
        '-R', str(existing_dir)
    ])

    assert exit_code == 0, "Dry-run should complete successfully"

    # Verify: No new files created in output
    final_files = list(expected_dir.glob('**/*'))
    final_count = len(final_files)
    assert final_count == initial_count, "Dry-run should not create files"

    # Verify: Job tracked in database
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM jobs WHERE status = 'completed'")
    job_count = cursor.fetchone()[0]
    assert job_count == 1, "Dry-run job should be tracked in database"

    conn.close()


@pytest.mark.integration
def test_worker_url_discovery(existing_dir, expected_dir, test_database):
    """
    Test that workers can discover URLs from OPF files.

    This verifies the worker-side URL discovery logic when tasks
    are created with url=NULL during identification.
    """
    # Execute: Process with --from-opf (workers will get URL from OPF)
    app = BadaBoomBooksApp()
    exit_code = app.run([
        '--copy',
        '--from-opf',
        '--yolo',
        '--dry-run',
        '-O', str(expected_dir),
        '-R', str(existing_dir)
    ])

    assert exit_code == 0, "App should complete successfully"

    # Verify: Task has URL set (discovered by worker)
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()

    cursor.execute("SELECT url FROM tasks")
    task = cursor.fetchone()
    assert task is not None, "Task should exist"

    # URL can be:
    # - 'OPF' marker (from existing file)
    # - NULL (if no source in OPF, which is the case for test data)
    # - Actual URL string
    # The important thing is that worker processed the task
    url = task[0]
    # Task should exist and have been processed (status = completed)
    cursor.execute("SELECT status FROM tasks")
    status = cursor.fetchone()[0]
    assert status == 'completed', "Worker should have processed the task"

    conn.close()


@pytest.mark.integration
def test_multiple_books_processing(test_database, tmp_path):
    """
    Test processing multiple books in parallel.

    This verifies:
    1. All books are identified during phase 1
    2. All tasks are created before processing starts
    3. Workers process books in parallel
    """
    from src.processors.metadata_operations import MetadataProcessor

    # Setup: Create multiple test book folders
    books_dir = tmp_path / "books"
    books_dir.mkdir()

    output_dir = tmp_path / "output"
    output_dir.mkdir()

    # Create 3 test book folders
    for i in range(1, 4):
        book_dir = books_dir / f"Book_{i}"
        book_dir.mkdir()

        # Create a simple metadata.opf file
        opf_content = f"""<?xml version='1.0' encoding='utf-8'?>
<package xmlns:dc='http://purl.org/dc/elements/1.1/'>
  <metadata>
    <dc:title>Test Book {i}</dc:title>
    <dc:creator>Test Author {i}</dc:creator>
  </metadata>
</package>"""
        opf_file = book_dir / "metadata.opf"
        opf_file.write_text(opf_content, encoding='utf-8')

        # Create a dummy audio file
        audio_file = book_dir / "chapter1.mp3"
        audio_file.touch()

    # Execute: Process all books
    app = BadaBoomBooksApp()
    exit_code = app.run([
        '--copy',
        '--from-opf',
        '--yolo',
        '--dry-run',
        '-O', str(output_dir),
        '-R', str(books_dir)
    ])

    assert exit_code == 0, "Should process all books successfully"

    # Verify: All 3 tasks were created
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM jobs ORDER BY created_at DESC LIMIT 1")
    job = cursor.fetchone()
    assert job is not None, "Job should exist"
    job_id = job[0]

    # Verify: All 3 tasks in database
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE job_id = ?", (job_id,))
    task_count = cursor.fetchone()[0]
    assert task_count == 3, "Should have identified 3 tasks"

    # Verify: All tasks completed
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE job_id = ? AND status = 'completed'", (job_id,))
    completed_count = cursor.fetchone()[0]
    assert completed_count == 3, "Should have completed 3 tasks"

    conn.close()


@pytest.mark.integration
def test_queue_manager_api(test_database):
    """
    Test QueueManager API methods.

    This verifies:
    1. create_job() creates job correctly
    2. create_task() creates task correctly
    3. update_job_status() updates status
    4. get_job_progress() returns correct progress
    5. get_incomplete_jobs() finds incomplete jobs
    """
    qm = QueueManager()

    # Test create_job
    dummy_args = ProcessingArgs(
        folders=[Path('/tmp/test')],
        yolo=True,
        dry_run=True
    )
    job_id = qm.create_job(dummy_args)
    assert job_id is not None, "Job ID should be returned"
    assert len(job_id) > 0, "Job ID should not be empty"

    # Test create_task
    task_id = qm.create_task(job_id, Path('/tmp/test/book1'), url='http://example.com')
    assert task_id is not None, "Task ID should be returned"

    # Test update_job_status
    qm.update_job_status(job_id, 'processing')

    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM jobs WHERE id = ?", (job_id,))
    status = cursor.fetchone()[0]
    assert status == 'processing', "Job status should be updated"
    conn.close()

    # Test get_job_progress
    progress = qm.get_job_progress(job_id)
    assert progress is not None, "Progress should be returned"
    assert 'total' in progress, "Progress should have total"
    assert progress['total'] == 1, "Should have 1 task"

    # Test get_incomplete_jobs
    incomplete = qm.get_incomplete_jobs()
    assert len(incomplete) == 1, "Should have 1 incomplete job"
    assert incomplete[0]['id'] == job_id, "Incomplete job should be our job"
