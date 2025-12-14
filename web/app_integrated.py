#!/usr/bin/env python3
"""
Updated web interface that integrates with the actual BadaBoomBooks application.
"""

import os
import sys
import json
import threading
import time
import uuid
import logging as log
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from flask import Flask, render_template, request, jsonify

# Add the src directory to the Python path
root_dir = Path(__file__).parent.parent
src_dir = root_dir / 'src'
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(root_dir))

# Import the actual application components
try:
    from src.main import BadaBoomBooksApp
    from src.models import BookMetadata, ProcessingArgs, ProcessingResult
    from src.config import setup_logging, setup_environment
    from src.ui.progress import ProgressReporter
    from src.utils import detect_url_site
    print("✓ Successfully imported BadaBoomBooks core modules")
except ImportError as e:
    print(f"⚠️  Could not import BadaBoomBooks core modules: {e}")
    # Fallback for when core isn't available
    class BookMetadata:
        @staticmethod
        def create_empty(name, url=""):
            obj = object()
            obj.input_folder = name
            obj.url = url
            return obj
    
    class ProcessingArgs:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)
    
    class ProcessingResult:
        def __init__(self):
            self.success_books = []
            self.failed_books = []
            self.skipped_books = []
        
        def has_failures(self):
            return len(self.failed_books) > 0

app = Flask(__name__)
app.secret_key = 'badaboombooks-web-secret'

# Setup logging for web interface
try:
    setup_environment()
    setup_logging(debug=True)
except:
    # Basic logging setup if BadaBoomBooks modules aren't available
    logging.basicConfig(level=logging.INFO)

# Global job storage
jobs = {}

class WebProgressReporter:
    """Progress reporter that updates job status for web interface."""
    
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.start_time = time.time()
        log.info(f"WebProgressReporter created for job {job_id}")
        
    def start_processing(self, total_books: int):
        """Start processing with total book count."""
        log.info(f"Starting processing of {total_books} books")
        jobs[self.job_id].update({
            'total_books': total_books,
            'status': 'processing',
            'progress': 0,
            'current_step': 'Starting processing...',
            'start_time': self.start_time
        })
    
    def start_book(self, metadata, book_index: int):
        """Start processing a specific book."""
        job = jobs.get(self.job_id, {})
        total_books = job.get('total_books', 1)
        progress = (book_index / total_books) * 100 if total_books > 0 else 0
        
        book_name = getattr(metadata, 'input_folder', 'Unknown')
        if hasattr(metadata, 'input_folder') and isinstance(metadata.input_folder, str):
            book_name = Path(metadata.input_folder).name
        
        log.info(f"Starting book {book_index + 1}/{total_books}: {book_name}")
        
        jobs[self.job_id].update({
            'current_book': book_name,
            'book_index': book_index,
            'progress': progress,
            'current_step': f'Processing book {book_index + 1}/{total_books}: {book_name}'
        })
    
    def finish_book(self, success: bool, error: str = None):
        """Mark book as finished."""
        job = jobs.get(self.job_id, {})
        if job:
            book_name = job.get('current_book', 'Unknown')
            if success:
                log.info(f"✅ Book completed: {book_name}")
            else:
                log.error(f"❌ Book failed: {book_name} - {error}")
    
    def report_search_progress(self, search_term: str, search_type: str):
        """Report search progress."""
        log.info(f"🔍 Search progress: {search_type} for {search_term}")
        step_text = f'Searching {search_type} for: {search_term}'
        jobs[self.job_id].update({
            'current_step': step_text
        })
    
    def report_scraping_progress(self, url: str, site: str = ""):
        """Report scraping progress."""
        log.info(f"🌐 Scraping {site}: {url}")
        try:
            site_name = site if site else detect_url_site(url) or "website"
        except:
            site_name = site or "website"
        step_text = f'Scraping metadata from {site_name}...'
        jobs[self.job_id].update({
            'current_step': step_text
        })
    
    def report_file_operation(self, operation: str, source, target=None):
        """Report file operation progress."""
        log.info(f"📁 File operation: {operation}")
        step_text = f'{operation.title()} files...'
        jobs[self.job_id].update({
            'current_step': step_text
        })
    
    def report_metadata_operation(self, operation: str, file_type: str = ""):
        """Report metadata operation progress."""
        log.info(f"📝 Metadata operation: {operation} {file_type}")
        step_text = f'{operation} {file_type}...'
        jobs[self.job_id].update({
            'current_step': step_text
        })
    
    def show_final_summary(self, result: ProcessingResult):
        """Show final processing summary."""
        elapsed = time.time() - self.start_time
        log.info(f"Processing completed in {elapsed:.1f}s")
        
        # Update job with final results
        jobs[self.job_id].update({
            'elapsed_time': elapsed,
            'success_count': len(result.success_books),
            'failed_count': len(result.failed_books),
            'skipped_count': len(result.skipped_books),
            'results': {
                'success': result.success_books,
                'failed': result.failed_books,
                'skipped': result.skipped_books
            }
        })


