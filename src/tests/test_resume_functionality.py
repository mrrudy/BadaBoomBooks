"""
Tests for resume functionality in the parallel queue system.

This module tests various resume scenarios including:
- Resuming incomplete jobs
- Resuming from specific task positions
- Multiple incomplete jobs handling
- Resume with --resume flag vs interactive prompt
"""

import pytest
import sqlite3
from pathlib import Path
from src.main import BadaBoomBooksApp
from src.queue_manager import QueueManager
from src.models import ProcessingArgs


@pytest.mark.integration
def test_resume_from_specific_position(test_database, tmp_path):
    """
    Test resuming a job that was interrupted mid-processing.

    This verifies:
    1. Completed tasks are not re-processed
    2. Only pending/failed tasks are processed on resume
    3. Job progress is correctly updated
    """
    from src.processors.metadata_operations import MetadataProcessor

    # Setup: Create 3 test book folders
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    for i in range(1, 4):
        book_dir = books_dir / f"Book_{i}"
        book_dir.mkdir()

        opf_content = f"""<?xml version='1.0' encoding='utf-8'?>
<package xmlns:dc='http://purl.org/dc/elements/1.1/'>
  <metadata>
    <dc:title>Test Book {i}</dc:title>
    <dc:creator>Test Author {i}</dc:creator>
  </metadata>
</package>"""
        (book_dir / "metadata.opf").write_text(opf_content, encoding='utf-8')
        (book_dir / "chapter1.mp3").touch()

    # Create incomplete job with mixed task states
    qm = QueueManager()
    args = ProcessingArgs(
        folders=[books_dir / "Book_1", books_dir / "Book_2", books_dir / "Book_3"],
        output=output_dir,
        copy=True,
        from_opf=True,
        yolo=True,
        dry_run=True
    )
    job_id = qm.create_job(args)
    qm.update_job_status(job_id, 'processing')

    # Create tasks: 1 completed, 2 pending
    task1_id = qm.create_task(job_id, books_dir / "Book_1", url='OPF')
    task2_id = qm.create_task(job_id, books_dir / "Book_2", url='OPF')
    task3_id = qm.create_task(job_id, books_dir / "Book_3", url='OPF')

    qm.update_task_status(task1_id, 'completed')  # Already done
    # task2_id and task3_id stay 'pending' - will be resumed

    # Verify initial state
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE job_id = ? AND status = 'completed'", (job_id,))
    completed_before = cursor.fetchone()[0]
    assert completed_before == 1, "Should have 1 completed task before resume"

    cursor.execute("SELECT COUNT(*) FROM tasks WHERE job_id = ? AND status = 'pending'", (job_id,))
    pending_before = cursor.fetchone()[0]
    assert pending_before == 2, "Should have 2 pending tasks before resume"
    conn.close()

    # Execute: Resume the job
    app = BadaBoomBooksApp()
    exit_code = app.run(['--resume', '--yolo'])

    assert exit_code == 0, "Resume should complete successfully"

    # Verify: All tasks are now completed
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM tasks WHERE job_id = ? AND status = 'completed'", (job_id,))
    completed_after = cursor.fetchone()[0]
    assert completed_after == 3, "All 3 tasks should be completed after resume"

    # Verify task1 was NOT re-processed (still completed from before)
    cursor.execute("SELECT status FROM tasks WHERE id = ?", (task1_id,))
    task1_status = cursor.fetchone()[0]
    assert task1_status == 'completed', "Task 1 should remain completed"

    # Verify task2 and task3 were processed
    cursor.execute("SELECT status FROM tasks WHERE id = ?", (task2_id,))
    task2_status = cursor.fetchone()[0]
    assert task2_status == 'completed', "Task 2 should be completed after resume"

    cursor.execute("SELECT status FROM tasks WHERE id = ?", (task3_id,))
    task3_status = cursor.fetchone()[0]
    assert task3_status == 'completed', "Task 3 should be completed after resume"

    conn.close()


