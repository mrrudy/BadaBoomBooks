"""
Test database isolation for tests.

This module verifies that tests use isolated databases and don't
interfere with production operations.
"""

import pytest
import os
from pathlib import Path


def test_database_isolation_via_env(test_database):
    """
    Test that test_database fixture sets environment variable correctly.

    Verifies:
    1. BADABOOMBOOKS_DB_PATH environment variable is set
    2. Points to temporary test database
    3. Is NOT the production database
    """
    from src.config import root_path

    # Get environment variable
    db_path = os.environ.get('BADABOOMBOOKS_DB_PATH')

    assert db_path is not None, "BADABOOMBOOKS_DB_PATH not set"

    # Verify it's NOT the production database
    production_db = root_path / 'badaboombooksqueue.db'
    assert db_path != str(production_db), \
        f"Test database should not be production DB: {db_path}"

    # Verify it's the test database
    assert db_path == str(test_database), \
        f"Environment variable should match test_database fixture: {db_path} != {test_database}"


def test_queue_manager_uses_test_database(test_database):
    """
    Test that QueueManager respects the test database environment variable.

    Verifies:
    1. QueueManager uses test database when BADABOOMBOOKS_DB_PATH is set
    2. Does NOT use production database
    """
    from src.queue_manager import QueueManager
    from src.config import root_path

    # Create QueueManager (should use test database)
    qm = QueueManager()

    # Verify it's using test database
    production_db = root_path / 'badaboombooksqueue.db'

    assert qm.db_path != production_db, \
        f"QueueManager should not use production DB: {qm.db_path}"

    assert qm.db_path == test_database, \
        f"QueueManager should use test database: {qm.db_path} != {test_database}"


def test_huey_uses_test_database(test_database):
    """
    Test that Huey instance uses test database environment variable.

    Verifies:
    1. Huey's database path is NOT production
    2. Huey uses isolated test database
    """
    from src.queue_manager import huey, _get_database_path
    from src.config import root_path

    # Get current database path
    current_db = _get_database_path()

    # Verify NOT production
    production_db = root_path / 'badaboombooksqueue.db'
    assert current_db != production_db, \
        f"Huey should not use production DB: {current_db}"

    # Verify using test database
    assert current_db == test_database, \
        f"Huey should use test database: {current_db} != {test_database}"


@pytest.mark.integration
def test_test_runs_dont_pollute_production_db(test_database, existing_dir, expected_dir):
    """
    Integration test verifying tests don't affect production database.

    This test:
    1. Runs a simple operation that would create a job
    2. Verifies job was created in test database
    3. Verifies production database was NOT touched
    """
    from src.main import BadaBoomBooksApp
    from src.config import root_path
    import sqlite3

    production_db = root_path / 'badaboombooksqueue.db'

    # Get initial production DB state (if it exists)
    production_job_count_before = None
    if production_db.exists():
        conn = sqlite3.connect(str(production_db))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM jobs")
        production_job_count_before = cursor.fetchone()[0]
        conn.close()

    # Run app with test database
    app = BadaBoomBooksApp()
    exit_code = app.run([
        '--copy',
        '--rename',
        '--from-opf',
        '--yolo',
        '-O', str(expected_dir),
        '-R', str(existing_dir)
    ])

    assert exit_code == 0, "App should complete successfully"

    # Verify test database was used
    test_conn = sqlite3.connect(str(test_database))
    test_cursor = test_conn.cursor()
    test_cursor.execute("SELECT COUNT(*) FROM jobs")
    test_job_count = test_cursor.fetchone()[0]
    test_conn.close()

    assert test_job_count > 0, "Test database should have jobs"

    # Verify production database was NOT affected
    if production_db.exists() and production_job_count_before is not None:
        conn = sqlite3.connect(str(production_db))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM jobs")
        production_job_count_after = cursor.fetchone()[0]
        conn.close()

        assert production_job_count_after == production_job_count_before, \
            f"Production database should NOT be modified by tests: " \
            f"before={production_job_count_before}, after={production_job_count_after}"
