"""
Data models and structures for audiobook metadata.

This module defines the core data structures used throughout the application,
including the BookMetadata class and helper functions for data validation.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Any, Dict
import logging as log


@dataclass
class BookMetadata:
    """
    Complete metadata structure for an audiobook.
    
    This class encapsulates all metadata fields that can be scraped
    from various sources, processed, and used for organizing audiobooks.
    """
    
    # === CORE IDENTIFICATION ===
    input_folder: str = ""
    url: str = ""
    asin: str = ""
    isbn: str = ""
    
    # === BASIC INFORMATION ===
    title: str = ""
    subtitle: str = ""
    author: str = ""
    narrator: str = ""
    
    # === PUBLICATION DATA ===
    publisher: str = ""
    publishyear: str = ""
    datepublished: str = ""
    language: str = ""
    
    # === CONTENT DESCRIPTION ===
    summary: str = ""
    genres: str = ""
    
    # === SERIES INFORMATION ===
    series: str = ""
    volumenumber: str = ""
    
    # === MULTI-VALUE FIELDS ===
    authors_multi: List[Dict[str, Any]] = field(default_factory=list)
    series_multi: List[Dict[str, Any]] = field(default_factory=list)
    narrators_multi: List[Dict[str, Any]] = field(default_factory=list)
    
    # === MEDIA AND FILES ===
    cover_url: str = ""
    final_output: Optional[Path] = None
    
    # === PROCESSING STATUS ===
    failed: bool = False
    failed_exception: str = ""
    skip: bool = False
    
    def __post_init__(self):
        """Initialize metadata with default values for critical fields."""
        if not self.author and not self.failed:
            log.warning(f"No author for {self.input_folder}, will use '_unknown_'")
        
        if not self.title and not self.failed:
            log.warning(f"No title for {self.input_folder}, will use folder name")
    
    @classmethod
    def create_empty(cls, input_folder: str, url: str = "") -> 'BookMetadata':
        """Create a new BookMetadata instance with minimal required fields."""
        return cls(
            input_folder=input_folder,
            url=url,
            author='',
            title='',
            failed=False,
            skip=False
        )
    
    def has_series_info(self) -> bool:
        """Check if this book has series information."""
        return bool(self.series and self.volumenumber)
    
    def get_safe_author(self) -> str:
        """Get author or fallback to '_unknown_'."""
        return self.author if self.author else '_unknown_'
    
    def get_safe_title(self) -> str:
        """Get title or fallback to input folder name."""
        return self.title if self.title else self.input_folder
    
    def get_publication_date(self) -> str:
        """Get the best available publication date."""
        return self.datepublished or self.publishyear or ""
    
    def get_genres_list(self) -> List[str]:
        """Convert genres string to list."""
        if not self.genres:
            return []
        if isinstance(self.genres, list):
            return self.genres
        return [g.strip() for g in self.genres.split(',') if g.strip()]
    
    def is_valid_for_processing(self) -> bool:
        """Check if metadata is valid for processing operations."""
        return not self.failed and not self.skip and (self.author or self.title)
    
    def mark_as_failed(self, exception: str):
        """Mark this metadata as failed with an exception message."""
        self.failed = True
        self.failed_exception = exception
        log.error(f"Marked {self.input_folder} as failed: {exception}")
    
    def mark_as_skipped(self):
        """Mark this metadata to be skipped."""
        self.skip = True
        log.info(f"Marked {self.input_folder} as skipped")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary for serialization."""
        result = {}
        for field_name, field_value in self.__dict__.items():
            if isinstance(field_value, Path):
                result[field_name] = str(field_value)
            else:
                result[field_name] = field_value
        return result
    
    def update_from_dict(self, data: Dict[str, Any]):
        """Update metadata fields from a dictionary."""
        for key, value in data.items():
            if hasattr(self, key):
                if key == 'final_output' and value:
                    setattr(self, key, Path(value))
                else:
                    setattr(self, key, value)


@dataclass 
class ProcessingResult:
    """Results from processing a collection of audiobooks."""
    
    success_books: List[str] = field(default_factory=list)
    failed_books: List[str] = field(default_factory=list)  
    skipped_books: List[str] = field(default_factory=list)
    
    def add_success(self, book_name: str, details: str = ""):
        """Add a successfully processed book."""
        entry = f"{book_name} - {details}" if details else book_name
        self.success_books.append(entry)
    
    def add_failure(self, book_name: str, error: str):
        """Add a failed book with error details."""
        self.failed_books.append(f"{book_name} ({error})")
    
    def add_skipped(self, book_name: str):
        """Add a skipped book."""
        self.skipped_books.append(book_name)
    
    def has_failures(self) -> bool:
        """Check if any books failed processing."""
        return len(self.failed_books) > 0
    
    def has_successes(self) -> bool:
        """Check if any books were processed successfully."""
        return len(self.success_books) > 0
    
    def total_processed(self) -> int:
        """Get total number of books processed (including failures and skips)."""
        return len(self.success_books) + len(self.failed_books) + len(self.skipped_books)


@dataclass
class SearchCandidate:
    """Represents a search result candidate for book metadata."""
    
    site_key: str
    url: str
    title: str
    snippet: str
    html: str = ""
    
    def __str__(self):
        return f"{self.site_key} | {self.title}\n    {self.url}\n    {self.snippet[:100]}..."


@dataclass
class ProcessingArgs:
    """Command line arguments and processing options."""
    
    # === INPUT/OUTPUT ===
    folders: List[Path] = field(default_factory=list)
    output: Optional[Path] = None
    book_root: Optional[Path] = None
    
    # === PROCESSING OPTIONS ===
    copy: bool = False
    move: bool = False
    dry_run: bool = False
    
    # === FEATURE FLAGS ===
    flatten: bool = False
    rename: bool = False
    opf: bool = False
    infotxt: bool = False
    id3_tag: bool = False
    series: bool = False
    cover: bool = False
    from_opf: bool = False
    
    # === SEARCH OPTIONS ===
    site: str = 'all'
    auto_search: bool = False
    search_limit: int = 5
    download_limit: int = 3
    search_delay: float = 2.0
    
    # === DEBUG ===
    debug: bool = False
    
    def validate(self) -> List[str]:
        """Validate arguments and return list of errors."""
        errors = []
        
        if self.copy and self.move:
            errors.append("Cannot specify both --copy and --move")
        
        if self.output and not self.output.is_dir():
            errors.append(f"Output path does not exist or is not a directory: {self.output}")
        
        if self.book_root and not self.book_root.is_dir():
            errors.append(f"Book root path does not exist or is not a directory: {self.book_root}")
        
        if self.search_limit < 1:
            errors.append("Search limit must be at least 1")
            
        if self.download_limit < 1:
            errors.append("Download limit must be at least 1")
            
        if self.search_delay < 0:
            errors.append("Search delay cannot be negative")
        
        return errors