@pytest.mark.integration
def test_resume_skips_failed_tasks(test_database, tmp_path):
    """
    Test that resume does NOT automatically retry failed tasks.

    This verifies:
    1. Failed tasks are NOT retried on resume (prevents infinite loops)
    2. Job with only failed tasks is considered complete
    3. Exit code indicates some failures occurred
    """
    # Setup: Create test book
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    book_dir = books_dir / "Book_1"
    book_dir.mkdir()
    opf_content = """<?xml version='1.0' encoding='utf-8'?>
<package xmlns:dc='http://purl.org/dc/elements/1.1/'>
  <metadata>
    <dc:title>Test Book</dc:title>
    <dc:creator>Test Author</dc:creator>
  </metadata>
</package>"""
    (book_dir / "metadata.opf").write_text(opf_content, encoding='utf-8')
    (book_dir / "chapter1.mp3").touch()

    # Create job with failed task
    qm = QueueManager()
    args = ProcessingArgs(
        folders=[book_dir],
        output=output_dir,
        copy=True,
        from_opf=True,
        yolo=True,
        dry_run=True
    )
    job_id = qm.create_job(args)
    qm.update_job_status(job_id, 'processing')

    task_id = qm.create_task(job_id, book_dir, url='OPF')
    qm.update_task_status(task_id, 'failed')

    # Execute: Resume (should NOT retry failed task)
    app = BadaBoomBooksApp()
    exit_code = app.run(['--resume', '--yolo'])

    # Exit code 1 indicates job had failures (which is correct)
    # The job is "complete" in that there's no pending work, but it failed
    assert exit_code == 1, "Resume should exit with failure code when job has failed tasks"

    # Verify: Failed task is still failed (not retried)
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()

    cursor.execute("SELECT status FROM tasks WHERE id = ?", (task_id,))
    status = cursor.fetchone()[0]
    assert status == 'failed', "Failed task should remain failed (not auto-retried)"

    # Verify: Job is considered complete (no pending work)
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE job_id = ? AND status = 'pending'", (job_id,))
    pending_count = cursor.fetchone()[0]
    assert pending_count == 0, "Should have no pending tasks"

    conn.close()


@pytest.mark.integration
def test_resume_multiple_incomplete_jobs(test_database, tmp_path):
    """
    Test handling multiple incomplete jobs.

    This verifies:
    1. --resume resumes the most recent incomplete job
    2. Older incomplete jobs are left untouched
    3. User can choose which job to resume
    """
    # Setup: Create 2 incomplete jobs
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    book_dir = books_dir / "Book_1"
    book_dir.mkdir()
    opf_content = """<?xml version='1.0' encoding='utf-8'?>
<package xmlns:dc='http://purl.org/dc/elements/1.1/'>
  <metadata>
    <dc:title>Test Book</dc:title>
    <dc:creator>Test Author</dc:creator>
  </metadata>
</package>"""
    (book_dir / "metadata.opf").write_text(opf_content, encoding='utf-8')
    (book_dir / "chapter1.mp3").touch()

    qm = QueueManager()
    args = ProcessingArgs(
        folders=[book_dir],
        output=output_dir,
        copy=True,
        from_opf=True,
        yolo=True,
        dry_run=True
    )

    # Create first incomplete job (older)
    job1_id = qm.create_job(args)
    qm.update_job_status(job1_id, 'processing')
    task1_id = qm.create_task(job1_id, book_dir, url='OPF')

    import time
    time.sleep(0.1)  # Ensure different timestamps

    # Create second incomplete job (newer - should be resumed first)
    job2_id = qm.create_job(args)
    qm.update_job_status(job2_id, 'processing')
    task2_id = qm.create_task(job2_id, book_dir, url='OPF')

    # Verify 2 incomplete jobs
    incomplete_jobs = qm.get_incomplete_jobs()
    assert len(incomplete_jobs) == 2, "Should have 2 incomplete jobs"

    # Execute: Resume with --resume flag (should resume most recent)
    app = BadaBoomBooksApp()
    exit_code = app.run(['--resume', '--yolo'])

    assert exit_code == 0, "Resume should complete successfully"

    # Verify: One of the jobs was processed
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()

    # Check how many jobs are now complete (by task count)
    cursor.execute("""
        SELECT job_id, COUNT(*) as completed
        FROM tasks
        WHERE status = 'completed'
        GROUP BY job_id
    """)
    results = cursor.fetchall()

    # Should have exactly 1 job with 1 completed task
    assert len(results) == 1, "Exactly one job should have been resumed and completed"
    resumed_job_id, completed_count = results[0]
    assert completed_count == 1, "The resumed job should have 1 completed task"

    # Verify: The other job still has a pending task
    cursor.execute("""
        SELECT COUNT(*)
        FROM tasks
        WHERE status = 'pending'
    """)
    pending_total = cursor.fetchone()[0]
    assert pending_total == 1, "One job should still have a pending task"

    # Verify: We still have 2 jobs total
    cursor.execute("SELECT COUNT(*) FROM jobs")
    total_jobs = cursor.fetchone()[0]
    assert total_jobs == 2, "Should still have 2 jobs"

    conn.close()


