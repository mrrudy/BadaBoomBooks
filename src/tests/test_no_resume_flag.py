"""
Tests for --no-resume flag behavior.

This module verifies that the --no-resume flag correctly prevents
resume prompts and starts fresh jobs.
"""

import pytest
from pathlib import Path
from src.main import BadaBoomBooksApp


@pytest.mark.integration
def test_no_resume_skips_resume_prompt(existing_dir, expected_dir, test_database):
    """
    Test that --no-resume skips resume prompt even with incomplete jobs.

    This test:
    1. Creates an incomplete job in the database
    2. Runs app with --no-resume --yolo
    3. Verifies it starts a fresh job without prompting
    """
    from src.queue_manager import QueueManager
    from src.models import ProcessingArgs
    import sqlite3

    # Setup: Create an incomplete job
    qm = QueueManager()
    dummy_args = ProcessingArgs(
        folders=[existing_dir],
        yolo=True,
        dry_run=True
    )
    job_id = qm.create_job(dummy_args)
    qm.update_job_status(job_id, 'processing')  # Leave it incomplete

    # Verify incomplete job exists
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE status = 'processing'")
    incomplete_count_before = cursor.fetchone()[0]
    conn.close()

    assert incomplete_count_before == 1, "Should have 1 incomplete job"

    # Execute: Run app with --no-resume --yolo
    app = BadaBoomBooksApp()
    exit_code = app.run([
        '--no-resume',
        '--yolo',
        '--dry-run',
        '--from-opf',
        '-R', str(existing_dir)
    ])

    # Verify: App completed successfully
    assert exit_code == 0, "App should complete successfully"

    # Verify: New job was created (not resumed)
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs")
    total_jobs = cursor.fetchone()[0]
    conn.close()

    assert total_jobs == 2, "Should have 2 jobs total (old incomplete + new fresh)"


@pytest.mark.integration
def test_no_resume_overrides_resume_flag(existing_dir, expected_dir, test_database):
    """
    Test that --no-resume overrides --resume flag.

    When both flags are specified, --no-resume should win and start fresh.
    """
    from src.queue_manager import QueueManager
    from src.models import ProcessingArgs
    import sqlite3

    # Setup: Create an incomplete job
    qm = QueueManager()
    dummy_args = ProcessingArgs(
        folders=[existing_dir],
        yolo=True,
        dry_run=True
    )
    job_id = qm.create_job(dummy_args)
    qm.update_job_status(job_id, 'processing')

    # Execute: Run app with conflicting flags
    app = BadaBoomBooksApp()
    exit_code = app.run([
        '--resume',
        '--no-resume',
        '--yolo',
        '--dry-run',
        '--from-opf',
        '-R', str(existing_dir)
    ])

    # Verify: App completed successfully
    assert exit_code == 0, "App should complete successfully"

    # Verify: New job was created (not resumed)
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs")
    total_jobs = cursor.fetchone()[0]
    conn.close()

    assert total_jobs == 2, "Should have 2 jobs (no-resume overrides resume)"


@pytest.mark.integration
def test_yolo_without_no_resume_behavior(existing_dir, expected_dir, test_database):
    """
    Test that --yolo alone skips resume prompt (existing behavior).

    This verifies backward compatibility - --yolo always skipped resume prompts.
    """
    from src.queue_manager import QueueManager
    from src.models import ProcessingArgs
    import sqlite3

    # Setup: Create an incomplete job
    qm = QueueManager()
    dummy_args = ProcessingArgs(
        folders=[existing_dir],
        yolo=True,
        dry_run=True
    )
    job_id = qm.create_job(dummy_args)
    qm.update_job_status(job_id, 'processing')

    # Execute: Run app with --yolo only
    app = BadaBoomBooksApp()
    exit_code = app.run([
        '--yolo',
        '--dry-run',
        '--from-opf',
        '-R', str(existing_dir)
    ])

    # Verify: App completed successfully
    assert exit_code == 0, "App should complete successfully"

    # Verify: New job was created (yolo skips resume)
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs")
    total_jobs = cursor.fetchone()[0]
    conn.close()

    assert total_jobs == 2, "Should have 2 jobs (yolo skips resume)"


@pytest.mark.integration
def test_no_resume_allows_fresh_automated_runs(existing_dir, expected_dir, test_database):
    """
    Test real-world scenario: automated cron job that always starts fresh.

    Use case:
    - Cron job runs daily: --auto-search --yolo --no-resume --opf --id3-tag
    - Should never prompt for resume
    - Should always start fresh processing
    """
    from src.queue_manager import QueueManager
    from src.models import ProcessingArgs
    import sqlite3

    # Setup: Create multiple incomplete jobs (simulating previous failed runs)
    qm = QueueManager()
    for i in range(3):
        dummy_args = ProcessingArgs(
            folders=[existing_dir],
            yolo=True,
            dry_run=True
        )
        job_id = qm.create_job(dummy_args)
        qm.update_job_status(job_id, 'processing')

    # Verify 3 incomplete jobs exist
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE status = 'processing'")
    incomplete_before = cursor.fetchone()[0]
    conn.close()

    assert incomplete_before == 3, "Should have 3 incomplete jobs"

    # Execute: Automated run with --no-resume --yolo
    app = BadaBoomBooksApp()
    exit_code = app.run([
        '--no-resume',
        '--yolo',
        '--dry-run',
        '--from-opf',
        '-R', str(existing_dir)
    ])

    # Verify: App completed successfully
    assert exit_code == 0, "Automated run should complete successfully"

    # Verify: New fresh job was created
    conn = sqlite3.connect(str(test_database))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs")
    total_jobs = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM jobs WHERE status = 'completed'")
    completed_jobs = cursor.fetchone()[0]

    conn.close()

    assert total_jobs == 4, "Should have 4 jobs total (3 old + 1 new)"
    assert completed_jobs == 1, "New job should be completed"
