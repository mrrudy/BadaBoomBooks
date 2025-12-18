#!/usr/bin/env python3
"""
Quick diagnostic script to check queue status.
"""
import sys
import sqlite3

sys.stdout.reconfigure(encoding='utf-8')

db_path = "badaboombooksqueue.db"

try:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get all jobs
    cursor.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT 5")
    jobs = cursor.fetchall()

    print("=" * 80)
    print("RECENT JOBS")
    print("=" * 80)

    for job in jobs:
        job_id = job['id']
        print(f"\nJob ID: {job_id[:8]}...")
        print(f"  Status: {job['status']}")
        print(f"  Created: {job['created_at']}")
        print(f"  Started: {job['started_at']}")
        print(f"  Completed: {job['completed_at']}")

        # Get task statistics for this job
        cursor.execute("""
            SELECT
                status,
                COUNT(*) as count
            FROM tasks
            WHERE job_id = ?
            GROUP BY status
        """, (job_id,))

        task_stats = cursor.fetchall()

        print(f"  Tasks:")
        for stat in task_stats:
            print(f"    {stat['status']}: {stat['count']}")

        # Show some sample tasks
        cursor.execute("""
            SELECT id, folder_path, url, status, enqueued_at
            FROM tasks
            WHERE job_id = ?
            ORDER BY created_at
            LIMIT 5
        """, (job_id,))

        sample_tasks = cursor.fetchall()
        print(f"  Sample tasks (first 5):")
        for task in sample_tasks:
            from pathlib import Path
            folder_name = Path(task['folder_path']).name
            enqueued = "✓" if task['enqueued_at'] else "✗"
            print(f"    [{task['status']}] {folder_name[:40]} (enqueued: {enqueued})")

    conn.close()

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
