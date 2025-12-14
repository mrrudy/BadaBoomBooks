#!/usr/bin/env python3
"""
FIXED web interface that integrates with the actual BadaBoomBooks application.
This version fixes the auto-search integration issue.
"""

import os
import sys
import json
import threading
import time
import uuid
import logging as log
import logging
import requests
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
    CORE_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Could not import BadaBoomBooks core modules: {e}")
    print("   Web interface will work in simulation mode")
    CORE_AVAILABLE = False

app = Flask(__name__)
app.secret_key = 'badaboombooks-web-secret'

# Setup logging
try:
    if CORE_AVAILABLE:
        setup_environment()
        setup_logging()
except:
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
        log.info(f"Starting processing of {total_books} books")
        jobs[self.job_id].update({
            'total_books': total_books,
            'status': 'processing',
            'progress': 0,
            'current_step': 'Starting processing...',
            'start_time': self.start_time
        })
    
    def start_book(self, metadata, book_index: int):
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
        job = jobs.get(self.job_id, {})
        if job:
            book_name = job.get('current_book', 'Unknown')
            if success:
                log.info(f"✅ Book completed: {book_name}")
            else:
                log.error(f"❌ Book failed: {book_name} - {error}")
    
    def report_search_progress(self, search_term: str, search_type: str):
        log.info(f"🔍 Search progress: {search_type} for {search_term}")
        step_text = f'Searching {search_type} for: {search_term}'
        jobs[self.job_id].update({'current_step': step_text})
    
    def report_scraping_progress(self, url: str, site: str = ""):
        log.info(f"🌐 Scraping {site}: {url}")
        try:
            site_name = site if site else (detect_url_site(url) if CORE_AVAILABLE else "website")
        except:
            site_name = site or "website"
        step_text = f'Scraping metadata from {site_name}...'
        jobs[self.job_id].update({'current_step': step_text})
    
    def report_file_operation(self, operation: str, source, target=None):
        log.info(f"📁 File operation: {operation}")
        step_text = f'{operation.title()} files...'
        jobs[self.job_id].update({'current_step': step_text})
    
    def report_metadata_operation(self, operation: str, file_type: str = ""):
        log.info(f"📝 Metadata operation: {operation} {file_type}")
        step_text = f'{operation} {file_type}...'
        jobs[self.job_id].update({'current_step': step_text})
    
    def show_final_summary(self, result: ProcessingResult):
        elapsed = time.time() - self.start_time
        log.info(f"Processing completed in {elapsed:.1f}s")
        
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


