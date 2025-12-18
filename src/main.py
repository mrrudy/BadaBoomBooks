"""
Main application entry point.

This module contains the main application logic that coordinates
all the other modules to provide the complete audiobook processing functionality.
"""

import sys
import configparser
import logging as log
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional

from .config import setup_logging, setup_environment, config_file, opf_template, SCRAPER_REGISTRY
from .models import BookMetadata, ProcessingResult, ProcessingArgs
from .ui import CLIHandler, ProgressReporter, OutputFormatter
from .search import AutoSearchEngine, ManualSearchHandler
from .scrapers import AudibleScraper, GoodreadsScraper, LubimyczytacScraper
from .processors import FileProcessor, MetadataProcessor, AudioProcessor
from .utils import encode_for_config, decode_from_config, detect_url_site, find_metadata_opf
from .queue_manager import QueueManager, huey

class BadaBoomBooksApp:
    """Main application class that coordinates all processing."""
    
    def __init__(self):
        self.cli = CLIHandler()
        self.progress = ProgressReporter()
        self.result = ProcessingResult()

        # Processors
        self.file_processor = None
        self.metadata_processor = None
        self.audio_processor = None

        # Search engines
        self.auto_search = None
        self.manual_search = ManualSearchHandler()

        # Queue system for parallel processing
        self.queue_manager = QueueManager()

        # Configuration (legacy queue.ini support)
        # Use only colon as delimiter to avoid conflicts with base64 '=' padding
        self.config = configparser.ConfigParser(delimiters=(':',))
        self.config.optionxform = lambda option: option
        self.config['urls'] = {}
    
    def run(self, args: List[str] = None) -> int:
        """
        Main application entry point.
        
        Args:
            args: Command line arguments (for testing)
            
        Returns:
            Exit code (0 for success, 1 for error)
        """
        try:
            # Parse arguments
            processing_args = self.cli.parse_args(args)

            # Handle LLM connection test early (before validation)
            if processing_args.llm_conn_test:
                # Setup environment for config loading
                setup_environment()
                from .search.llm_scoring import test_llm_connection
                success = test_llm_connection()
                return 0 if success else 1

            # Setup environment and logging early (needed for resume check)
            setup_environment()
            setup_logging(processing_args.debug)

            # Show banner
            self.cli.print_banner()

            # Check for incomplete jobs BEFORE validation (resume logic)
            # When resuming, args are loaded from database, so validation can be skipped
            if processing_args.resume or not processing_args.yolo:
                incomplete_jobs = self.queue_manager.get_incomplete_jobs()
                if incomplete_jobs and len(incomplete_jobs) > 0:
                    print(f"\n⚠️  Found {len(incomplete_jobs)} incomplete job(s) from previous run:")
                    for i, job in enumerate(incomplete_jobs[:3]):  # Show max 3
                        created = job['created_at']
                        status = job['status']
                        print(f"  {i+1}. Job {job['id'][:8]}... ({created}) - Status: {status}")

                    if processing_args.resume:
                        print("\n🔄 Auto-resuming most recent incomplete job (--resume flag)...")
                        return self._resume_job(incomplete_jobs[0], processing_args)
                    elif not processing_args.yolo:
                        resume = input("\nResume most recent incomplete job? (y/n): ").lower().strip() == 'y'
                        if resume:
                            return self._resume_job(incomplete_jobs[0], processing_args)
                elif processing_args.resume:
                    # User explicitly requested resume but no incomplete jobs found
                    print("\n✅ No incomplete jobs to resume. All previous jobs are complete.")
                    if not processing_args.yolo:
                        input("Press enter to exit...")
                    return 0

            # Validate arguments (only for new jobs, not resume)
            validation_errors = self.cli.validate_args(processing_args)

            if validation_errors:
                self.cli.handle_validation_errors(validation_errors, processing_args.yolo)
                return 1

            # Check LLM availability if needed for genre categorization
            # Note: --llm-select enables LLM for both candidate selection AND genre mapping
            if processing_args.llm_select:
                if not self._check_llm_for_genre_categorization():
                    print("\n❌ LLM is not available but --llm-select flag is set.")
                    print("   LLM is required for intelligent genre categorization.")
                    print("   Either configure LLM in .env file or run without --llm-select flag.")
                    if not processing_args.yolo:
                        input("Press enter to exit...")
                    return 1

            # Initialize processors
            self._initialize_processors(processing_args)

            # Discover folders to process
            folders = self._discover_folders(processing_args)
            
            if not folders:
                print("No audiobook folders found to process.")
                if not processing_args.yolo:
                    input("Press enter to exit...")
                return 1

            # Show processing plan
            plan = OutputFormatter.format_processing_plan(folders, processing_args)
            print(f"\n{plan}")

            # Confirm processing
            if not self.cli.confirm_processing(folders, processing_args.dry_run, processing_args.yolo):
                print("Processing cancelled by user.")
                return 0
            
            # Process all folders
            return self._process_all_folders(folders, processing_args)
            
        except KeyboardInterrupt:
            print("\n\nProcessing interrupted by user.")
            return 1
        except Exception as e:
            log.error(f"Unexpected error: {e}")
            print(f"\nUnexpected error: {e}")
            return 1
    
    def _check_llm_for_genre_categorization(self) -> bool:
        """
        Check if LLM is available for genre categorization.

        Returns:
            True if LLM is available, False otherwise.
        """
        try:
            from .utils.genre_normalizer import GenreNormalizer

            log.info("Testing LLM connection for genre categorization...")
            test_normalizer = GenreNormalizer(use_llm=True)

            return test_normalizer.llm_available

        except Exception as e:
            log.error(f"Failed to initialize LLM for genre categorization: {e}")
            return False

    def _initialize_processors(self, args: ProcessingArgs):
        """Initialize all processor instances."""
        self.file_processor = FileProcessor(args)
        self.metadata_processor = MetadataProcessor(args.dry_run, use_llm=args.llm_select)
        self.audio_processor = AudioProcessor(args.dry_run)

        if args.auto_search:
            self.auto_search = AutoSearchEngine(
                debug_enabled=args.debug,
                enable_ai_selection=args.llm_select,
                yolo=args.yolo
            )
    
    def _discover_folders(self, args: ProcessingArgs) -> List[Path]:
        """Discover all folders to process."""
        folders = []

        # Add folders from book root
        if args.book_root:
            discovered = self.cli.discover_folders_from_book_root(args.book_root)
            folders.extend(discovered)
            print(f"Discovered {len(discovered)} audiobook folders in {args.book_root}")

        # Add explicitly specified folders
        # If a folder contains audio files only in subdirectories (e.g., author folders),
        # discover the actual audiobook folders within it
        for folder in args.folders:
            # Check if audio files are directly in this folder
            from .utils import find_audio_files
            audio_files_in_folder = find_audio_files(folder)

            if audio_files_in_folder:
                # Check if audio files are ALL in subdirectories (not in root)
                audio_in_root = any(f.parent == folder for f in audio_files_in_folder)

                if not audio_in_root:
                    # This is a parent folder (like author folder) - discover subfolders
                    log.info(f"Folder {folder.name} contains audio files only in subdirectories, discovering audiobook folders...")
                    discovered = self.cli.discover_folders_from_book_root(folder)
                    folders.extend(discovered)
                    print(f"Discovered {len(discovered)} audiobook folders in {folder.name}")
                else:
                    # Audio files in root - this is an audiobook folder
                    folders.append(folder)
            else:
                # No audio files at all - add anyway, will fail validation later
                folders.append(folder)

        # Remove duplicates while preserving order
        unique_folders = []
        seen = set()
        for folder in folders:
            folder_resolved = folder.resolve()
            if folder_resolved not in seen:
                unique_folders.append(folder_resolved)
                seen.add(folder_resolved)

        return unique_folders
    
    def _process_all_folders(self, folders: List[Path], args: ProcessingArgs) -> int:
        """Process all folders using parallel queue system with two-phase task creation."""
        print('\n===================================== IDENTIFICATION ====================================')

        job_id = None
        try:
            # Create job in database
            job_id = self.queue_manager.create_job(args)
            self.queue_manager.update_job_status(job_id, 'planning', started_at=datetime.now().isoformat())

            log.info(f"Created job {job_id} with {len(folders)} folders")

            # Phase 1: Identification - Create tasks for all folders (fast, no URL discovery yet)
            try:
                for i, folder in enumerate(folders):
                    print(f"\r[{i+1}/{len(folders)}] Identifying books for processing...    ", end='', flush=True)

                    try:
                        # Create task without URL (URL will be discovered later)
                        # URL is set to None initially, workers will discover it
                        self.queue_manager.create_task(job_id, folder, url=None)
                        log.debug(f"Identified {folder.name} for processing")

                    except Exception as e:
                        log.error(f"Error identifying {folder}: {e}")

                print()  # Newline after progress

            except KeyboardInterrupt:
                # Identification interrupted - discard incomplete job
                print("\n\n⚠️  Identification interrupted. Discarding incomplete job...")
                self.queue_manager.delete_job(job_id)
                raise  # Re-raise to exit application

            # Get task count
            progress = self.queue_manager.get_job_progress(job_id)
            total_tasks = progress.get('total', 0)

            if total_tasks == 0:
                print("\n⚠️  No books queued for processing.")
                if not args.yolo:
                    input("Press enter to exit...")
                return 1

            print(f"\n✓ Identified {total_tasks} books for processing")

            # Phase 2: Processing (workers will discover URLs and process books in parallel)
            self.queue_manager.update_job_status(job_id, 'processing')

            # Initialize processors (needed for URL discovery in workers)
            self._initialize_processors(args)

            # Start worker threads
            print(f"\n🚀 Starting {args.workers} parallel workers...")
            self._start_workers(args.workers)

            # Enqueue all tasks to Huey
            self.queue_manager.enqueue_all_tasks(job_id)

            # Monitor progress and wait for completion
            return self._monitor_job_progress(job_id, args)

        except Exception as e:
            log.error(f"Error during processing: {e}", exc_info=True)
            print(f"\n❌ Processing error: {e}")
            return 1
    
    def _get_url_for_folder(self, folder: Path, args: ProcessingArgs) -> Optional[str]:
        """
        Get URL or marker for a single folder.

        Args:
            folder: Folder to process
            args: Processing arguments

        Returns:
            URL string, 'OPF' marker, or None if skipped
        """
        try:
            # Check for existing OPF file if requested (but not if force refresh)
            if args.from_opf and not args.force_refresh:
                opf_file = find_metadata_opf(folder)
                if opf_file:
                    log.info(f"Using existing OPF for {folder.name}")
                    return 'OPF'

            # If force_refresh is set, treat OPF as search source
            if args.force_refresh:
                opf_file = find_metadata_opf(folder)
                if opf_file:
                    # Read OPF to get title/author/source for searching
                    temp_metadata = self.metadata_processor.read_opf_metadata(opf_file)

                    if temp_metadata.url:
                        # Use source URL from OPF for re-scraping
                        log.info(f"Force refreshing from source URL: {temp_metadata.url}")
                        return temp_metadata.url
                    else:
                        # No source URL - fall through to normal search
                        log.warning(f"No source URL in OPF for {folder.name}, performing search")

            # Use auto-search or manual search
            if args.auto_search:
                from .utils import generate_search_term

                # Extract current book information for context
                book_info = self._extract_book_info(folder, args.book_root)

                # Generate search term
                if book_info.get('title') and book_info.get('author'):
                    search_term = f"{book_info['title']} by {book_info['author']}"
                elif book_info.get('title'):
                    search_term = book_info['title']
                elif book_info.get('author'):
                    search_term = f"{folder.name} by {book_info['author']}"
                else:
                    search_term = generate_search_term(folder)

                # Determine sites to search
                if args.site == 'all':
                    site_keys = list(SCRAPER_REGISTRY.keys())
                else:
                    site_keys = [args.site]

                # Perform search
                site_key, url, html = self.auto_search.search_and_select_with_context(
                    search_term, site_keys, book_info, args.search_limit, args.download_limit, args.search_delay
                )

                if site_key and url:
                    log.info(f"Auto-search found {SCRAPER_REGISTRY[site_key]['domain']}: {url}")
                    return url
                else:
                    log.info(f"Auto-search failed for {folder.name}, skipping")
                    return None

            else:
                # Manual search
                book_info = self._extract_book_info(folder, args.book_root)
                site_key, url = self.manual_search.handle_manual_search_with_context(folder, book_info, args.site)

                if site_key and url:
                    return url
                else:
                    return None

        except Exception as e:
            log.error(f"Error getting URL for {folder}: {e}")
            return None

    def _build_processing_queue(self, folders: List[Path], args: ProcessingArgs) -> bool:
        """Build the processing queue by gathering URLs for each folder (LEGACY - kept for compatibility)."""
        print('\n===================================== QUEUE BUILDING ====================================')
        
        for i, folder in enumerate(folders):
            self.progress.start_book(BookMetadata.create_empty(str(folder)), i)
            
            try:
                # Check for existing OPF file if requested (but not if force refresh)
                if args.from_opf and not args.force_refresh:
                    opf_file = find_metadata_opf(folder)
                    if opf_file:
                        self._add_opf_to_queue(folder)
                        self.progress.finish_book(True)
                        continue

                # If force_refresh is set, treat OPF as search source
                if args.force_refresh:
                    opf_file = find_metadata_opf(folder)
                    if opf_file:
                        # Read OPF to get title/author/source for searching
                        temp_metadata = self.metadata_processor.read_opf_metadata(opf_file)

                        if temp_metadata.url:
                            # Use source URL from OPF for re-scraping
                            self._add_url_to_queue(folder, temp_metadata.url)
                            self.progress.finish_book(True)
                            continue
                        else:
                            # No source URL - fall through to normal search
                            log.warning(f"No source URL in OPF for {folder.name}, performing search")

                # Use auto-search or manual search
                if args.auto_search:
                    success = self._auto_search_for_folder(folder, args)
                else:
                    success = self._manual_search_for_folder(folder, args)
                
                if success:
                    self.progress.finish_book(True)
                else:
                    self.result.add_skipped(folder.name)
                    self.progress.finish_book(False, "Skipped by user")
                
            except Exception as e:
                log.error(f"Error building queue for {folder}: {e}")
                self.result.add_failure(folder.name, str(e))
                self.progress.finish_book(False, str(e))
        
        # Save queue configuration
        self._save_queue_config()
        return True
    
    def _auto_search_for_folder(self, folder: Path, args: ProcessingArgs) -> bool:
        """Perform auto-search for a folder."""
        from .utils import generate_search_term
        
        # Extract current book information for context
        book_info = self._extract_book_info(folder, args.book_root)
        
        # Generate search term using book_info if available
        if book_info.get('title') and book_info.get('author'):
            search_term = f"{book_info['title']} by {book_info['author']}"
        elif book_info.get('title'):
            search_term = book_info['title']
        elif book_info.get('author'):
            search_term = f"{folder.name} by {book_info['author']}"
        else:
            search_term = generate_search_term(folder)
        
        self.progress.report_search_progress(search_term, "auto")
        
        # Determine sites to search
        if args.site == 'all':
            site_keys = list(SCRAPER_REGISTRY.keys())
        else:
            site_keys = [args.site]
        
        # Perform search with book context
        site_key, url, html = self.auto_search.search_and_select_with_context(
            search_term, site_keys, book_info, args.search_limit, args.download_limit, args.search_delay
        )
        
        if site_key and url:
            self._add_url_to_queue(folder, url)
            print(f"Selected {SCRAPER_REGISTRY[site_key]['domain']} URL: {url}")
            return True
        else:
            print("Auto search failed, skipping book.")
            return False
    
    def _manual_search_for_folder(self, folder: Path, args: ProcessingArgs) -> bool:
        """Perform manual search for a folder."""
        # Extract current book information for context
        book_info = self._extract_book_info(folder, args.book_root)
        
        site_key, url = self.manual_search.handle_manual_search_with_context(folder, book_info, args.site)
        
        if site_key and url:
            self._add_url_to_queue(folder, url)
            return True
        else:
            return False
    
    def _add_url_to_queue(self, folder: Path, url: str):
        """Add URL to processing queue."""
        b64_folder = encode_for_config(str(folder.resolve()))
        b64_url = encode_for_config(url)
        self.config['urls'][b64_folder] = b64_url
    
    def _add_opf_to_queue(self, folder: Path):
        """Add OPF marker to processing queue."""
        b64_folder = encode_for_config(str(folder.resolve()))
        b64_url = encode_for_config('OPF')
        self.config['urls'][b64_folder] = b64_url
        print(f"Queued OPF metadata for {folder.name}")
    
    def _extract_book_info(self, folder: Path, book_root: Optional[Path] = None) -> dict:
        """Extract current book information for context display.

        Args:
            folder: The audiobook folder to extract info from
            book_root: If provided (when using -R flag), will attempt to extract
                      author from parent directory when no author is found in metadata
        """
        
        book_info = {
            'folder_name': folder.name,
            'source': 'folder name'
        }

        try:
            # Try to read existing OPF file first
            opf_file = find_metadata_opf(folder)
            if opf_file:
                opf_info = self._extract_from_opf(opf_file)
                book_info.update(opf_info)
                book_info['source'] = 'existing OPF file'
                # If OPF provided author, return early (author found)
                if 'author' in opf_info and opf_info['author']:
                    return book_info
            
            # Try to extract from ID3 tags if no author found yet
            if 'author' not in book_info:
                id3_info = self._extract_from_id3_tags(folder)
                if id3_info:
                    book_info.update(id3_info)
                    book_info['source'] = 'ID3 tags' if book_info.get('source') == 'folder name' else book_info['source']
                    # If ID3 provided author, return early (author found)
                    if 'author' in id3_info and id3_info['author']:
                        return book_info
                
        except Exception as e:
            log.debug(f"Error extracting book info from {folder}: {e}")

        # If -R flag was used and no author was found, try parent directory
        
        if book_root is not None and 'author' not in book_info:
            
            try:
                parent_dir = folder.parent
                
                
                # Resolve both paths to handle UNC vs drive letter issues
                parent_resolved = parent_dir.resolve()
                root_resolved = book_root.resolve()
                
                
                # Extract author from parent if parent is book_root or within book_root
                # This handles structures like: -R "Author/" discovers "Author/Book"
                # or -R "Root/" discovers "Root/Author/Book"
                try:
                    is_within_root = parent_resolved.is_relative_to(root_resolved)
                except AttributeError:
                    # Python < 3.9 compatibility
                    is_within_root = root_resolved in parent_resolved.parents or parent_resolved == root_resolved
                
                if is_within_root:
                    book_info['author'] = parent_dir.name
                    
                    log.debug(f"Extracted author '{parent_dir.name}' from parent directory for {folder.name}")
                
            except Exception as e:
                log.debug(f"Error extracting author from parent directory for {folder}: {e}")

        
        return book_info
    
    def _extract_from_opf(self, opf_file: Path) -> dict:
        """Extract metadata from existing OPF file."""
        info = {}
        
        try:
            from xml.etree import ElementTree as ET
            
            tree = ET.parse(opf_file)
            root = tree.getroot()
            
            # Define namespace
            ns = {'dc': 'http://purl.org/dc/elements/1.1/',
                  'opf': 'http://www.idpf.org/2007/opf'}
            
            # Extract basic metadata
            title_elem = root.find('.//dc:title', ns)
            if title_elem is not None and title_elem.text:
                info['title'] = title_elem.text.strip()
            
            creator_elem = root.find('.//dc:creator', ns)
            if creator_elem is not None and creator_elem.text:
                info['author'] = creator_elem.text.strip()
            
            # Extract series info from meta tags
            for meta in root.findall('.//opf:meta', ns):
                name = meta.get('name', '')
                content = meta.get('content', '')
                
                if name == 'calibre:series' and content:
                    info['series'] = content.strip()
                elif name == 'calibre:series_index' and content:
                    info['volume'] = content.strip()
            
            # Extract other metadata
            publisher_elem = root.find('.//dc:publisher', ns)
            if publisher_elem is not None and publisher_elem.text:
                info['publisher'] = publisher_elem.text.strip()
            
            date_elem = root.find('.//dc:date', ns)
            if date_elem is not None and date_elem.text:
                date_text = date_elem.text.strip()
                # Extract year from date
                import re
                year_match = re.search(r'(\d{4})', date_text)
                if year_match:
                    info['year'] = year_match.group(1)
            
            language_elem = root.find('.//dc:language', ns)
            if language_elem is not None and language_elem.text:
                info['language'] = language_elem.text.strip()
                
        except Exception as e:
            log.debug(f"Error parsing OPF file {opf_file}: {e}")
        
        return info
    
    def _extract_from_id3_tags(self, folder: Path) -> dict:
        """Extract metadata from ID3 tags in audio files."""
        info = {}
        
        try:
            from tinytag import TinyTag
            
            # Find the first audio file
            audio_files = []
            for ext in ['.mp3', '.m4a', '.m4b', '.flac', '.ogg', '.wma']:
                audio_files.extend(folder.glob(f'*{ext}'))
                if audio_files:
                    break
            
            if not audio_files:
                return info
            
            # Read metadata from first audio file
            first_file = audio_files[0]
            tag = TinyTag.get(str(first_file))
            
            if tag.title:
                info['title'] = tag.title.strip()
            if tag.album and tag.album != tag.title:
                if 'title' not in info:
                    info['title'] = tag.album.strip()
                else:
                    # Use album as series if different from title
                    info['series'] = tag.album.strip()
            
            if tag.artist:
                info['author'] = tag.artist.strip()
            
            if tag.albumartist and tag.albumartist != tag.artist:
                if 'author' not in info:
                    info['author'] = tag.albumartist.strip()
            
            if hasattr(tag, 'year') and tag.year:
                info['year'] = str(tag.year)
            
            # Try to extract narrator from comment or other fields
            if hasattr(tag, 'comment') and tag.comment:
                comment = tag.comment.lower()
                if 'narrated by' in comment or 'narrator' in comment:
                    # Simple extraction - could be enhanced
                    import re
                    narrator_match = re.search(r'(?:narrated by|narrator:?)\s*([^,\n]+)', comment, re.IGNORECASE)
                    if narrator_match:
                        info['narrator'] = narrator_match.group(1).strip()
                        
        except ImportError:
            log.debug("TinyTag not available for ID3 extraction")
        except Exception as e:
            log.debug(f"Error extracting ID3 tags from {folder}: {e}")
        
        return info
    
    def _save_queue_config(self):
        """Save the processing queue to configuration file."""
        with config_file.open('w', encoding='utf-8') as file:
            self.config.write(file)
        log.debug(f"Saved queue configuration to {config_file}")
    
    def _process_queue(self, args: ProcessingArgs) -> bool:
        """Process all items in the queue."""
        print('\n===================================== PROCESSING ====================================')
        
        # Read configuration
        self.config.read(config_file, encoding='utf-8')
        
        # Get only the URLs section items
        if 'urls' not in self.config:
            log.warning("No 'urls' section found in config file")
            return True
        
        url_items = list(self.config['urls'].items())
        log.debug(f"Raw config items count: {len(url_items)}")
        
        # Filter out any non-base64 entries that might be config metadata
        valid_items = []
        for key, value in url_items:
            try:
                # Test if both key and value are valid base64
                decode_from_config(key)
                decode_from_config(value) 
                valid_items.append((key, value))
            except Exception as e:
                log.warning(f"Skipping invalid config entry: {key[:50]}... Error: {e}")
        
        log.debug(f"Processing {len(valid_items)} valid items from queue (filtered from {len(url_items)} total)")
        
        for i, (key, value) in enumerate(valid_items):
            try:
                log.debug(f"Processing item {i+1}/{len(valid_items)}: {key[:50]}...")
                
                # Decode folder and URL (already validated in filter above)
                folder_path = Path(decode_from_config(key))
                url_or_marker = decode_from_config(value)
                
                # Create metadata object
                metadata = BookMetadata.create_empty(str(folder_path), url_or_marker)
                
                self.progress.start_book(metadata, i)
                
                # Process the book
                success = self._process_single_book(metadata, folder_path, url_or_marker, args)
                
                if success and not metadata.failed and not metadata.skip:
                    details = f"{metadata.get_safe_author()}/{metadata.get_safe_title()}"
                    self.result.add_success(metadata.input_folder, details)
                    self.progress.finish_book(True)
                elif metadata.skip:
                    self.result.add_skipped(metadata.input_folder)
                    self.progress.finish_book(False, "Skipped")
                else:
                    self.result.add_failure(metadata.input_folder, metadata.failed_exception)
                    self.progress.finish_book(False, metadata.failed_exception)
                
            except Exception as e:
                log.error(f"Error processing queue item {key}: {e}")
                folder_name = "Unknown"
                try:
                    folder_name = Path(decode_from_config(key)).name
                except:
                    pass
                self.result.add_failure(folder_name, str(e))
                self.progress.finish_book(False, str(e))
        
        return True
    
    def _process_single_book(self, metadata: BookMetadata, folder_path: Path, 
                           url_or_marker: str, args: ProcessingArgs) -> bool:
        """Process a single book through the complete pipeline."""
        
        metadata.input_folder = str(folder_path)
        
        try:
            # Step 1: Scrape metadata
            if url_or_marker == "OPF":
                metadata = self._read_opf_metadata(folder_path, metadata)
            else:
                metadata.url = url_or_marker
                metadata = self._scrape_metadata(metadata)
            
            if metadata.failed or metadata.skip:
                return False
            
            # Step 2: Organize files
            if args.copy or args.move:
                self.progress.report_file_operation("organize", folder_path)
                if not self.file_processor.process_folder_organization(metadata):
                    return False
            else:
                metadata.final_output = folder_path
            
            # Step 3: Process files
            if args.flatten:
                self.progress.report_file_operation("flatten", metadata.final_output)
                if not self.file_processor.flatten_folder(metadata):
                    return False
            
            if args.rename:
                self.progress.report_file_operation("rename", metadata.final_output)
                if not self.file_processor.rename_audio_tracks(metadata):
                    return False
            
            # Step 4: Generate metadata files
            if args.opf:
                self.progress.report_metadata_operation("Creating", "metadata.opf")
                if not self.metadata_processor.create_opf_file(metadata, opf_template):
                    return False
            
            if args.infotxt:
                self.progress.report_metadata_operation("Creating", "info.txt")
                if not self.metadata_processor.create_info_file(metadata):
                    return False
            
            if args.cover:
                self.progress.report_metadata_operation("Downloading", "cover image")
                self.metadata_processor.download_cover_image(metadata)
            
            # Step 5: Update audio tags
            if args.id3_tag:
                self.progress.report_metadata_operation("Updating", "ID3 tags")
                if not self.audio_processor.update_id3_tags(metadata):
                    return False
            
            # Display final metadata summary
            summary = OutputFormatter.format_metadata_summary(metadata)
            print(f"\n{summary}\n")
            
            return True
            
        except Exception as e:
            log.error(f"Error processing {metadata.input_folder}: {e}")
            metadata.mark_as_failed(str(e))
            return False
    
    def _read_opf_metadata(self, folder_path: Path, metadata: BookMetadata) -> BookMetadata:
        """Read metadata from OPF file."""
        opf_file = find_metadata_opf(folder_path)
        if not opf_file:
            log.error(f"No metadata.opf found in {folder_path}")
            metadata.mark_as_failed(f"No metadata.opf found")
            return metadata

        opf_metadata = self.metadata_processor.read_opf_metadata(opf_file)

        if opf_metadata.failed:
            return opf_metadata

        print(f"Read metadata from OPF for {metadata.input_folder}")

        # Normalize genres with LLM if enabled (even if not writing OPF)
        # This allows building genre mappings with --from-opf --llm-select
        if self.metadata_processor.use_llm and opf_metadata.genres:
            try:
                from .utils.genre_normalizer import normalize_genres
                genre_list = opf_metadata.get_genres_list()
                normalized_genres = normalize_genres(genre_list, use_llm=True)
                opf_metadata.genres = ','.join(normalized_genres)
                log.debug(f"Normalized genres with LLM: {normalized_genres}")
            except Exception as e:
                log.error(f"Failed to normalize genres with LLM: {e}")
                opf_metadata.mark_as_failed(f"LLM genre categorization failed: {e}")
                return opf_metadata

        # If URL is present in OPF, try to scrape missing fields
        if opf_metadata.url:
            self.progress.report_scraping_progress(opf_metadata.url, "supplement")
            scraped_metadata = self._scrape_metadata(opf_metadata)

            # Merge scraped data into OPF data (OPF takes precedence)
            for field in ['summary', 'genres', 'cover_url', 'language']:
                if not getattr(opf_metadata, field) and getattr(scraped_metadata, field):
                    setattr(opf_metadata, field, getattr(scraped_metadata, field))

        return opf_metadata
    
    def _scrape_metadata(self, metadata: BookMetadata) -> BookMetadata:
        """Scrape metadata from URL."""
        site_key = detect_url_site(metadata.url)
        if not site_key:
            metadata.mark_as_failed(f"Unsupported URL: {metadata.url}")
            return metadata
        
        self.progress.report_scraping_progress(metadata.url, site_key)
        
        try:
            # Get scraper configuration
            config = SCRAPER_REGISTRY[site_key]
            
            # Preprocess URL if needed
            if site_key == 'audible':
                from .scrapers.base import preprocess_audible_url
                preprocess_audible_url(metadata)
            
            # Make HTTP request
            if site_key == 'audible':
                from .scrapers.base import http_request_audible_api
                metadata, response = http_request_audible_api(metadata, log)
            else:
                from .scrapers.base import http_request_generic  
                metadata, response = http_request_generic(metadata, log)
            
            if metadata.failed:
                return metadata
            
            # Scrape metadata
            if site_key == 'audible':
                # Use new modular Audible scraper
                scraper = AudibleScraper()
                metadata = scraper.scrape_metadata(metadata, response, log)
            elif site_key == 'goodreads':
                # Use new modular Goodreads scraper
                scraper = GoodreadsScraper()
                metadata = scraper.scrape_metadata(metadata, response, log)
            elif site_key == 'lubimyczytac':
                # Use new modular LubimyCzytac scraper
                scraper = LubimyczytacScraper()
                metadata = scraper.scrape_metadata(metadata, response, log)
            
        except Exception as e:
            log.error(f"Error scraping {metadata.url}: {e}")
            metadata.mark_as_failed(f"Scraping error: {e}")
        
        return metadata

    def _start_workers(self, num_workers: int):
        """
        Start Huey consumer with multiple workers.

        Note: We start ONE consumer with N workers, not N consumers with 1 worker each.
        Huey's Consumer is designed to manage a pool of worker threads internally.
        """
        log.info(f"Starting Huey consumer with {num_workers} worker threads...")

        # Start single consumer thread with worker pool
        consumer_thread = threading.Thread(
            target=self._run_huey_consumer,
            args=(num_workers,),
            name="HueyConsumer",
            daemon=True
        )
        consumer_thread.start()

        log.info(f"✓ Started consumer with {num_workers} workers")

    def _run_huey_consumer(self, num_workers: int):
        """
        Run Huey consumer with worker pool.

        Args:
            num_workers: Number of worker threads in the pool
        """
        try:
            from huey.consumer import Consumer

            # Create consumer with worker pool
            # The consumer manages multiple worker threads internally
            consumer = Consumer(
                huey,
                workers=num_workers,  # Worker pool size
                periodic=False,       # Disable periodic task scheduler
                check_worker_health=True,
                worker_type='thread'  # Use threads (not processes)
            )

            log.info(f"Huey consumer running with {num_workers} workers")
            consumer.run()

        except Exception as e:
            log.error(f"Consumer error: {e}", exc_info=True)

    def _monitor_job_progress(self, job_id: str, args: ProcessingArgs) -> int:
        """
        Monitor job progress and show real-time updates.

        Args:
            job_id: Job ID to monitor
            args: Processing arguments

        Returns:
            Exit code (0 for success, 1 for failures)
        """
        print('\n===================================== PROCESSING ====================================')

        last_running = 0
        last_completed = 0
        last_failed = 0
        last_enqueue_check = 0
        enqueue_check_interval = 30  # Check for new pending tasks every 30 iterations (~9 seconds)

        iteration = 0
        while True:
            progress = self.queue_manager.get_job_progress(job_id)

            total = progress.get('total', 0)
            completed = progress.get('completed', 0)
            failed = progress.get('failed', 0)
            skipped = progress.get('skipped', 0)
            running = progress.get('running', 0)
            pending = progress.get('pending', 0)

            # Periodically check for and enqueue new pending tasks
            # This handles the case where another process (discovery) is still creating tasks
            iteration += 1
            if iteration - last_enqueue_check >= enqueue_check_interval:
                pending_tasks = self.queue_manager.get_pending_tasks(job_id)
                if pending_tasks:
                    # Enqueue any tasks that haven't been queued yet
                    log.info(f"Found {len(pending_tasks)} pending tasks, enqueueing...")
                    self.queue_manager.enqueue_all_tasks(job_id)
                last_enqueue_check = iteration

            # Show progress if changed
            if running != last_running or completed != last_completed or failed != last_failed:
                percent = ((completed + failed + skipped) / total * 100) if total > 0 else 0
                print(f"\r[{percent:5.1f}%] Completed: {completed} | Failed: {failed} | Running: {running} | Pending: {pending}    ", end='', flush=True)

                last_running = running
                last_completed = completed
                last_failed = failed

            # Check if done
            if completed + failed + skipped >= total:
                print()  # Newline after progress
                break

            time.sleep(0.3)

        # Update job status
        self.queue_manager.update_job_status(
            job_id,
            'completed',
            completed_at=datetime.now().isoformat(),
            completed_tasks=completed,
            failed_tasks=failed,
            skipped_tasks=skipped
        )

        # Build result summary
        # Note: Task results are in database, we could fetch them here if needed
        print(f"\n✓ Processing completed: {completed} successful, {failed} failed, {skipped} skipped")

        if failed > 0:
            print(f"\n⚠️  {failed} books failed to process. Check the log for details.")
            if not args.yolo:
                input("Press enter to exit...")
            return 1
        else:
            print("\n✅ All books processed successfully!")
            if not args.yolo:
                input("Press enter to exit...")
            return 0

    def _resume_job(self, job: dict, cli_args: ProcessingArgs) -> int:
        """
        Resume an interrupted job.

        Args:
            job: Job dictionary from database
            cli_args: CLI arguments (for workers count, debug, etc.)

        Returns:
            Exit code
        """
        job_id = job['id']

        print(f"\n🔄 Resuming job {job_id[:8]}...")
        print(f"   Created: {job['created_at']}")
        print(f"   Status: {job['status']}")

        # Load stored args from database
        import json
        stored_args_dict = json.loads(job['args_json'])

        # Convert stored args dict back to ProcessingArgs
        # Use stored args as base, but allow CLI to override workers count
        from pathlib import Path
        stored_args = ProcessingArgs(
            **{k: (Path(v) if k in ['output', 'book_root'] and v else
                  [Path(p) for p in v] if k == 'folders' and v else v)
               for k, v in stored_args_dict.items()}
        )

        # Override workers count if specified in CLI
        if cli_args.workers != 4:  # 4 is default, so user explicitly set it
            stored_args.workers = cli_args.workers

        # Use stored args for processing (includes original yolo, dry_run, etc.)
        args = stored_args

        # Get task statistics
        progress = self.queue_manager.get_job_progress(job_id)
        print(f"   Tasks: {progress['completed']} completed, {progress['failed']} failed, {progress['running']} running, {progress['pending']} pending")

        # Reset any running tasks to pending (workers died)
        cursor = self.queue_manager.connection.cursor()
        cursor.execute("""
            UPDATE tasks SET status = 'pending', started_at = NULL, worker_id = NULL
            WHERE job_id = ? AND status = 'running'
        """, (job_id,))
        running_reset_count = cursor.rowcount
        self.queue_manager.connection.commit()

        # Refresh progress after resetting running tasks
        progress = self.queue_manager.get_job_progress(job_id)
        total_pending = progress['pending']

        # Check if there are any tasks left to process
        if total_pending == 0:
            total = progress['total']
            completed = progress['completed']
            failed = progress['failed']
            skipped = progress['skipped']

            if total > 0 and (completed + failed + skipped >= total):
                # Job is already complete
                print(f"\n✅ Job already complete: {completed} successful, {failed} failed, {skipped} skipped")
                self.queue_manager.update_job_status(job_id, 'completed')
                if not args.yolo:
                    input("Press enter to exit...")
                return 0 if failed == 0 else 1
            else:
                # No tasks to resume
                print(f"\n⚠️  No pending tasks to resume.")
                if not args.yolo:
                    input("Press enter to exit...")
                return 0

        if running_reset_count > 0:
            print(f"   Reset {running_reset_count} interrupted task(s) to pending")

        # Update job status
        self.queue_manager.update_job_status(job_id, 'processing')

        # Initialize processors
        self._initialize_processors(args)

        # Start workers
        self._start_workers(args.workers)

        # Re-enqueue pending tasks
        print(f"\n🔄 Re-enqueueing {total_pending} pending tasks...")
        self.queue_manager.enqueue_all_tasks(job_id)

        # Monitor progress with stored args (includes yolo flag)
        return self._monitor_job_progress(job_id, args)

def main():
    """Main entry point for the application."""
    app = BadaBoomBooksApp()
    return app.run()

if __name__ == "__main__":
    sys.exit(main())
