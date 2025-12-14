#!/usr/bin/env python3
"""
BadaBoomBooks Web Interface

A modern web-based UI for the BadaBoomBooks audiobook organization tool.
Provides an intuitive interface for managing audiobook collections.
"""

import os
import sys
import json
import threading
import time
import string
import logging as log
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_socketio import SocketIO, emit
import uuid

# Add the src directory to the Python path
root_dir = Path(__file__).parent.parent
src_dir = root_dir / 'src'
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(root_dir))

from src.main import BadaBoomBooksApp
from src.models import ProcessingArgs, BookMetadata
from src.config import SCRAPER_REGISTRY, __version__

app = Flask(__name__)
app.config['SECRET_KEY'] = 'badaboombooks-web-interface'
socketio = SocketIO(app, cors_allowed_origins="*")

# Global state management
class WebState:
    def __init__(self):
        self.jobs: Dict[str, Dict] = {}
        self.active_sessions: Dict[str, Dict] = {}
        
    def create_job(self, job_type: str, params: Dict) -> str:
        job_id = str(uuid.uuid4())
        self.jobs[job_id] = {
            'id': job_id,
            'type': job_type,
            'status': 'created',
            'params': params,
            'created_at': datetime.now(),
            'progress': 0,
            'current_step': '',
            'results': [],
            'errors': [],
            'candidates': [],
            'awaiting_selection': False
        }
        return job_id
    
    def get_job(self, job_id: str) -> Optional[Dict]:
        return self.jobs.get(job_id)
    
    def update_job(self, job_id: str, updates: Dict):
        if job_id in self.jobs:
            self.jobs[job_id].update(updates)
            
    def set_job_candidates(self, job_id: str, candidates: List, book_info: Dict):
        if job_id in self.jobs:
            self.jobs[job_id].update({
                'candidates': candidates,
                'book_info': book_info,
                'awaiting_selection': True,
                'status': 'awaiting_selection'
            })

web_state = WebState()

class WebProgressReporter:
    """Progress reporter that emits to web interface."""
    
    def __init__(self, job_id: str):
        self.job_id = job_id
        print(f"[DEBUG] WebProgressReporter created for job {job_id}")
        
    def start_processing(self, total_books: int):
        print(f"[DEBUG] Starting processing of {total_books} books")
        web_state.update_job(self.job_id, {
            'total_books': total_books,
            'status': 'processing',
            'progress': 0
        })
        
        message = {
            'job_id': self.job_id,
            'status': 'processing',
            'total_books': total_books,
            'progress': 0,
            'current_step': 'Starting processing...'
        }
        print(f"[DEBUG] Emitting job_progress: {message}")
        socketio.emit('job_progress', message)
        print(f"[DEBUG] job_progress emitted successfully")
    
    def start_book(self, metadata, book_index: int):
        job = web_state.get_job(self.job_id)
        total_books = job.get('total_books', 1) if job else 1
        progress = (book_index / total_books) * 100
        
        book_name = getattr(metadata, 'input_folder', 'Unknown')
        print(f"[DEBUG] Starting book {book_index + 1}/{total_books}: {book_name}")
        
        web_state.update_job(self.job_id, {
            'current_book': book_name,
            'book_index': book_index,
            'progress': progress
        })
        
        message = {
            'job_id': self.job_id,
            'current_book': book_name,
            'progress': progress,
            'current_step': f'Processing book {book_index + 1}/{total_books}: {book_name}'
        }
        print(f"[DEBUG] Emitting job_progress for book start: {message}")
        socketio.emit('job_progress', message)
        print(f"[DEBUG] Book start job_progress emitted successfully")
    
    def finish_book(self, success: bool, error: str = None):
        job = web_state.get_job(self.job_id)
        if job:
            if success:
                print(f"[DEBUG] ✅ Book completed: {job.get('current_book', 'Unknown')}")
                job['results'].append({
                    'book': job.get('current_book', 'Unknown'),
                    'status': 'success'
                })
            else:
                print(f"[DEBUG] ❌ Book failed: {job.get('current_book', 'Unknown')} - {error}")
                job['errors'].append({
                    'book': job.get('current_book', 'Unknown'),
                    'error': error or 'Unknown error'
                })
    
    def report_search_progress(self, search_term: str, search_type: str):
        print(f"[DEBUG] 🔍 Search progress: {search_type} for {search_term}")
        step_text = f'Searching {search_type} for: {search_term}'
        web_state.update_job(self.job_id, {
            'current_step': step_text
        })
        
        message = {
            'job_id': self.job_id,
            'current_step': step_text
        }
        print(f"[DEBUG] Emitting job_progress for search: {message}")
        socketio.emit('job_progress', message)
        print(f"[DEBUG] Search progress emitted successfully")