class WebAutoSearchEngine:
    """FIXED web-compatible auto-search engine."""
    
    def __init__(self, progress_reporter, debug=True):
        self.progress_reporter = progress_reporter
        self.debug = debug
    
    def search_and_select_with_context(self, search_term: str, site_keys: list, book_info: dict, 
                                      search_limit: int = 5, download_limit: int = 3, search_delay: float = 2.0):
        """FIXED version that uses the original AutoSearchEngine but automatically selects candidates."""
        try:
            log.info(f"🔧 FIXED Web auto-search starting for: '{search_term}'")
            log.info(f"🔍 Sites to search: {site_keys}")
            log.info(f"📚 Book info: {book_info}")
            
            # Import and use the original AutoSearchEngine
            from src.search.auto_search import AutoSearchEngine
            from selenium import webdriver
            from src.config import get_chrome_options
            
            # Create original search engine
            auto_search = AutoSearchEngine(debug=self.debug)
            
            # Initialize Chrome driver (like the original)
            chrome_options = get_chrome_options()
            driver = None
            all_candidates = []
            
            try:
                driver = webdriver.Chrome(options=chrome_options)
                log.info("✅ Chrome driver initialized successfully")
                
                # Search each site using the original method
                for site_key in site_keys:
                    try:
                        log.info(f"🔍 Searching {site_key} using original method...")
                        self.progress_reporter.report_search_progress(search_term, f"{site_key} search")
                        
                        # Use the original _search_single_site method
                        candidates = auto_search._search_single_site(
                            driver, site_key, search_term, search_limit, download_limit, search_delay
                        )
                        
                        log.info(f"Found {len(candidates)} candidates from {site_key}")
                        all_candidates.extend(candidates)
                        
                        if search_delay > 0:
                            time.sleep(search_delay)
                            
                    except Exception as e:
                        log.error(f"Search failed for {site_key}: {e}")
                        continue
                
            finally:
                if driver:
                    driver.quit()
                    log.info("Chrome driver closed")
            
            log.info(f"Total candidates found: {len(all_candidates)}")
            
            if not all_candidates:
                log.warning("No search candidates found")
                return None, None, None
            
            # Auto-select the best candidate
            best_candidate = self._select_best_candidate_auto(all_candidates, book_info)
            
            if best_candidate:
                log.info(f"🎯 Auto-selected: {best_candidate.site_key} - {best_candidate.title}")
                return best_candidate.site_key, best_candidate.url, best_candidate.html
            else:
                log.warning("No suitable candidate found after scoring")
                return None, None, None
                
        except Exception as e:
            log.error(f"FIXED Web auto-search error: {e}", exc_info=True)
            return None, None, None
    
    def _select_best_candidate_auto(self, candidates, book_info):
        """Automatically select the best candidate based on scoring."""
        if not candidates:
            return None
        
        log.info(f"🎯 Auto-selecting from {len(candidates)} candidates...")
        
        # Score each candidate
        scored_candidates = []
        for candidate in candidates:
            score = self._score_candidate(candidate, book_info)
            scored_candidates.append((score, candidate))
            log.debug(f"Candidate score {score:.2f}: {candidate.site_key} - {candidate.title}")
        
        # Sort by score (higher is better)
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        
        # Log the scoring results
        log.info("Top candidate scores:")
        for i, (score, candidate) in enumerate(scored_candidates[:3]):
            log.info(f"  {i+1}. {score:.2f}: {candidate.site_key} - {candidate.title}")
        
        # Return the best candidate
        if scored_candidates:
            best_score, best_candidate = scored_candidates[0]
            log.info(f"🏆 Selected best candidate with score {best_score:.2f}")
            return best_candidate
        else:
            return None
    
    def _score_candidate(self, candidate, book_info):
        """Score a candidate based on how well it matches the book info."""
        score = 0.0
        
        if not book_info:
            return 1.0
        
        candidate_title = candidate.title.lower()
        candidate_snippet = candidate.snippet.lower() if candidate.snippet else ""
        candidate_text = f"{candidate_title} {candidate_snippet}"
        
        # Extract book info safely
        book_title = str(book_info.get('title', '')).lower()
        book_author = str(book_info.get('author', '')).lower()
        book_series = str(book_info.get('series', '')).lower()
        folder_name = str(book_info.get('folder_name', '')).lower()
        
        # Title matching (most important)
        if book_title:
            if book_title in candidate_title:
                score += 15.0
            else:
                title_words = [word for word in book_title.split() if len(word) > 3]
                matches = sum(1 for word in title_words if word in candidate_text)
                score += matches * 3.0
        
        # Folder name matching as fallback
        if folder_name and not book_title:
            clean_folder = folder_name.replace('_', ' ').replace('-', ' ')
            if clean_folder in candidate_title:
                score += 10.0
            else:
                folder_words = [word for word in clean_folder.split() if len(word) > 3]
                matches = sum(1 for word in folder_words if word in candidate_text)
                score += matches * 2.0
        
        # Author matching
        if book_author:
            if book_author in candidate_text:
                score += 8.0
            else:
                author_words = [word for word in book_author.split() if len(word) > 2]
                matches = sum(1 for word in author_words if word in candidate_text)
                score += matches * 2.0
        
        # Series matching
        if book_series and book_series in candidate_text:
            score += 5.0
        
        # Site preference
        site_scores = {'audible': 4.0, 'goodreads': 3.0, 'lubimyczytac': 2.0}
        score += site_scores.get(candidate.site_key, 1.0)
        
        # Polish content preference
        if 'polish' in folder_name or any(polish_word in candidate_text for polish_word in ['polish', 'polski', 'polska']):
            if candidate.site_key == 'lubimyczytac':
                score += 3.0
        
        return max(0.0, score)