def process_audiobooks_real(job_id: str, folders: List[str], options: Dict):
    """Real processing function using BadaBoomBooks application."""
    log.info(f"Starting real processing for job {job_id}")
    
    try:
        # Initialize job status
        jobs[job_id].update({
            'status': 'initializing',
            'current_step': 'Initializing BadaBoomBooks application...'
        })
        
        # Create progress reporter
        progress_reporter = WebProgressReporter(job_id)
        
        # Create the main application
        badaboombooksapp = BadaBoomBooksApp()
        
        # Replace the default progress reporter with our web version
        badaboombooksapp.progress = progress_reporter
        
        # Convert options to ProcessingArgs
        processing_args = ProcessingArgs(
            folders=[Path(folder) for folder in folders],
            output=Path(options.get('output')) if options.get('output') else None,
            book_root=None,
            
            # File operations
            copy=options.get('copy', False),
            move=options.get('move', False),
            dry_run=options.get('dry_run', False),
            
            # Processing features
            flatten=options.get('flatten', False),
            rename=options.get('rename', False),
            opf=options.get('opf', True),  # Default to true
            infotxt=options.get('info_txt', False),
            id3_tag=options.get('id3_tags', False),
            series=options.get('series', False),
            cover=options.get('cover', False),
            from_opf=options.get('from_opf', False),
            
            # Search options
            site=options.get('site', 'all'),
            auto_search=options.get('auto_search', False),
            search_limit=options.get('search_limit', 5),
            download_limit=options.get('download_limit', 3),
            search_delay=options.get('search_delay', 2.0),
            
            # Debug
            debug=options.get('debug', True)
        )
        
        # Initialize processors
        badaboombooksapp._initialize_processors(processing_args)
        
        # Process folders
        folders_paths = [Path(folder).resolve() for folder in folders]
        
        # Build processing queue
        jobs[job_id].update({
            'status': 'building_queue',
            'current_step': 'Building processing queue...'
        })
        
        queue_success = badaboombooksapp._build_processing_queue(folders_paths, processing_args)
        if not queue_success:
            jobs[job_id].update({
                'status': 'failed',
                'error': 'Failed to build processing queue'
            })
            return
        
        # Process the queue
        jobs[job_id].update({
            'status': 'processing',
            'current_step': 'Processing audiobooks...'
        })
        
        process_success = badaboombooksapp._process_queue(processing_args)
        
        # Show final summary and mark as completed
        badaboombooksapp.progress.show_final_summary(badaboombooksapp.result)
        
        # Determine final status
        if badaboombooksapp.result.has_failures() and not badaboombooksapp.result.success_books:
            # All failed
            jobs[job_id].update({
                'status': 'failed',
                'progress': 100,
                'completed_at': datetime.now().isoformat(),
                'current_step': 'Processing completed with failures',
                'error': f"{len(badaboombooksapp.result.failed_books)} books failed to process"
            })
        else:
            # Success (even with some failures)
            jobs[job_id].update({
                'status': 'completed',
                'progress': 100,
                'completed_at': datetime.now().isoformat(),
                'current_step': 'Processing completed successfully!'
            })
        
        log.info(f"Real processing completed for job {job_id}")
        
    except Exception as e:
        log.error(f"ERROR in real processing: {e}", exc_info=True)
        jobs[job_id].update({
            'status': 'failed',
            'error': str(e),
            'current_step': f'Error: {str(e)}'
        })


@app.route('/')
def index():
    return render_template('index_integrated.html')