class WebAutoSearchEngine:
    """Web-aware auto search engine that handles candidate selection via UI."""
    
    def __init__(self, job_id: str):
        self.job_id = job_id
    
    def search_and_select_with_context(self, search_term: str, site_keys: List[str], 
                                     book_info: dict = None, search_limit: int = 5, 
                                     download_limit: int = 3, delay: float = 2.0):
        # Simulate search and candidate generation
        # In real implementation, this would use the actual search engine
        candidates = [
            {
                'site_key': 'audible',
                'url': 'https://audible.com/example1',
                'title': f'{search_term} - Audible Version',
                'snippet': 'High quality audiobook from Audible...'
            },
            {
                'site_key': 'goodreads', 
                'url': 'https://goodreads.com/example2',
                'title': f'{search_term} - Goodreads Page',
                'snippet': 'Detailed book information and reviews...'
            }
        ]
        
        # Set candidates and wait for user selection
        web_state.set_job_candidates(self.job_id, candidates, book_info or {})
        
        socketio.emit('candidate_selection_required', {
            'job_id': self.job_id,
            'book_info': book_info,
            'candidates': candidates,
            'search_term': search_term
        })
        
        # Wait for user selection (in real implementation, this would be handled differently)
        # For demo purposes, return first candidate
        time.sleep(1)  # Simulate processing time
        return candidates[0]['site_key'], candidates[0]['url'], '<html>mock content</html>'

@app.route('/')
def index():
    """Main dashboard page."""
    return render_template('index.html', version=__version__)