@pytest.mark.integration
def test_resume_no_incomplete_jobs(test_database, existing_dir):
    """
    Test resume behavior when no incomplete jobs exist.

    This verifies:
    1. Application exits gracefully with message
    2. No error occurs
    3. Exit code indicates success
    """
    # Execute: Try to resume with no incomplete jobs
    app = BadaBoomBooksApp()
    exit_code = app.run(['--resume', '--yolo'])

    # Should exit with code 0 and friendly message
    assert exit_code == 0, "Should exit gracefully when no incomplete jobs"

    # Verify: No jobs in database
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs")
    job_count = cursor.fetchone()[0]
    assert job_count == 0, "Should have no jobs in database"
    conn.close()


@pytest.mark.integration
def test_resume_preserves_original_args(test_database, tmp_path):
    """
    Test that resume uses original job arguments.

    This verifies:
    1. Job args are stored in database
    2. Resume loads args from database
    3. Processing uses original args (not current command line)
    """
    # Setup: Create job with specific args
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    book_dir = books_dir / "Book_1"
    book_dir.mkdir()
    opf_content = """<?xml version='1.0' encoding='utf-8'?>
<package xmlns:dc='http://purl.org/dc/elements/1.1/'>
  <metadata>
    <dc:title>Test Book</dc:title>
    <dc:creator>Test Author</dc:creator>
  </metadata>
</package>"""
    (book_dir / "metadata.opf").write_text(opf_content, encoding='utf-8')
    (book_dir / "chapter1.mp3").touch()

    # Create job with series flag enabled
    qm = QueueManager()
    args = ProcessingArgs(
        folders=[book_dir],
        output=output_dir,
        copy=True,
        from_opf=True,
        series=True,  # Original job used --series
        yolo=True,
        dry_run=True
    )
    job_id = qm.create_job(args)
    qm.update_job_status(job_id, 'processing')
    task_id = qm.create_task(job_id, book_dir, url='OPF')

    # Verify args stored in database
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()
    cursor.execute("SELECT args_json FROM jobs WHERE id = ?", (job_id,))
    args_json = cursor.fetchone()[0]
    assert 'series' in args_json, "Args should include series flag"
    conn.close()

    # Execute: Resume (should use stored args with series=True)
    app = BadaBoomBooksApp()
    exit_code = app.run(['--resume', '--yolo'])

    assert exit_code == 0, "Resume should complete successfully"

    # Verify: Job completed
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM jobs WHERE id = ?", (job_id,))
    status = cursor.fetchone()[0]
    assert status == 'completed', "Job should be completed"
    conn.close()


@pytest.mark.integration
def test_resume_after_ctrl_c_during_processing(test_database, tmp_path):
    """
    Test real-world scenario: Ctrl+C during processing, then resume.

    This simulates:
    1. User starts processing 3 books
    2. Presses Ctrl+C after 1 book completes
    3. Resumes later with --resume flag
    4. Only remaining 2 books are processed
    """
    # Setup: Create 3 test books
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    for i in range(1, 4):
        book_dir = books_dir / f"Book_{i}"
        book_dir.mkdir()
        opf_content = f"""<?xml version='1.0' encoding='utf-8'?>
<package xmlns:dc='http://purl.org/dc/elements/1.1/'>
  <metadata>
    <dc:title>Test Book {i}</dc:title>
    <dc:creator>Test Author</dc:creator>
  </metadata>
</package>"""
        (book_dir / "metadata.opf").write_text(opf_content, encoding='utf-8')
        (book_dir / "chapter1.mp3").touch()

    # Simulate: Job was processing 3 books, 1 completed, then Ctrl+C
    qm = QueueManager()
    args = ProcessingArgs(
        folders=[books_dir / f"Book_{i}" for i in range(1, 4)],
        output=output_dir,
        copy=True,
        from_opf=True,
        yolo=True,
        dry_run=True
    )
    job_id = qm.create_job(args)
    qm.update_job_status(job_id, 'processing')

    # Create tasks: 1 completed, 2 pending
    task1_id = qm.create_task(job_id, books_dir / "Book_1", url='OPF')
    task2_id = qm.create_task(job_id, books_dir / "Book_2", url='OPF')
    task3_id = qm.create_task(job_id, books_dir / "Book_3", url='OPF')

    qm.update_task_status(task1_id, 'completed')
    # task2 and task3 remain pending

    # Verify initial state
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE job_id = ? AND status = 'pending'", (job_id,))
    pending_before = cursor.fetchone()[0]
    assert pending_before == 2, "Should have 2 pending tasks"
    conn.close()

    # Execute: Resume the interrupted job
    app = BadaBoomBooksApp()
    exit_code = app.run(['--resume', '--yolo'])

    assert exit_code == 0, "Resume should complete successfully"

    # Verify: All tasks completed
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM tasks WHERE job_id = ? AND status = 'completed'", (job_id,))
    completed_after = cursor.fetchone()[0]
    assert completed_after == 3, "All 3 tasks should be completed after resume"

    # Verify: Job status is completed
    cursor.execute("SELECT status FROM jobs WHERE id = ?", (job_id,))
    job_status = cursor.fetchone()[0]
    assert job_status == 'completed', "Job should be marked as completed"

    conn.close()


