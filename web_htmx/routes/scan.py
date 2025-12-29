"""
Scan Planning Routes

Handles form submission, validation, and job creation for audiobook scanning.
"""

import threading
import json
from pathlib import Path
from typing import List, Dict

from flask import Blueprint, request, jsonify, render_template, session

# Import from src
from src.models import ProcessingArgs
from src.queue_manager import QueueManager
from src.main import BadaBoomBooksApp

bp = Blueprint('scan', __name__, url_prefix='/scan')

# Initialize QueueManager
queue_manager = QueueManager()


@bp.route('/validate', methods=['POST'])
def validate_form():
    """
    Validate scan planning form before submission.

    JSON body: Form data

    Returns:
        JSON with validation result:
        {
            "valid": bool,
            "errors": List[str]
        }
    """
    try:
        data = request.json
        errors = []

        # Check selected folders
        selected_folders = session.get('selected_folders', [])
        if not selected_folders:
            errors.append("Please select at least one audiobook folder")

        # Validate force_refresh dependencies
        if data.get('force_refresh'):
            if not data.get('opf'):
                errors.append("Force Refresh requires OPF to be enabled")
            if not data.get('from_opf'):
                errors.append("Force Refresh requires From OPF to be enabled")

        # Validate LLM select (check cache without testing)
        if data.get('llm_select'):
            from state.cache import llm_cache
            cache_info = llm_cache.get_cache_info()
            if cache_info['has_cache']:
                cached_result = cache_info['cached_result']
                if not cached_result.get('available'):
                    errors.append("LLM is not available. Please test connection or disable LLM Select")

        # Validate numeric inputs
        try:
            search_limit = int(data.get('search_limit', 5))
            if search_limit < 1 or search_limit > 20:
                errors.append("Search Limit must be between 1 and 20")
        except (ValueError, TypeError):
            errors.append("Search Limit must be a valid number")

        try:
            download_limit = int(data.get('download_limit', 3))
            if download_limit < 1 or download_limit > 10:
                errors.append("Download Limit must be between 1 and 10")
        except (ValueError, TypeError):
            errors.append("Download Limit must be a valid number")

        try:
            search_delay = float(data.get('search_delay', 2.0))
            if search_delay < 0:
                errors.append("Search Delay cannot be negative")
        except (ValueError, TypeError):
            errors.append("Search Delay must be a valid number")

        return jsonify({
            'valid': len(errors) == 0,
            'errors': errors
        })

    except Exception as e:
        return jsonify({
            'valid': False,
            'errors': [f'Validation error: {str(e)}']
        }), 500


@bp.route('/start', methods=['POST'])
def start_scan():
    """
    Start audiobook scanning job.

    JSON body: Form data

    Returns:
        JSON with job_id:
        {
            "success": bool,
            "job_id": str,
            "total_tasks": int
        }
    """
    try:
        data = request.json
        selected_folders = session.get('selected_folders', [])

        if not selected_folders:
            return jsonify({
                'success': False,
                'error': 'No folders selected'
            }), 400

        # Convert form data to ProcessingArgs
        processing_args = form_to_processing_args(data, selected_folders)

        # Validate args
        errors = processing_args.validate()
        if errors:
            return jsonify({
                'success': False,
                'errors': errors
            }), 400

        # Create job in database
        user_id = session.get('user_id', 'web_user')
        job_id = queue_manager.create_job(processing_args, user_id=user_id)

        # Create tasks (one per folder)
        for folder in selected_folders:
            queue_manager.create_task(job_id, Path(folder), url=None)

        # Start background processing
        thread = threading.Thread(
            target=process_in_background,
            args=(job_id, processing_args.workers),
            daemon=True
        )
        thread.start()

        # Clear selected folders
        session['selected_folders'] = []
        session.modified = True

        return jsonify({
            'success': True,
            'job_id': job_id,
            'total_tasks': len(selected_folders)
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to start scan: {str(e)}'
        }), 500


def form_to_processing_args(form_data: Dict, selected_folders: List[str]) -> ProcessingArgs:
    """
    Convert form data to ProcessingArgs dataclass.

    Args:
        form_data: Form data dict
        selected_folders: List of selected folder paths

    Returns:
        ProcessingArgs instance
    """
    return ProcessingArgs(
        folders=[Path(f) for f in selected_folders],

        # Always enforced
        auto_search=True,
        yolo=True,
        no_resume=True,

        # User-configurable flags
        dry_run=form_data.get('dry_run', False),
        from_opf=form_data.get('from_opf', True),
        flatten=form_data.get('flatten', False),
        rename=form_data.get('rename', False),
        opf=form_data.get('opf', False),
        infotxt=form_data.get('infotxt', False),
        id3_tag=form_data.get('id3_tag', False),
        series=form_data.get('series', False),
        cover=form_data.get('cover', False),
        force_refresh=form_data.get('force_refresh', False),
        llm_select=form_data.get('llm_select', False),

        # Action modifiers
        copy=form_data.get('copy', False),
        move=form_data.get('move', False),

        # Output directory
        output=Path(form_data.get('output_dir')) if form_data.get('output_dir') and form_data.get('output_dir').strip() else None,

        # Numeric inputs
        search_limit=int(form_data.get('search_limit', 5)),
        download_limit=int(form_data.get('download_limit', 3)),
        search_delay=float(form_data.get('search_delay', 2.0)),
        workers=int(form_data.get('workers', 4)),

        # Debug flag
        debug=form_data.get('debug', False)
    )


def process_in_background(job_id: str, num_workers: int = 4):
    """
    Process audiobook job in background using parallel workers.

    Args:
        job_id: Job UUID
        num_workers: Number of parallel workers
    """
    try:
        # Enqueue all tasks for this job
        queue_manager.enqueue_all_tasks(job_id)

        # Start workers (this will block until all tasks complete)
        app = BadaBoomBooksApp()
        app._start_workers(num_workers=num_workers)

    except Exception as e:
        # Update job as failed
        queue_manager.update_job_status(job_id, 'failed', error=str(e))