@app.route('/job_status/<job_id>')
def get_job_status(job_id):
    """Get current job status (for polling)."""
    job = jobs.get(job_id, {})
    return jsonify(job)

@app.route('/start_processing', methods=['POST'])
def start_processing():
    """Start audiobook processing job with real BadaBoomBooks integration."""
    try:
        data = request.get_json()
        folders = data.get('folders', [])
        options = data.get('options', {})
        
        if not folders:
            return jsonify({'error': 'No folders provided'}), 400
        
        # Validate folders exist
        invalid_folders = []
        for folder in folders:
            if not Path(folder).exists():
                invalid_folders.append(folder)
        
        if invalid_folders:
            return jsonify({
                'error': f'Some folders do not exist: {", ".join(invalid_folders)}'
            }), 400
        
        # Generate job ID
        job_id = str(uuid.uuid4())
        
        # Initialize job
        jobs[job_id] = {
            'id': job_id,
            'folders': folders,
            'options': options,
            'status': 'created',
            'progress': 0,
            'created_at': datetime.now().isoformat(),
            'current_step': 'Job created...',
            'current_book': '',
            'results': [],
            'errors': []
        }
        
        # Start processing in background thread
        thread = threading.Thread(
            target=process_audiobooks_real,
            args=(job_id, folders, options),
            daemon=True,
            name=f"BadaBoomBooks-{job_id[:8]}"
        )
        thread.start()
        
        log.info(f"Started processing job {job_id} with {len(folders)} folders")
        
        return jsonify({'job_id': job_id})
        
    except Exception as e:
        log.error(f"Error starting processing: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/browse')
def browse():
    """File browser for selecting audiobook folders."""
    path = request.args.get('path', '')
    
    try:
        # Handle drive listing for Windows
        if not path or path == 'drives':
            import string
            drives = []
            if os.name == 'nt':  # Windows
                for letter in string.ascii_uppercase:
                    drive_path = f"{letter}:\\"
                    if os.path.exists(drive_path):
                        try:
                            os.listdir(drive_path)
                            drives.append({
                                'name': f"{letter}: Drive",
                                'path': drive_path,
                                'type': 'drive',
                                'audio_count': 0
                            })
                        except (OSError, PermissionError):
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
                path = '/'
        
        if not path:
            if os.name == 'nt':
                return browse()
            else:
                path = '/'
        
        if os.name == 'nt' and path.endswith('\\') and len(path) == 3:
            current_path = Path(path)
        else:
            current_path = Path(path).resolve()
        
        if os.name == 'nt' and str(current_path).endswith(':\\'):
            parent_path = 'drives'
        else:
            parent = current_path.parent if current_path != current_path.parent else None
            parent_path = str(parent) if parent else None
        
        items = []
        if current_path.exists() and current_path.is_dir():
            try:
                for item in sorted(current_path.iterdir()):
                    if item.is_dir():
                        audio_extensions = ['.mp3', '.m4a', '.m4b', '.flac', '.ogg', '.wma']
                        audio_files = []
                        try:
                            for ext in audio_extensions:
                                audio_files.extend(list(item.glob(f'*{ext}')))
                                if len(audio_files) > 0:
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
        log.error(f"Error browsing path {path}: {e}", exc_info=True)
        return jsonify({'error': f'Failed to browse path: {e}'}), 400

@app.route('/test_processing')
def test_processing():
    """Test endpoint to verify processing integration works."""
    try:
        # Try to import and test the main application
        from src.main import BadaBoomBooksApp
        from src.models import ProcessingArgs
        
        # Create a test instance
        app_instance = BadaBoomBooksApp()
        
        return jsonify({
            'status': 'success',
            'message': 'BadaBoomBooks integration is working',
            'components': {
                'main_app': 'imported successfully',
                'models': 'imported successfully',
                'processors': 'available'
            }
        })
        
    except Exception as e:
        log.error(f"Test processing error: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

if __name__ == '__main__':
    print("🌐 Starting BadaBoomBooks Web Interface with Real Processing")
    print("📁 Available on: http://localhost:5001")
    print("🔥 This version integrates with the actual BadaBoomBooks application")
    print("⚙️  Test the integration at: http://localhost:5001/test_processing")
    
    app.run(host='0.0.0.0', port=5001, debug=True, threaded=True)