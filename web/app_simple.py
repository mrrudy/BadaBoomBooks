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
import logging
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
    if CORE_AVAILABLE:
        setup_environment()
        setup_logging()
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
            site_name = site if site else (detect_url_site(url) if CORE_AVAILABLE else "website")
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


def process_audiobooks_simulation(job_id: str, folders: List[str], options: Dict):
    """Simulation processing when core modules aren't available."""
    print(f"\n🎭 SIMULATION PROCESSING STARTED for job {job_id}")
    print(f"This should NOT be called if CORE_AVAILABLE is True!")
    print(f"CORE_AVAILABLE = {CORE_AVAILABLE}")
    
    log.info(f"Starting simulation processing for job {job_id}")
    
    try:
        # Initialize job status
        jobs[job_id].update({
            'status': 'initializing',
            'current_step': 'Initializing simulation mode...'
        })
        
        # Create progress reporter
        progress_reporter = WebProgressReporter(job_id)
        progress_reporter.start_processing(len(folders))
        
        # Simulate processing each folder
        for i, folder_path in enumerate(folders):
            folder_path = Path(folder_path)
            log.info(f"Simulating processing folder {i+1}/{len(folders)}: {folder_path}")
            
            # Create fake metadata for this book
            book_metadata = BookMetadata.create_empty(str(folder_path.name))
            progress_reporter.start_book(book_metadata, i)
            
            # Simulate various processing steps
            progress_reporter.report_search_progress(f"Searching for {folder_path.name}", "simulation")
            time.sleep(0.5)
            
            progress_reporter.report_scraping_progress("http://simulation.url", "simulation")
            time.sleep(0.5)
            
            progress_reporter.report_metadata_operation("Creating", "OPF file")
            time.sleep(0.3)
            
            progress_reporter.finish_book(True)
            time.sleep(0.2)
        
        # Create fake results
        fake_result = ProcessingResult()
        for folder in folders:
            fake_result.add_success(Path(folder).name, "Simulation/Test Author")
        
        progress_reporter.show_final_summary(fake_result)
        
        # Mark as completed
        jobs[job_id].update({
            'status': 'completed',
            'progress': 100,
            'completed_at': datetime.now().isoformat(),
            'current_step': 'Simulation completed successfully!'
        })
        
        log.info(f"Simulation processing completed for job {job_id}")
        
    except Exception as e:
        log.error(f"ERROR in simulation processing: {e}", exc_info=True)
        jobs[job_id].update({
            'status': 'failed',
            'error': str(e),
            'current_step': f'Simulation error: {str(e)}'
        })