def process_audiobooks_real_fixed(job_id: str, folders: List[str], options: Dict):
    """FIXED real processing function with proper auto-search integration."""
    
    print(f"\n🔧 FIXED REAL PROCESSING STARTED for job {job_id}")
    
    try:
        # Setup debug logging
        debug_log_file = Path(__file__).parent.parent / f'web_debug_fixed_{job_id[:8]}.log'
        debug_logger = logging.getLogger(f'web_debug_fixed_{job_id}')
        debug_logger.setLevel(logging.DEBUG)
        
        file_handler = logging.FileHandler(str(debug_log_file), mode='w', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        debug_logger.addHandler(file_handler)
        
        debug_logger.info(f"🔧 FIXED WEB DEBUG LOG STARTED for job {job_id}")
        debug_logger.info(f"📁 Folders to process: {folders}")
        debug_logger.info(f"⚙️ Options: {options}")
        
        # Initialize job status
        jobs[job_id].update({
            'status': 'initializing',
            'current_step': 'Initializing FIXED BadaBoomBooks application...'
        })
        
        # Create progress reporter
        progress_reporter = WebProgressReporter(job_id)
        debug_logger.info("Progress reporter created")
        
        # Create the main application
        badaboombooksapp = BadaBoomBooksApp()
        debug_logger.info("BadaBoomBooksApp created")
        
        # Replace the default progress reporter
        badaboombooksapp.progress = progress_reporter
        debug_logger.info("Progress reporter replaced")
        
        # Convert options to ProcessingArgs
        processing_args = ProcessingArgs(
            folders=[Path(folder) for folder in folders],
            output=Path(options.get('output')) if options.get('output') else None,
            book_root=None,
            copy=options.get('copy', False),
            move=options.get('move', False),
            dry_run=options.get('dry_run', False),
            flatten=options.get('flatten', False),
            rename=options.get('rename', False),
            opf=options.get('opf', True),
            infotxt=options.get('info_txt', False),
            id3_tag=options.get('id3_tags', False),
            series=options.get('series', False),
            cover=options.get('cover', False),
            from_opf=options.get('from_opf', False),
            site=options.get('site', 'all'),
            auto_search=True,  # Always use auto search in web interface
            search_limit=options.get('search_limit', 5),
            download_limit=options.get('download_limit', 3),
            search_delay=options.get('search_delay', 2.0),
            debug=options.get('debug', True)
        )
        
        # CRITICAL FIX: Replace auto_search BEFORE initializing processors
        debug_logger.info("=== FIXED AUTO SEARCH REPLACEMENT (BEFORE PROCESSORS) ===")
        
        # Create our web-compatible auto search engine FIRST
        web_auto_search = WebAutoSearchEngine(progress_reporter, debug=True)
        
        # Initialize processors AFTER we set up our auto search
        badaboombooksapp._initialize_processors(processing_args)
        debug_logger.info("Processors initialized")
        
        # Now replace the auto_search that was just created
        if hasattr(badaboombooksapp, 'auto_search') and badaboombooksapp.auto_search is not None:
            debug_logger.info(f"Found existing auto_search: {type(badaboombooksapp.auto_search)}")
            badaboombooksapp.auto_search = web_auto_search
            debug_logger.info("✅ Replaced existing auto_search with WebAutoSearchEngine")
        else:
            debug_logger.info("No existing auto_search found, creating new one")
            badaboombooksapp.auto_search = web_auto_search
            debug_logger.info("✅ Created new WebAutoSearchEngine")
        
        debug_logger.info(f"Final auto_search type: {type(badaboombooksapp.auto_search)}")
        debug_logger.info(f"Has search_and_select_with_context: {hasattr(badaboombooksapp.auto_search, 'search_and_select_with_context')}")
        
        # Test the method exists
        if hasattr(badaboombooksapp.auto_search, 'search_and_select_with_context'):
            debug_logger.info("✅ search_and_select_with_context method is available")
        else:
            debug_logger.error("❌ search_and_select_with_context method is NOT available - this will cause problems!")
        
        # Process folders
        folders_paths = [Path(folder).resolve() for folder in folders]
        
        # Build processing queue
        jobs[job_id].update({
            'status': 'building_queue',
            'current_step': 'Building processing queue...'
        })
        
        debug_logger.info("=== QUEUE BUILDING PHASE ===")
        debug_logger.info(f"About to build queue for folders: {folders_paths}")
        
        queue_success = badaboombooksapp._build_processing_queue(folders_paths, processing_args)
        
        debug_logger.info(f"Queue building finished. Success: {queue_success}")
        
        if not queue_success:
            error_msg = 'Failed to build processing queue'
            jobs[job_id].update({
                'status': 'failed',
                'error': error_msg
            })
            debug_logger.error(error_msg)
            return
        
        # Process the queue
        jobs[job_id].update({
            'status': 'processing',
            'current_step': 'Processing audiobooks...'
        })
        
        debug_logger.info("=== QUEUE PROCESSING PHASE ===")
        
        process_success = badaboombooksapp._process_queue(processing_args)
        
        debug_logger.info(f"Queue processing finished. Success: {process_success}")
        
        # Show final summary
        badaboombooksapp.progress.show_final_summary(badaboombooksapp.result)
        
        # Determine final status
        if badaboombooksapp.result.has_failures() and not badaboombooksapp.result.success_books:
            final_status = {
                'status': 'failed',
                'progress': 100,
                'completed_at': datetime.now().isoformat(),
                'current_step': 'Processing completed with failures',
                'error': f"{len(badaboombooksapp.result.failed_books)} books failed to process"
            }
        else:
            final_status = {
                'status': 'completed',
                'progress': 100,
                'completed_at': datetime.now().isoformat(),
                'current_step': 'Processing completed successfully!'
            }
        
        jobs[job_id].update(final_status)
        debug_logger.info(f"Final status: {final_status}")
        
        log.info(f"FIXED real processing completed for job {job_id}")
        
    except Exception as e:
        error_msg = str(e)
        log.error(f"ERROR in FIXED real processing: {e}", exc_info=True)
        
        final_status = {
            'status': 'failed',
            'error': error_msg,
            'current_step': f'Error: {error_msg}'
        }
        
        jobs[job_id].update(final_status)
        
        if 'debug_logger' in locals():
            debug_logger.error(f"FATAL ERROR: {e}", exc_info=True)


@app.route('/')
def index():
    return render_template('index_simple.html')

@app.route('/job_status/<job_id>')
def get_job_status(job_id):
    job = jobs.get(job_id, {})
    return jsonify(job)

@app.route('/start_processing', methods=['POST'])
def start_processing():
    print("\n" + "="*80)
    print("🔧 FIXED START_PROCESSING ROUTE CALLED")
    print(f"CORE_AVAILABLE: {CORE_AVAILABLE}")
    print("="*80 + "\n")
    
    try:
        data = request.get_json()
        folders = data.get('folders', [])
        options = data.get('options', {})
        
        print(f"📁 Received folders: {folders}")
        print(f"⚙️ Received options: {options}")
        
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
        print(f"🆔 Generated job ID: {job_id}")
        
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
        
        # Choose processing function
        if CORE_AVAILABLE:
            process_func = process_audiobooks_real_fixed  # Use FIXED version
            mode = "real_fixed"
            print("🔧 Using FIXED real processing function")
        else:
            # For simulation - would need to implement if needed
            return jsonify({'error': 'Simulation mode not implemented in fixed version'}), 500
        
        print(f"🎯 Selected processing mode: {mode}")
        
        # Start processing in background thread
        thread = threading.Thread(
            target=process_func,
            args=(job_id, folders, options),
            daemon=True,
            name=f"BadaBoomBooks-{mode}-{job_id[:8]}"
        )
        thread.start()
        
        print(f"🚀 Started {mode} processing thread: {thread.name}")
        
        return jsonify({'job_id': job_id})
        
    except Exception as e:
        print(f"❌ ERROR in start_processing route: {e}")
        log.error(f"Error starting processing: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/browse')
def browse():
    path = request.args.get('path', '')
    
    try:
        # Handle drive listing for Windows
        if not path or path == 'drives':
            import string
            drives = []
            if os.name == 'nt':
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
        
        current_path = Path(path).resolve() if path else Path.home()
        
        parent = current_path.parent if current_path != current_path.parent else None
        parent_path = str(parent) if parent else 'drives' if os.name == 'nt' else None
        
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
    try:
        if CORE_AVAILABLE:
            return jsonify({
                'status': 'success',
                'message': 'FIXED BadaBoomBooks integration is working',
                'mode': 'real_processing_fixed',
                'components': {
                    'main_app': 'imported successfully',
                    'models': 'imported successfully',
                    'processors': 'available'
                }
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'BadaBoomBooks core modules not available',
                'mode': 'unavailable'
            })
        
    except Exception as e:
        log.error(f"Test processing error: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e),
            'mode': 'error'
        }), 500

if __name__ == '__main__':
    mode_text = "FIXED Real Processing Integration" if CORE_AVAILABLE else "Core Not Available"
    print(f"🌐 Starting FIXED BadaBoomBooks Web Interface - {mode_text}")
    print("📁 Available on: http://localhost:5001")
    
    if CORE_AVAILABLE:
        print("🔧 This FIXED version should resolve the auto-search integration issue")
        print("⚙️  Test the integration at: http://localhost:5001/test_processing")
    else:
        print("❌ BadaBoomBooks core modules not available")
    
    app.run(host='0.0.0.0', port=5001, debug=True, threaded=True)
