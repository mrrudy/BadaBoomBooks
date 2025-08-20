"""
Progress reporting and status display.

This module handles progress tracking and user feedback during processing.
"""

import time
from typing import List, Optional
from pathlib import Path

from ..models import BookMetadata, ProcessingResult
from ..utils import ProgressTracker


class ProgressReporter:
    """Handles progress reporting and status updates."""
    
    def __init__(self, show_progress: bool = True):
        self.show_progress = show_progress
        self.start_time = None
        self.current_book = None
        self.tracker = None
    
    def start_processing(self, total_books: int, description: str = "Processing books"):
        """
        Start progress tracking.
        
        Args:
            total_books: Total number of books to process
            description: Description of the process
        """
        self.start_time = time.time()
        self.tracker = ProgressTracker(total_books, description)
        
        if self.show_progress:
            print(f"\n{'='*35} {description.upper()} {'='*35}")
            print(f"Processing {total_books} book(s)...")
    
    def start_book(self, metadata: BookMetadata, book_index: int = 0):
        """
        Report start of processing a book.
        
        Args:
            metadata: BookMetadata for the book being processed
            book_index: Current book index (0-based)
        """
        self.current_book = metadata
        
        if self.show_progress and self.tracker:
            progress_str = self.tracker.get_progress_str()
            print(f"\n----- {metadata.input_folder} -----")
            print(f"[{progress_str}]")
    
    def update_book_status(self, status: str, details: str = ""):
        """
        Update status for current book.
        
        Args:
            status: Status message
            details: Optional details
        """
        if self.show_progress:
            message = f"  {status}"
            if details:
                message += f": {details}"
            print(message)
    
    def finish_book(self, success: bool = True, error: str = ""):
        """
        Report completion of a book.
        
        Args:
            success: Whether book was processed successfully
            error: Error message if unsuccessful
        """
        if self.tracker:
            self.tracker.update()
        
        if self.show_progress:
            if success:
                print("  ✓ Done!")
            else:
                print(f"  ✗ Failed: {error}")
    
    def report_search_progress(self, search_term: str, site: str = ""):
        """
        Report search progress.
        
        Args:
            search_term: Term being searched
            site: Site being searched (optional)
        """
        if self.show_progress:
            if site:
                print(f"  Searching {site} for: {search_term}")
            else:
                print(f"  Searching for: {search_term}")
    
    def report_scraping_progress(self, url: str, site: str = ""):
        """
        Report scraping progress.
        
        Args:
            url: URL being scraped
            site: Site being scraped (optional)
        """
        if self.show_progress:
            if site:
                print(f"  Scraping {site}: {url}")
            else:
                print(f"  Scraping: {url}")
    
    def report_file_operation(self, operation: str, source: Path, target: Path = None):
        """
        Report file operation progress.
        
        Args:
            operation: Type of operation (copy, move, etc.)
            source: Source path
            target: Target path (optional)
        """
        if self.show_progress:
            if target:
                print(f"  {operation.title()}ing {source.name} -> {target}")
            else:
                print(f"  {operation.title()}ing {source.name}")
    
    def report_metadata_operation(self, operation: str, file_type: str = ""):
        """
        Report metadata operation progress.
        
        Args:
            operation: Type of operation
            file_type: Type of file being created (optional)
        """
        if self.show_progress:
            if file_type:
                print(f"  {operation} {file_type}")
            else:
                print(f"  {operation}")
    
    def get_elapsed_time(self) -> float:
        """
        Get elapsed time since processing started.
        
        Returns:
            Elapsed time in seconds
        """
        if self.start_time:
            return time.time() - self.start_time
        return 0.0
    
    def get_estimated_remaining_time(self) -> Optional[float]:
        """
        Estimate remaining processing time.
        
        Returns:
            Estimated remaining time in seconds, or None if unknown
        """
        if not self.tracker or not self.start_time or self.tracker.current == 0:
            return None
        
        elapsed = self.get_elapsed_time()
        rate = self.tracker.current / elapsed
        remaining_books = self.tracker.total - self.tracker.current
        
        return remaining_books / rate if rate > 0 else None
    
    def format_time(self, seconds: float) -> str:
        """
        Format time duration as human-readable string.
        
        Args:
            seconds: Duration in seconds
            
        Returns:
            Formatted time string
        """
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"
    
    def show_final_summary(self, result: ProcessingResult):
        """
        Show final processing summary.
        
        Args:
            result: ProcessingResult with summary information
        """
        if not self.show_progress:
            return
        
        elapsed = self.get_elapsed_time()
        
        print(f"\n{'='*35} SUMMARY {'='*35}")
        print(f"Processing completed in {self.format_time(elapsed)}")
        print()
        
        if result.has_successes():
            print(f"✓ Successfully processed {len(result.success_books)} book(s):")
            for book in result.success_books:
                print(f"  - {book}")
            print()
        
        if result.skipped_books:
            print(f"⊘ Skipped {len(result.skipped_books)} book(s):")
            for book in result.skipped_books:
                print(f"  - {book}")
            print()
        
        if result.has_failures():
            print(f"✗ Failed to process {len(result.failed_books)} book(s):")
            for book in result.failed_books:
                print(f"  - {book}")
            print()
        
        # Overall status
        if result.has_failures():
            print("⚠️  Processing completed with some failures.")
        elif result.skipped_books:
            print("✓ Processing completed successfully (some books skipped).")
        else:
            print("✓ All books processed successfully!")
    
    def show_dry_run_summary(self, folders: List[Path], args):
        """
        Show dry run summary of what would be processed.
        
        Args:
            folders: List of folders that would be processed
            args: Processing arguments
        """
        if not self.show_progress:
            return
        
        print(f"\n{'='*35} DRY RUN SUMMARY {'='*35}")
        print(f"Would process {len(folders)} folder(s) with the following operations:")
        print()
        
        operations = []
        if args.copy:
            operations.append("Copy folders")
        elif args.move:
            operations.append("Move folders")
        else:
            operations.append("Process in-place")
        
        if args.flatten:
            operations.append("Flatten folder structure")
        if args.rename:
            operations.append("Rename audio tracks")
        if args.opf:
            operations.append("Create OPF metadata files")
        if args.infotxt:
            operations.append("Create info.txt files")
        if args.id3_tag:
            operations.append("Update ID3 tags")
        if args.cover:
            operations.append("Download cover images")
        
        for operation in operations:
            print(f"  • {operation}")
        
        print()
        if args.output:
            print(f"Output directory: {args.output}")
        if args.series:
            print("Series organization: Enabled")
        
        print(f"\nSearch mode: {args.site}")
        if args.auto_search:
            print("Auto-search: Enabled")
        
        print(f"\n{'='*77}")


class QuietProgressReporter(ProgressReporter):
    """Progress reporter that only shows minimal output."""
    
    def __init__(self):
        super().__init__(show_progress=False)
    
    def start_book(self, metadata: BookMetadata, book_index: int = 0):
        """Only show book name for quiet mode."""
        print(f"Processing: {metadata.input_folder}")
    
    def finish_book(self, success: bool = True, error: str = ""):
        """Show completion status."""
        if not success and error:
            print(f"  Error: {error}")


class VerboseProgressReporter(ProgressReporter):
    """Progress reporter with extra detailed output."""
    
    def start_book(self, metadata: BookMetadata, book_index: int = 0):
        """Show detailed book information."""
        super().start_book(metadata, book_index)
        
        if self.show_progress:
            # Show estimated time remaining
            remaining = self.get_estimated_remaining_time()
            if remaining:
                print(f"  Estimated time remaining: {self.format_time(remaining)}")
            
            # Show folder size
            from ..utils import get_folder_size, format_file_size
            folder_path = Path(metadata.input_folder)
            if folder_path.exists():
                size = get_folder_size(folder_path)
                print(f"  Folder size: {format_file_size(size)}")