class WebAutoSearchEngine:
    """Web-compatible auto-search engine that automatically selects best matches."""
    
    def __init__(self, progress_reporter):
        self.progress_reporter = progress_reporter
    
    def search_and_select_with_context(self, search_term: str, site_keys: list, book_info: dict, 
                                      search_limit: int = 5, download_limit: int = 3, search_delay: float = 2.0):
        """Interface compatible with AutoSearchEngine."""
        return self._search_and_auto_select(search_term, site_keys, book_info, search_limit, download_limit, search_delay)
    
    def _search_and_auto_select(self, search_term: str, site_keys: list, book_info: dict, 
                               search_limit: int = 5, download_limit: int = 3, search_delay: float = 2.0):
        """Search and automatically select the best candidate without user input."""
        try:
            log.info(f"Web auto-search starting for: '{search_term}'")
            log.info(f"Sites to search: {site_keys}")
            log.info(f"Book info: {book_info}")
            
            # Import here to avoid circular imports
            from src.search.auto_search import AutoSearchEngine
            
            # Create the original auto search engine
            auto_search = AutoSearchEngine(debug=True)
            
            # Perform search on each site to get candidates
            all_candidates = []
            for site_key in site_keys:
                try:
                    log.info(f"Searching {site_key}...")
                    candidates = auto_search._search_site(search_term, site_key, search_limit)
                    log.info(f"Found {len(candidates)} candidates from {site_key}")
                    all_candidates.extend(candidates)
                    if search_delay > 0:
                        time.sleep(search_delay)
                except Exception as e:
                    log.error(f"Search failed for {site_key}: {e}")
                    continue
            
            log.info(f"Total candidates found: {len(all_candidates)}")
            
            if not all_candidates:
                log.warning("No search candidates found")
                return None, None, None
            
            # Auto-select the best candidate
            best_candidate = self._select_best_candidate(all_candidates, book_info)
            
            if best_candidate:
                log.info(f"Auto-selected: {best_candidate.site_key} - {best_candidate.title}")
                
                # Download the page content
                try:
                    log.info(f"Downloading page content for: {best_candidate.url}")
                    
                    # Create a temporary metadata object for the download
                    temp_metadata = BookMetadata.create_empty("temp", best_candidate.url)
                    
                    if best_candidate.site_key == 'audible':
                        from src.scrapers.base import http_request_audible_api
                        temp_metadata, response = http_request_audible_api(temp_metadata, log)
                    else:
                        from src.scrapers.base import http_request_generic
                        temp_metadata, response = http_request_generic(temp_metadata, log)
                    
                    if temp_metadata.failed:
                        log.error(f"Failed to download page: {temp_metadata.failed_exception}")
                        return best_candidate.site_key, best_candidate.url, best_candidate.html or ""
                    
                    log.info(f"Successfully downloaded page content ({len(response)} characters)")
                    return best_candidate.site_key, best_candidate.url, response
                    
                except Exception as e:
                    log.error(f"Failed to download page for {best_candidate.url}: {e}")
                    # Return the candidate with whatever HTML we have
                    return best_candidate.site_key, best_candidate.url, best_candidate.html or ""
            else:
                log.warning("No suitable candidate found after scoring")
                return None, None, None
            
        except Exception as e:
            log.error(f"Web auto-search error: {e}", exc_info=True)
            return None, None, None
    
    def _select_best_candidate(self, candidates, book_info):
        """Automatically select the best candidate based on scoring."""
        if not candidates:
            return None
        
        # Score each candidate
        scored_candidates = []
        for candidate in candidates:
            score = self._score_candidate(candidate, book_info)
            scored_candidates.append((score, candidate))
        
        # Sort by score (higher is better)
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        
        # Log the scoring results
        log.info("Candidate scoring results:")
        for score, candidate in scored_candidates[:3]:  # Show top 3
            log.info(f"  {score:.2f}: {candidate.site_key} - {candidate.title}")
        
        # Return the best candidate
        return scored_candidates[0][1] if scored_candidates else None
    
    def _select_best_candidate_direct(self, candidates, book_info):
        """Direct candidate selection that returns the actual candidate object expected by the system."""
        best_candidate = self._select_best_candidate(candidates, book_info)
        if best_candidate:
            log.info(f"WebAutoSearch selected: {best_candidate.site_key} - {best_candidate.title}")
            return best_candidate
        else:
            log.warning("No suitable candidate found, skipping")
            return None
    
    def _score_candidate(self, candidate, book_info):
        """Score a candidate based on how well it matches the book info."""
        score = 0.0
        
        # Get book info
        book_title = book_info.get('title', '').lower()
        book_author = book_info.get('author', '').lower()
        book_series = book_info.get('series', '').lower()
        book_language = book_info.get('language', '')
        
        candidate_title = candidate.title.lower()
        
        # Title matching (most important)
        if book_title and book_title in candidate_title:
            score += 10.0
        elif book_title:
            # Partial title match
            words = book_title.split()
            matches = sum(1 for word in words if len(word) > 3 and word in candidate_title)
            score += matches * 3.0
        
        # Author matching
        if book_author and book_author in candidate_title:
            score += 5.0
        
        # Series matching
        if book_series and book_series in candidate_title:
            score += 3.0
        
        # Language preference (prefer Polish for Polish books, English otherwise)
        if book_language == 'pol' and candidate.site_key == 'lubimyczytac':
            score += 2.0
        elif book_language != 'pol' and candidate.site_key in ['audible', 'goodreads']:
            score += 2.0
        
        # Site preference based on user preference (lubimyczytac > goodreads > audible)
        site_scores = {'lubimyczytac': 3.0, 'goodreads': 2.0, 'audible': 1.0}
        score += site_scores.get(candidate.site_key, 0.0)
        
        # Prefer exact matches in URL or snippet
        if book_title and book_title.replace(' ', '-') in candidate.url.lower():
            score += 2.0
        
        return score