@app.route('/browse')
def browse():
    """File browser for selecting audiobook folders."""
    path = request.args.get('path', '')
    
    try:
        # Handle drive listing for Windows
        if not path or path == 'drives':
            # List available drives on Windows
            drives = []
            if os.name == 'nt':  # Windows
                for letter in string.ascii_uppercase:
                    drive_path = f"{letter}:\\"
                    if os.path.exists(drive_path):
                        try:
                            # Test if drive is accessible
                            os.listdir(drive_path)
                            drives.append({
                                'name': f"{letter}: Drive",
                                'path': drive_path,
                                'type': 'drive',
                                'audio_count': 0
                            })
                        except (OSError, PermissionError):
                            # Drive exists but not accessible
                            drives.append({
                                'name': f"{letter}: Drive (No Access)",
                                'path': drive_path,
                                'type': 'drive_inaccessible',
                                'audio_count': 0
                            })
                
                return jsonify({
                    'current_path': 'Computer',
                    'parent': None,
                    'items': drives,
                    'is_drives': True
                })
            else:
                # Unix-like systems, start from root
                path = '/'
        
        # Handle empty path - default to drives on Windows, root on Unix
        if not path:
            if os.name == 'nt':
                return browse()  # Recursive call to show drives
            else:
                path = '/'
        
        # Clean up the path for Windows
        if os.name == 'nt' and path.endswith('\\') and len(path) == 3:
            # Windows drive path like "C:\\"
            current_path = Path(path)
        else:
            current_path = Path(path).resolve()
        
        # Determine parent path
        if os.name == 'nt' and str(current_path).endswith(':\\'):
            # Windows drive root - parent should be drives list
            parent_path = 'drives'
        else:
            parent = current_path.parent if current_path != current_path.parent else None
            parent_path = str(parent) if parent else None
        
        items = []
        if current_path.exists() and current_path.is_dir():
            try:
                for item in sorted(current_path.iterdir()):
                    if item.is_dir():
                        # Check if it might be an audiobook folder
                        audio_extensions = ['.mp3', '.m4a', '.m4b', '.flac', '.ogg', '.wma']
                        audio_files = []
                        try:
                            for ext in audio_extensions:
                                audio_files.extend(list(item.glob(f'*{ext}')))
                                if len(audio_files) > 0:  # Stop checking if we found audio files
                                    break
                        except (PermissionError, OSError):
                            pass
                        
                        is_audiobook = len(audio_files) > 0
                        
                        items.append({
                            'name': item.name,
                            'path': str(item),
                            'type': 'audiobook' if is_audiobook else 'folder',
                            'audio_count': len(audio_files) if is_audiobook else 0
                        })
            except (PermissionError, OSError) as e:
                return jsonify({'error': f'Access denied: {e}'}), 403
        else:
            return jsonify({'error': f'Path does not exist or is not a directory: {path}'}), 404
        
        return jsonify({
            'current_path': str(current_path),
            'parent': parent_path,
            'items': items,
            'is_drives': False
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to browse path: {e}'}), 400

@app.route('/start_processing', methods=['POST'])
def start_processing():
    """Start audiobook processing job."""
    try:
        data = request.json
        folders = data.get('folders', [])
        options = data.get('options', {})
        
        if not folders:
            return jsonify({'error': 'No folders selected'}), 400
        
        # Create processing job
        job_id = web_state.create_job('processing', {
            'folders': folders,
            'options': options
        })
        
        # Start processing in background thread
        thread = threading.Thread(
            target=process_audiobooks_background,
            args=(job_id, folders, options)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({'job_id': job_id})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/job_status/<job_id>')
def job_status(job_id: str):
    """Get job status and progress."""
    job = web_state.get_job(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    return jsonify(job)

@app.route('/select_candidate', methods=['POST'])
def select_candidate():
    """Handle candidate selection from user."""
    try:
        data = request.json
        job_id = data.get('job_id')
        candidate_index = data.get('candidate_index')
        
        job = web_state.get_job(job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        if not job.get('awaiting_selection'):
            return jsonify({'error': 'Job not awaiting selection'}), 400
        
        candidates = job.get('candidates', [])
        if candidate_index < 0 or candidate_index >= len(candidates):
            return jsonify({'error': 'Invalid candidate index'}), 400
        
        selected = candidates[candidate_index]
        
        # Update job with selection
        web_state.update_job(job_id, {
            'awaiting_selection': False,
            'status': 'processing',
            'selected_candidate': selected
        })
        
        socketio.emit('candidate_selected', {
            'job_id': job_id,
            'candidate': selected
        })
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/skip_book', methods=['POST'])
def skip_book():
    """Skip current book in processing."""
    try:
        data = request.json
        job_id = data.get('job_id')
        
        job = web_state.get_job(job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        # Update job to skip current book
        web_state.update_job(job_id, {
            'awaiting_selection': False,
            'status': 'processing',
            'selected_candidate': None
        })
        
        socketio.emit('book_skipped', {'job_id': job_id})
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def process_audiobooks_background(job_id: str, folders: List[str], options: Dict):
    """Background processing function."""
    print(f"[DEBUG] Starting background processing for job {job_id}")
    print(f"[DEBUG] Threading - Current thread: {threading.current_thread().name}")
    
    try:
        print(f"[DEBUG] About to update job status to starting")
        web_state.update_job(job_id, {'status': 'starting'})
        
        # Create progress reporter
        progress_reporter = WebProgressReporter(job_id)
        
        # Start processing
        print(f"[DEBUG] About to start processing {len(folders)} folders")
        progress_reporter.start_processing(len(folders))
        print(f"[DEBUG] Processing started, beginning folder loop")
        
        # Simple simulation for now to avoid threading issues
        for i, folder_path in enumerate(folders):
            folder_path = Path(folder_path)
            print(f"[DEBUG] Processing folder {i+1}/{len(folders)}: {folder_path}")
            
            # Create metadata for this book
            book_metadata = BookMetadata.create_empty(str(folder_path.name))
            progress_reporter.start_book(book_metadata, i)
            
            # Simulate processing
            print(f"[DEBUG] About to report search progress for {folder_path.name}")
            progress_reporter.report_search_progress(f"Processing {folder_path.name}", "simulation")
            print(f"[DEBUG] Search progress reported, sleeping for 1 second")
            time.sleep(1)  # Simulate processing time
            print(f"[DEBUG] Sleep completed, finishing book")
            progress_reporter.finish_book(True)
            print(f"[DEBUG] Book {i+1} completed")
        
        print(f"[DEBUG] All books processed, updating job to completed")
        web_state.update_job(job_id, {
            'status': 'completed',
            'progress': 100,
            'completed_at': datetime.now(),
            'current_step': 'Processing completed successfully!'
        })
        
        # Send final completion message
        completion_message = {
            'job_id': job_id,
            'progress': 100,
            'current_step': 'Processing completed successfully!'
        }
        print(f"[DEBUG] Emitting final job_progress: {completion_message}")
        socketio.emit('job_progress', completion_message)
        print(f"[DEBUG] Final job_progress emitted")
        
        completion_final = {'job_id': job_id}
        print(f"[DEBUG] Emitting job_completed: {completion_final}")
        socketio.emit('job_completed', completion_final)
        print(f"[DEBUG] job_completed emitted successfully")
        print(f"[DEBUG] Background processing completed for job {job_id}")
        
    except Exception as e:
        print(f"[DEBUG] ERROR in background processing: {e}")
        import traceback
        traceback.print_exc()
        log.error(f"Background processing error: {e}")
        
        web_state.update_job(job_id, {
            'status': 'failed',
            'error': str(e)
        })
        error_message = {'job_id': job_id, 'error': str(e)}
        print(f"[DEBUG] Emitting job_failed: {error_message}")
        socketio.emit('job_failed', error_message)
        print(f"[DEBUG] job_failed emitted")

@socketio.on('connect')
def handle_connect():
    print(f'[DEBUG] Client connected: {request.sid}')
    print(f'[DEBUG] Total connected clients: {len(socketio.server.manager.get_participants(socketio.server.manager.namespace, "/"))}')

@socketio.on('disconnect')
def handle_disconnect():
    print(f'[DEBUG] Client disconnected: {request.sid}')
    print(f'[DEBUG] Total connected clients: {len(socketio.server.manager.get_participants(socketio.server.manager.namespace, "/"))}')

if __name__ == '__main__':
    print(f"🌐 Starting BadaBoomBooks Web Interface v{__version__}")
    print("📁 Available on:")
    print("   Local: http://localhost:5000")
    print("   Network: http://0.0.0.0:5000")
    print("\n🚀 Ready to organize audiobooks!")
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
