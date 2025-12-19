"""
Task Management Routes

Provides endpoints for viewing and managing processing tasks.
"""

from flask import Blueprint, request, render_template, session, jsonify

from src.queue_manager import QueueManager

bp = Blueprint('tasks', __name__, url_prefix='/tasks')

# Initialize QueueManager
queue_manager = QueueManager()


@bp.route('/current', methods=['GET'])
def current_tasks():
    """
    Get current (pending/running) tasks for active jobs.

    Query params:
        job_id: Optional job ID to filter by

    Returns:
        HTML partial with current tasks
    """
    try:
        job_id = request.args.get('job_id')
        user_id = session.get('user_id')

        if job_id:
            # Get tasks for specific job
            tasks = queue_manager.get_tasks_for_job(job_id, status=['pending', 'running'])
            progress = queue_manager.get_job_progress(job_id)
            job = queue_manager.get_job(job_id)
        else:
            # Get all active tasks for user (return empty if no user_id)
            if not user_id:
                tasks = []
                progress = None
                job = None
            else:
                jobs = queue_manager.get_jobs_for_user(user_id, status=['pending', 'planning', 'processing'])
                tasks = []
                for job in jobs:
                    job_tasks = queue_manager.get_tasks_for_job(job['id'], status=['pending', 'running'])
                    tasks.extend(job_tasks)

                progress = None
                job = None

        return render_template('partials/section3_current_tasks.html',
                              tasks=tasks,
                              progress=progress,
                              job=job)
    except Exception as e:
        # Log the error and return empty state
        import traceback
        print(f"ERROR in current_tasks: {e}")
        print(traceback.format_exc())
        return render_template('partials/section3_current_tasks.html',
                              tasks=[],
                              progress=None,
                              job=None)


@bp.route('/failed', methods=['GET'])
def failed_tasks():
    """
    Get failed tasks for user.

    Returns:
        HTML partial with failed tasks
    """
    try:
        user_id = session.get('user_id')

        # Return empty if no user_id
        if not user_id:
            failed = []
        else:
            # Get all jobs for user
            all_jobs = queue_manager.get_jobs_for_user(user_id)

            # Get failed tasks from all jobs
            failed = []
            for job in all_jobs:
                job_tasks = queue_manager.get_tasks_for_job(job['id'], status=['failed'])
                failed.extend(job_tasks)

        return render_template('partials/section3_failed_tasks.html',
                              tasks=failed)
    except Exception as e:
        # Log the error and return empty state
        import traceback
        print(f"ERROR in failed_tasks: {e}")
        print(traceback.format_exc())
        return render_template('partials/section3_failed_tasks.html',
                              tasks=[])


@bp.route('/completed', methods=['GET'])
def completed_tasks():
    """
    Get completed tasks for user with pagination.

    Query params:
        page: Page number (default 1)
        per_page: Items per page (default 20)

    Returns:
        HTML partial with completed tasks
    """
    try:
        user_id = session.get('user_id')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))

        # Return empty if no user_id
        if not user_id:
            completed = []
        else:
            # Get all jobs for user
            all_jobs = queue_manager.get_jobs_for_user(user_id)

            # Get completed tasks from all jobs
            completed = []
            for job in all_jobs:
                job_tasks = queue_manager.get_tasks_for_job(job['id'], status=['completed'])
                completed.extend(job_tasks)

            # Sort by completion time (newest first)
            completed.sort(key=lambda t: t.get('completed_at', ''), reverse=True)

        # Paginate
        total = len(completed)
        start = (page - 1) * per_page
        end = start + per_page
        paginated = completed[start:end]

        total_pages = (total + per_page - 1) // per_page

        return render_template('partials/section3_completed_tasks.html',
                              tasks=paginated,
                              page=page,
                              per_page=per_page,
                              total=total,
                              total_pages=total_pages)
    except Exception as e:
        # Log the error and return empty state
        import traceback
        print(f"ERROR in completed_tasks: {e}")
        print(traceback.format_exc())
        return render_template('partials/section3_completed_tasks.html',
                              tasks=[],
                              page=1,
                              per_page=20,
                              total=0,
                              total_pages=0)


@bp.route('/<task_id>/retry', methods=['POST'])
def retry_task():
    """
    Retry a failed task by populating the form with its folder.

    Path params:
        task_id: Task UUID

    Returns:
        JSON with task folder path
    """
    task_id = request.args.get('task_id')
    task = queue_manager.get_task(task_id)

    if not task:
        return jsonify({'error': 'Task not found'}), 404

    folder_path = task.get('folder_path')

    return jsonify({
        'success': True,
        'folder_path': folder_path
    })


@bp.route('/job/<job_id>', methods=['GET'])
def job_details():
    """
    Get detailed information about a specific job.

    Path params:
        job_id: Job UUID

    Returns:
        JSON with job details and tasks
    """
    job_id = request.args.get('job_id')
    job = queue_manager.get_job(job_id)

    if not job:
        return jsonify({'error': 'Job not found'}), 404

    # Get all tasks for job
    all_tasks = queue_manager.get_tasks_for_job(job_id)

    # Get progress
    progress = queue_manager.get_job_progress(job_id)

    return jsonify({
        'job': job,
        'tasks': all_tasks,
        'progress': progress
    })


@bp.route('/cancel/<job_id>', methods=['POST'])
def cancel_job():
    """
    Cancel a running job.

    Path params:
        job_id: Job UUID

    Returns:
        JSON confirmation
    """
    job_id = request.args.get('job_id')
    job = queue_manager.get_job(job_id)

    if not job:
        return jsonify({'error': 'Job not found'}), 404

    # Update job status to cancelled
    queue_manager.update_job_status(job_id, 'cancelled')

    # Cancel pending tasks
    pending_tasks = queue_manager.get_tasks_for_job(job_id, status=['pending'])
    for task in pending_tasks:
        queue_manager.update_task_status(task['id'], 'cancelled')

    return jsonify({
        'success': True,
        'message': f'Job {job_id} cancelled'
    })