def process_audiobooks_real(job_id: str, folders: List[str], options: Dict):
    """Real processing function using BadaBoomBooks application."""
    
    print(f"\n🔥 REAL PROCESSING STARTED for job {job_id}")
    print(f"This should be called when CORE_AVAILABLE is True!")
    print(f"CORE_AVAILABLE = {CORE_AVAILABLE}")
    print(f"Folders: {folders}")
    print(f"Options: {options}")
    
    try:
        print("🚧 Step 1: Creating debug log file...")
        # Setup detailed debug logging to file
        debug_log_file = Path(__file__).parent.parent / f'web_debug_{job_id[:8]}.log'
        
        print(f"📝 Debug log file path: {debug_log_file}")
        
        # Create a custom logger for this job
        debug_logger = logging.getLogger(f'web_debug_{job_id}')
        debug_logger.setLevel(logging.DEBUG)
        
        # File handler for debug output
        file_handler = logging.FileHandler(str(debug_log_file), mode='w', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        debug_logger.addHandler(file_handler)
        
        print("✅ Step 1 completed: Debug logger created")
        
        debug_logger.info(f"🚀 WEB DEBUG LOG STARTED for job {job_id}")
        debug_logger.info(f"📁 Folders to process: {folders}")
        debug_logger.info(f"⚙️ Options: {options}")
        
        print("🚧 Step 2: Setting up job status...")
        # Initialize job status
        jobs[job_id].update({
            'status': 'initializing',
            'current_step': 'Initializing BadaBoomBooks application...'
        })
        
        print("✅ Step 2 completed: Job status updated")
        debug_logger.info("=== INITIALIZATION PHASE ===")
        
        # Create progress reporter
        progress_reporter = WebProgressReporter(job_id)
        debug_logger.info("Progress reporter created")
        
        # Create custom web auto-search engine
        web_auto_search = WebAutoSearchEngine(progress_reporter)
        debug_logger.info("Web auto-search engine created")
        
        # Create the main application
        badaboombooksapp = BadaBoomBooksApp()
        debug_logger.info("BadaBoomBooksApp created")
        
        # Replace the default progress reporter with our web version
        badaboombooksapp.progress = progress_reporter
        debug_logger.info("Progress reporter replaced")
        
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
            
            # Search options - FORCE auto_search to true for web interface
            site=options.get('site', 'all'),
            auto_search=True,  # Always use auto search in web interface
            search_limit=options.get('search_limit', 5),
            download_limit=options.get('download_limit', 3),
            search_delay=options.get('search_delay', 2.0),
            
            # Debug
            debug=options.get('debug', True)
        )
        
        # Initialize processors
        badaboombooksapp._initialize_processors(processing_args)
        debug_logger.info("Processors initialized")
        
        # FORCE initialize auto_search if it's not set
        debug_logger.info("=== AUTO SEARCH INITIALIZATION ===")
        debug_logger.info(f"Before forcing: auto_search exists: {hasattr(badaboombooksapp, 'auto_search')}, value: {getattr(badaboombooksapp, 'auto_search', 'NOT_SET')}")
        log.info(f"Before forcing: auto_search exists: {hasattr(badaboombooksapp, 'auto_search')}, value: {getattr(badaboombooksapp, 'auto_search', 'NOT_SET')}")
        
        if not hasattr(badaboombooksapp, 'auto_search') or badaboombooksapp.auto_search is None:
            debug_logger.info("🔧 Forcing initialization of auto_search...")
            log.info("🔧 Forcing initialization of auto_search...")
            from src.search.auto_search import AutoSearchEngine
            badaboombooksapp.auto_search = AutoSearchEngine(processing_args.debug if hasattr(processing_args, 'debug') else True)
            debug_logger.info("✅ Forced auto_search initialization complete")
            log.info("✅ Forced auto_search initialization complete")
        else:
            debug_logger.info("auto_search already exists, no forcing needed")
        
        # CRITICAL: Override the auto search method to prevent terminal prompts
        # THIS MUST HAPPEN BEFORE QUEUE BUILDING!
        debug_logger.info("=== AUTO SEARCH METHOD OVERRIDE ===")
        debug_logger.info(f"Checking auto_search availability: {hasattr(badaboombooksapp, 'auto_search')}")
        log.info(f"Checking auto_search availability: {hasattr(badaboombooksapp, 'auto_search')}")
        
        if hasattr(badaboombooksapp, 'auto_search'):
            debug_logger.info(f"auto_search object: {badaboombooksapp.auto_search}")
            log.info(f"auto_search object: {badaboombooksapp.auto_search}")
            
        if hasattr(badaboombooksapp, 'auto_search') and badaboombooksapp.auto_search:
            debug_logger.info("Found auto_search, attempting to override...")
            log.info("Found auto_search, attempting to override...")
            
            # Store original method
            original_method = badaboombooksapp.auto_search.search_and_select_with_context
            debug_logger.info(f"Original method: {original_method}")
            log.info(f"Original method: {original_method}")
            
            def web_compatible_search(search_term, site_keys, book_info, search_limit, download_limit, search_delay):
                """Web-compatible search that automatically selects best candidate."""
                debug_logger.info(f"🚨 WEB-COMPATIBLE SEARCH CALLED! Term: {search_term}, Sites: {site_keys}")
                debug_logger.info(f"Book info: {book_info}")
                log.info(f"🚨 WEB-COMPATIBLE SEARCH CALLED! Term: {search_term}, Sites: {site_keys}")
                try:
                    result = web_auto_search.search_and_select_with_context(search_term, site_keys, book_info, search_limit, download_limit, search_delay)
                    debug_logger.info(f"Web search result: {result[0] if result[0] else 'None'}, {result[1] if result[1] else 'None'}")
                    log.info(f"Web search result: {result[0] if result[0] else 'None'}, {result[1] if result[1] else 'None'}")
                    return result
                except Exception as e:
                    debug_logger.error(f"Web search failed with exception: {e}", exc_info=True)
                    log.error(f"Web search failed with exception: {e}", exc_info=True)
                    return None, None, None
            
            # Replace the method
            badaboombooksapp.auto_search.search_and_select_with_context = web_compatible_search
            debug_logger.info("✅ Successfully replaced auto_search method with web-compatible version")
            log.info("✅ Successfully replaced auto_search method with web-compatible version")
        else:
            debug_logger.warning("❌ No auto_search found or it's None - this might be the problem!")
            log.warning("❌ No auto_search found or it's None - this might be the problem!")
        
        # Process folders
        folders_paths = [Path(folder).resolve() for folder in folders]
        
        # Build processing queue
        jobs[job_id].update({
            'status': 'building_queue',
            'current_step': 'Building processing queue...'
        })
        
        debug_logger.info("=== QUEUE BUILDING PHASE ===")
        debug_logger.info(f"About to build queue for folders: {folders_paths}")
        log.info("🚀 About to build processing queue...")
        
        queue_success = badaboombooksapp._build_processing_queue(folders_paths, processing_args)
        
        debug_logger.info(f"Queue building finished. Success: {queue_success}")
        log.info(f"🏁 Queue building finished. Success: {queue_success}")
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
        
        log.info("🔄 About to start queue processing...")
        process_success = badaboombooksapp._process_queue(processing_args)
        log.info(f"✅ Queue processing finished. Success: {process_success}")
        
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
    # Temporarily use simple template to debug
    return render_template('index_simple.html')

