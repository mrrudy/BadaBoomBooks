"""
Command line interface handler.

This module handles argument parsing, validation, and CLI setup.
"""

import argparse
import sys
from pathlib import Path
from typing import List

from ..config import __version__, SCRAPER_REGISTRY
from ..models import ProcessingArgs
from ..utils import validate_path, has_audio_files


class CLIHandler:
    """Handles command line interface operations."""
    
    def __init__(self):
        self.parser = self._create_parser()
    
    def _create_parser(self) -> argparse.ArgumentParser:
        """Create and configure argument parser."""
        parser = argparse.ArgumentParser(
            prog='python BadaBoomBooks.py',
            formatter_class=argparse.RawTextHelpFormatter,
            description='Organize audiobook folders through webscraping metadata',
            epilog=r"""

1) Call the script and pass it the audiobook folders you would like to process, including any optional arguments...
    python BadaBoomBooks.py "C:\Path\To\Audiobook_folder1" "C:\Path\To\Audiobook_folder2" ...
    python BadaBoomBooks.py --infotxt --opf --rename --series --id3-tag --move -R 'T:\Incoming' -O 'T:\Sorted' 

2) Your browser will open and perform a web search for the current book, simply select the correct web-page and copy the url to your clipboard.

3) After building the queue, the process will start and folders will be organized accordingly. Cheers!
""")
        
        # === INPUT/OUTPUT OPTIONS ===
        parser.add_argument(
            'folders', 
            metavar='folder', 
            nargs='*', 
            help='Audiobook folder(s) to be organized'
        )
        parser.add_argument(
            '-O', 
            dest='output', 
            metavar='OUTPUT', 
            help='Path to place organized folders'
        )
        parser.add_argument(
            '-R', '--book-root',
            dest='book_root',
            metavar='BOOK_ROOT',
            help='Recursively discover audiobook folders from this root directory. When no author metadata is found, will extract author name from parent directory (e.g., "Author/Book" structure).'
        )
        
        # === OPERATION MODE ===
        parser.add_argument(
            '-c', '--copy', 
            action='store_true', 
            help='Copy folders instead of moving them'
        )
        parser.add_argument(
            '-m', '--move', 
            action='store_true', 
            help='Move folders instead of copying them'
        )
        parser.add_argument(
            '-D', '--dry-run', 
            action='store_true', 
            help="Perform a trial run without making any changes to filesystem"
        )
        
        # === PROCESSING OPTIONS ===
        parser.add_argument(
            '-f', '--flatten', 
            action='store_true', 
            help="Flatten book folders, useful if the player has issues with multi-folder books"
        )
        parser.add_argument(
            '-r', '--rename', 
            action='store_true', 
            help="Rename audio tracks to '## - {title}' format"
        )
        parser.add_argument(
            '-S', '--series', 
            action='store_true', 
            help="Include series information in output path (series/volume - title)"
        )
        parser.add_argument(
            '-I', '--id3-tag', 
            action='store_true', 
            help='Update ID3 tags of audio files using scraped metadata'
        )
        
        # === METADATA OPTIONS ===
        parser.add_argument(
            '-i', '--infotxt', 
            action='store_true', 
            help="Generate 'info.txt' file, used by SmartAudioBookPlayer to display book summary"
        )
        parser.add_argument(
            '-o', '--opf', 
            action='store_true', 
            help="Generate 'metadata.opf' file, used by Audiobookshelf to import metadata"
        )
        parser.add_argument(
            '-C', '--cover', 
            action='store_true', 
            help="Download and save cover image as cover.jpg in audiobook folder"
        )
        parser.add_argument(
            '-F', '--from-opf',
            action='store_true',
            help='Read metadata from metadata.opf file if present, fallback to web scraping if not'
        )
        parser.add_argument(
            '--force-refresh',
            action='store_true',
            help='Force re-scraping from web sources even if complete metadata.opf exists (requires dc:source URL in OPF)'
        )

        # === SEARCH OPTIONS ===
        parser.add_argument(
            '-s', '--site', 
            metavar='', 
            default='all', 
            choices=['audible', 'goodreads', 'lubimyczytac', 'all'], 
            help="Specify the site to perform initial searches [audible, goodreads, lubimyczytac, all]"
        )
        parser.add_argument(
            '--auto-search',
            action='store_true',
            help='Automatically search and fetch candidate pages for each book'
        )
        parser.add_argument(
            '--llm-select',
            action='store_true',
            help='Enable LLM-based candidate selection (requires LLM_API_KEY environment variable)'
        )
        parser.add_argument(
            '--llm-conn-test',
            action='store_true',
            help='Test LLM connection and exit (sends simple ping prompt to verify connectivity)'
        )
        parser.add_argument(
            '--search-limit',
            type=int,
            default=5,
            help='Number of search results to fetch per site'
        )
        parser.add_argument(
            '--download-limit', 
            type=int, 
            default=3, 
            help='Number of candidate pages to download per site'
        )
        parser.add_argument(
            '--search-delay',
            type=float,
            default=2.0,
            help='Delay (seconds) between search/download requests'
        )

        # === AUTOMATION OPTIONS ===
        parser.add_argument(
            '--yolo',
            action='store_true',
            help='Auto-accept all prompts (processing confirmation, LLM selections, etc.) - YOLO mode'
        )

        # === QUEUE SYSTEM OPTIONS ===
        parser.add_argument(
            '--workers',
            type=int,
            default=4,
            metavar='N',
            help='Number of parallel workers for processing (default: 4)'
        )

        parser.add_argument(
            '--resume',
            action='store_true',
            help='Resume most recent incomplete job'
        )

        # === DEBUG OPTIONS ===
        parser.add_argument(
            '-d', '--debug',
            action='store_true',
            help='Enable debugging to log file'
        )
        parser.add_argument(
            '-v', '--version', 
            action='version', 
            version=f"Version {__version__}"
        )
        
        return parser
    
    def parse_args(self, args: List[str] = None) -> ProcessingArgs:
        """
        Parse command line arguments.
        
        Args:
            args: Optional list of arguments (for testing)
            
        Returns:
            ProcessingArgs object with parsed arguments
        """
        parsed = self.parser.parse_args(args)
        
        # Convert to ProcessingArgs
        processing_args = ProcessingArgs(
            # Input/Output
            folders=[Path(f) for f in parsed.folders] if parsed.folders else [],
            output=Path(parsed.output) if parsed.output else None,
            book_root=Path(parsed.book_root) if parsed.book_root else None,

            # Operation mode
            copy=parsed.copy,
            move=parsed.move,
            dry_run=parsed.dry_run,

            # Processing options
            flatten=parsed.flatten,
            rename=parsed.rename,
            series=parsed.series,
            id3_tag=parsed.id3_tag,

            # Metadata options
            infotxt=parsed.infotxt,
            opf=parsed.opf,
            cover=parsed.cover,
            from_opf=parsed.from_opf,
            force_refresh=parsed.force_refresh,

            # Search options
            site=parsed.site,
            auto_search=parsed.auto_search,
            llm_select=parsed.llm_select,
            llm_conn_test=parsed.llm_conn_test,
            search_limit=parsed.search_limit,
            download_limit=parsed.download_limit,
            search_delay=parsed.search_delay,

            # Automation
            yolo=parsed.yolo,

            # Queue system
            workers=parsed.workers,
            resume=parsed.resume,

            # Debug
            debug=parsed.debug
        )
        
        return processing_args
    
    def validate_args(self, args: ProcessingArgs) -> List[str]:
        """
        Validate command line arguments.
        
        Args:
            args: ProcessingArgs to validate
            
        Returns:
            List of validation error messages
        """
        errors = args.validate()
        
        # Additional validations specific to CLI
        
        # Check that we have some input
        if not args.folders and not args.book_root:
            errors.append("Must specify either folders to process or --book-root")
        
        # Validate folder paths
        for folder in args.folders:
            if not folder.exists():
                errors.append(f"Folder does not exist: {folder}")
            elif not folder.is_dir():
                errors.append(f"Path is not a directory: {folder}")
            elif not has_audio_files(folder):
                errors.append(f"Folder contains no audio files: {folder}")
        
        # Validate site choice
        if args.site not in ['all'] + list(SCRAPER_REGISTRY.keys()):
            errors.append(f"Invalid site choice: {args.site}")
        
        return errors
    
    def discover_folders_from_book_root(self, book_root: Path) -> List[Path]:
        """
        Discover audiobook folders from book root directory.
        
        Args:
            book_root: Root directory to search
            
        Returns:
            List of discovered audiobook folders
        """
        if not book_root.is_dir():
            return []
        
        from ..config import AUDIO_EXTENSIONS
        
        # Find all folders that contain audio files
        audiobook_folders = set()
        
        for file_path in book_root.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in AUDIO_EXTENSIONS:
                audiobook_folders.add(file_path.parent.resolve())
        
        return sorted(audiobook_folders)
    
    def print_banner(self):
        """Print application banner."""
        print(fr"""
book-meister (v{__version__})
=========================================================================
""")
    
    def handle_validation_errors(self, errors: List[str], yolo: bool = False):
        """
        Handle validation errors by printing them and exiting.

        Args:
            errors: List of error messages
            yolo: Whether yolo mode is enabled (skip exit prompt)
        """
        if not errors:
            return

        print("\nValidation Errors:")
        for error in errors:
            print(f"  - {error}")

        print("\nUse --help for usage information.")
        if not yolo:
            input("\nPress enter to exit...")
        sys.exit(1)
    
    def confirm_processing(self, folders: List[Path], dry_run: bool = False, yolo: bool = False) -> bool:
        """
        Confirm processing with user.

        Args:
            folders: List of folders to process
            dry_run: Whether this is a dry run
            yolo: Whether yolo mode is enabled (auto-accept)

        Returns:
            True if user confirms or yolo mode is enabled, False otherwise
        """
        mode = "DRY RUN" if dry_run else "PROCESSING"

        print(f"\n=== {mode} CONFIRMATION ===")
        print(f"Ready to process {len(folders)} folder(s):")

        for folder in folders[:10]:  # Show first 10
            try:
                print(f"  - {folder.name}")
            except UnicodeEncodeError:
                # Fallback for Windows terminal that can't display special characters
                print(f"  - {folder.name.encode('ascii', 'replace').decode('ascii')}")

        if len(folders) > 10:
            print(f"  ... and {len(folders) - 10} more")

        if dry_run:
            print("\nThis is a dry run - no files will be modified.")

        if yolo:
            print("\n🚀 YOLO mode enabled - auto-accepting...")
            return True

        response = input("\nContinue? (y/N): ").strip().lower()
        return response in ['y', 'yes']
    
    def get_user_input(self, prompt: str, default: str = "") -> str:
        """
        Get input from user with optional default.
        
        Args:
            prompt: Prompt to display
            default: Default value if user enters nothing
            
        Returns:
            User input or default
        """
        if default:
            full_prompt = f"{prompt} [{default}]: "
        else:
            full_prompt = f"{prompt}: "
        
        response = input(full_prompt).strip()
        return response if response else default
    
    def get_yes_no_input(self, prompt: str, default: bool = False) -> bool:
        """
        Get yes/no input from user.
        
        Args:
            prompt: Prompt to display
            default: Default value
            
        Returns:
            True for yes, False for no
        """
        default_str = "Y/n" if default else "y/N"
        response = input(f"{prompt} ({default_str}): ").strip().lower()
        
        if not response:
            return default
        
        return response in ['y', 'yes', 'true', '1']