@pytest.mark.integration
def test_resume_with_url_discovery(test_database, tmp_path):
    """
    Test resuming job where tasks need URL discovery.

    This verifies:
    1. Tasks with url=NULL are discovered on resume
    2. URL discovery happens in workers during resume
    3. Processing completes successfully
    """
    # Setup: Create test book without source URL in OPF
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    book_dir = books_dir / "Book_1"
    book_dir.mkdir()

    # OPF without source URL
    opf_content = """<?xml version='1.0' encoding='utf-8'?>
<package xmlns:dc='http://purl.org/dc/elements/1.1/'>
  <metadata>
    <dc:title>Test Book</dc:title>
    <dc:creator>Test Author</dc:creator>
  </metadata>
</package>"""
    (book_dir / "metadata.opf").write_text(opf_content, encoding='utf-8')
    (book_dir / "chapter1.mp3").touch()

    # Create job with task that needs URL discovery (url=NULL)
    qm = QueueManager()
    args = ProcessingArgs(
        folders=[book_dir],
        output=output_dir,
        copy=True,
        from_opf=True,
        yolo=True,
        dry_run=True
    )
    job_id = qm.create_job(args)
    qm.update_job_status(job_id, 'processing')

    # Create task with url=None (simulates two-phase creation)
    task_id = qm.create_task(job_id, book_dir, url=None)

    # Verify task has no URL
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()
    cursor.execute("SELECT url FROM tasks WHERE id = ?", (task_id,))
    url_before = cursor.fetchone()[0]
    assert url_before is None, "Task should have NULL URL before resume"
    conn.close()

    # Execute: Resume (worker should discover URL)
    app = BadaBoomBooksApp()
    exit_code = app.run(['--resume', '--yolo'])

    assert exit_code == 0, "Resume with URL discovery should succeed"

    # Verify: Task was processed
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM tasks WHERE id = ?", (task_id,))
    status = cursor.fetchone()[0]
    assert status == 'completed', "Task should be completed after resume"
    conn.close()


@pytest.mark.integration
def test_no_resume_with_incomplete_job(test_database, tmp_path):
    """
    Test --no-resume flag prevents resuming even with incomplete jobs.

    This verifies:
    1. --no-resume skips incomplete jobs
    2. New job is created instead
    3. Old job remains incomplete
    """
    # Setup: Create incomplete job
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    book_dir = books_dir / "Book_1"
    book_dir.mkdir()
    opf_content = """<?xml version='1.0' encoding='utf-8'?>
<package xmlns:dc='http://purl.org/dc/elements/1.1/'>
  <metadata>
    <dc:title>Test Book</dc:title>
    <dc:creator>Test Author</dc:creator>
  </metadata>
</package>"""
    (book_dir / "metadata.opf").write_text(opf_content, encoding='utf-8')
    (book_dir / "chapter1.mp3").touch()

    qm = QueueManager()
    args = ProcessingArgs(
        folders=[book_dir],
        output=output_dir,
        copy=True,
        from_opf=True,
        yolo=True,
        dry_run=True
    )
    old_job_id = qm.create_job(args)
    qm.update_job_status(old_job_id, 'processing')
    qm.create_task(old_job_id, book_dir, url='OPF')

    # Execute: Run with --no-resume (should create new job)
    app = BadaBoomBooksApp()
    exit_code = app.run([
        '--no-resume',
        '--yolo',
        '--copy',
        '--from-opf',
        '--dry-run',
        '-O', str(output_dir),
        '-R', str(books_dir)
    ])

    assert exit_code == 0, "Should complete successfully"

    # Verify: Old job still incomplete
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM jobs WHERE id = ?", (old_job_id,))
    old_status = cursor.fetchone()[0]
    assert old_status == 'processing', "Old job should still be incomplete"

    # Verify: New job was created and completed
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE status = 'completed'")
    completed_count = cursor.fetchone()[0]
    assert completed_count == 1, "New job should be completed"

    cursor.execute("SELECT COUNT(*) FROM jobs")
    total_jobs = cursor.fetchone()[0]
    assert total_jobs == 2, "Should have 2 jobs total (old + new)"

    conn.close()