@app.route('/job_status/<job_id>')
def get_job_status(job_id):
    """Get current job status (for polling)."""
    job = jobs.get(job_id, {})
    return jsonify(job)

@app.route('/start_processing', methods=['POST'])
def start_processing():
    """Start audiobook processing job with real BadaBoomBooks integration."""
    print("\n" + "="*80)
    print("🚀 START_PROCESSING ROUTE CALLED")
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
        
        # Choose processing function based on core availability
        if CORE_AVAILABLE:
            process_func = process_audiobooks_real
            mode = "real"
            print("🔥 Using REAL processing function")
        else:
            process_func = process_audiobooks_simulation
            mode = "simulation"
            print("⚠️ Using SIMULATION processing function")
        
        print(f"🎯 Selected processing mode: {mode}")
        print(f"📦 Process function: {process_func}")
        
        # Start processing in background thread
        thread = threading.Thread(
            target=process_func,
            args=(job_id, folders, options),
            daemon=True,
            name=f"BadaBoomBooks-{mode}-{job_id[:8]}"
        )
        thread.start()
        
        print(f"🚀 Started {mode} processing thread: {thread.name}")
        
        log.info(f"Started {mode} processing job {job_id} with {len(folders)} folders")
        
        return jsonify({'job_id': job_id})
        
    except Exception as e:
        print(f"❌ ERROR in start_processing route: {e}")
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
        if CORE_AVAILABLE:
            # Try to import and test the main application
            from src.main import BadaBoomBooksApp
            from src.models import ProcessingArgs
            
            # Create a test instance
            app_instance = BadaBoomBooksApp()
            
            return jsonify({
                'status': 'success',
                'message': 'BadaBoomBooks integration is working',
                'mode': 'real_processing',
                'components': {
                    'main_app': 'imported successfully',
                    'models': 'imported successfully',
                    'processors': 'available'
                }
            })
        else:
            return jsonify({
                'status': 'warning',
                'message': 'BadaBoomBooks core modules not available - using simulation mode',
                'mode': 'simulation',
                'components': {
                    'main_app': 'not available',
                    'models': 'fallback classes',
                    'processors': 'simulation only'
                }
            })
        
    except Exception as e:
        log.error(f"Test processing error: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e),
            'mode': 'error'
        }), 500

if __name__ == '__main__':
    mode_text = "Real Processing Integration" if CORE_AVAILABLE else "Simulation Mode"
    print(f"🌐 Starting BadaBoomBooks Web Interface - {mode_text}")
    print("📁 Available on: http://localhost:5001")
    
    if CORE_AVAILABLE:
        print("🔥 This version integrates with the actual BadaBoomBooks application")
        print("⚙️  Test the integration at: http://localhost:5001/test_processing")
    else:
        print("⚠️  Running in simulation mode - core modules not available")
        print("   Install the full BadaBoomBooks application for real processing")
    
    app.run(host='0.0.0.0', port=5001, debug=True, threaded=True)