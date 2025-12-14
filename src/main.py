"""
Main application entry point.

This module contains the main application logic that coordinates
all the other modules to provide the complete audiobook processing functionality.
"""

import sys
import configparser
import logging as log
from pathlib import Path
from typing import List, Tuple, Optional

from .config import setup_logging, setup_environment, config_file, opf_template, SCRAPER_REGISTRY
from .models import BookMetadata, ProcessingResult, ProcessingArgs
from .ui import CLIHandler, ProgressReporter, OutputFormatter
from .search import AutoSearchEngine, ManualSearchHandler
from .scrapers import AudibleScraper, GoodreadsScraper, LubimyczytacScraper
from .processors import FileProcessor, MetadataProcessor, AudioProcessor
from .utils import encode_for_config, decode_from_config, detect_url_site


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
        
        # Configuration
        self.config = configparser.ConfigParser()
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
            # Parse and validate arguments
            processing_args = self.cli.parse_args(args)

            # Handle LLM connection test early (before validation)
            if processing_args.llm_conn_test:
                # Setup environment for config loading
                setup_environment()
                from .search.llm_scoring import test_llm_connection
                success = test_llm_connection()
                return 0 if success else 1

            validation_errors = self.cli.validate_args(processing_args)

            if validation_errors:
                self.cli.handle_validation_errors(validation_errors, processing_args.yolo)
                return 1

            # Setup environment and logging
            setup_environment()
            setup_logging(processing_args.debug)

            # Show banner
            self.cli.print_banner()

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
    
    def _initialize_processors(self, args: ProcessingArgs):
        """Initialize all processor instances."""
        self.file_processor = FileProcessor(args)
        self.metadata_processor = MetadataProcessor(args.dry_run)
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
        folders.extend(args.folders)
        
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
        """Process all folders and return exit code."""
        self.progress.start_processing(len(folders))
        
        try:
            # Build processing queue
            queue_success = self._build_processing_queue(folders, args)
            if not queue_success:
                return 1
            
            # Process the queue
            process_success = self._process_queue(args)
            
            # Show final summary
            self.progress.show_final_summary(self.result)
            
            # Determine exit code
            if self.result.has_failures():
                print("\n⚠️  Some books failed to process. Check the log for details.")
                if not args.yolo:
                    input("Press enter to exit...")
                return 1
            else:
                print("\n✅ Processing completed successfully!")
                if not args.yolo:
                    input("Press enter to exit...")
                return 0
                
        except Exception as e:
            log.error(f"Error during processing: {e}")
            print(f"Processing error: {e}")
            return 1
    
    def _build_processing_queue(self, folders: List[Path], args: ProcessingArgs) -> bool:
        """Build the processing queue by gathering URLs for each folder."""
        print('\n===================================== QUEUE BUILDING ====================================')
        
        for i, folder in enumerate(folders):
            self.progress.start_book(BookMetadata.create_empty(str(folder)), i)
            
            try:
                # Check for existing OPF file if requested
                if args.from_opf:
                    opf_file = folder / 'metadata.opf'
                    if opf_file.exists():
                        self._add_opf_to_queue(folder)
                        self.progress.finish_book(True)
                        continue
                
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
        book_info = self._extract_book_info(folder)
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
        book_info = self._extract_book_info(folder)
        
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
    
    def _extract_book_info(self, folder: Path) -> dict:
        """Extract current book information for context display."""
        book_info = {
            'folder_name': folder.name,
            'source': 'folder name'
        }
        
        try:
            # Try to read existing OPF file first
            opf_file = folder / 'metadata.opf'
            if opf_file.exists():
                book_info.update(self._extract_from_opf(opf_file))
                book_info['source'] = 'existing OPF file'
                return book_info
            
            # Try to extract from ID3 tags
            id3_info = self._extract_from_id3_tags(folder)
            if id3_info:
                book_info.update(id3_info)
                book_info['source'] = 'ID3 tags'
                return book_info
                
        except Exception as e:
            log.debug(f"Error extracting book info from {folder}: {e}")
        
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
                metadata = BookMetadata.create_empty(str(folder_path.name), url_or_marker)
                
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
        opf_file = folder_path / 'metadata.opf'
        opf_metadata = self.metadata_processor.read_opf_metadata(opf_file)
        
        if opf_metadata.failed:
            return opf_metadata
        
        print(f"Read metadata from OPF for {metadata.input_folder}")
        
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


def main():
    """Main entry point for the application."""
    app = BadaBoomBooksApp()
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
