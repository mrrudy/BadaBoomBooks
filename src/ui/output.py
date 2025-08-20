"""
Output formatting and display utilities.

This module handles formatting and displaying various types of output
including metadata summaries, error reports, and status information.
"""

from pathlib import Path
from typing import List, Dict, Any

from ..models import BookMetadata, ProcessingResult


class OutputFormatter:
    """Handles formatting and display of various output types."""
    
    @staticmethod
    def format_metadata_summary(metadata: BookMetadata) -> str:
        """
        Format metadata as a readable summary.
        
        Args:
            metadata: BookMetadata to format
            
        Returns:
            Formatted summary string
        """
        lines = []
        
        # Basic information
        lines.append(f"Title: {metadata.get_safe_title()}")
        lines.append(f"Author: {metadata.get_safe_author()}")
        
        if metadata.subtitle:
            lines.append(f"Subtitle: {metadata.subtitle}")
        
        if metadata.narrator:
            lines.append(f"Narrator: {metadata.narrator}")
        
        # Publication info
        if metadata.publisher:
            lines.append(f"Publisher: {metadata.publisher}")
        
        date = metadata.get_publication_date()
        if date:
            lines.append(f"Published: {date}")
        
        if metadata.language:
            lines.append(f"Language: {metadata.language}")
        
        # Series information
        if metadata.has_series_info():
            lines.append(f"Series: {metadata.series} | Volume: {metadata.volumenumber}")
        
        # Identifiers
        if metadata.isbn:
            lines.append(f"ISBN: {metadata.isbn}")
        
        if metadata.asin:
            lines.append(f"ASIN: {metadata.asin}")
        
        # Genres
        genres = metadata.get_genres_list()
        if genres:
            lines.append(f"Genres: {', '.join(genres)}")
        
        # Source
        if metadata.url:
            lines.append(f"URL: {metadata.url}")
        
        # Summary (truncated for display)
        if metadata.summary:
            summary = metadata.summary
            if len(summary) > 200:
                summary = summary[:197] + "..."
            lines.append(f"Summary: {summary}")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_book_status(metadata: BookMetadata) -> str:
        """
        Format book processing status.
        
        Args:
            metadata: BookMetadata with status information
            
        Returns:
            Formatted status string
        """
        if metadata.failed:
            return f"❌ FAILED: {metadata.failed_exception}"
        elif metadata.skip:
            return "⊘ SKIPPED"
        elif metadata.final_output:
            return f"✅ SUCCESS: {metadata.final_output}"
        else:
            return "📋 PENDING"
    
    @staticmethod
    def format_processing_plan(folders: List[Path], args) -> str:
        """
        Format processing plan for display.
        
        Args:
            folders: List of folders to process
            args: Processing arguments
            
        Returns:
            Formatted plan string
        """
        lines = []
        lines.append(f"📚 Books to process: {len(folders)}")
        
        if args.output:
            lines.append(f"📁 Output directory: {args.output}")
        
        # Operations
        operations = []
        if args.copy:
            operations.append("Copy")
        elif args.move:
            operations.append("Move")
        else:
            operations.append("In-place")
        
        if args.flatten:
            operations.append("Flatten")
        if args.rename:
            operations.append("Rename tracks")
        if args.series:
            operations.append("Series organization")
        
        if operations:
            lines.append(f"⚙️  Operations: {', '.join(operations)}")
        
        # File generation
        files = []
        if args.opf:
            files.append("OPF")
        if args.infotxt:
            files.append("info.txt")
        if args.cover:
            files.append("cover.jpg")
        
        if files:
            lines.append(f"📄 Generate files: {', '.join(files)}")
        
        # Audio processing
        if args.id3_tag:
            lines.append("🎵 Update ID3 tags: Yes")
        
        # Search settings
        search_info = f"🔍 Search: {args.site}"
        if args.auto_search:
            search_info += " (automatic)"
        lines.append(search_info)
        
        return "\n".join(lines)
    
    @staticmethod
    def format_error_report(errors: List[str]) -> str:
        """
        Format error list for display.
        
        Args:
            errors: List of error messages
            
        Returns:
            Formatted error report
        """
        if not errors:
            return "✅ No errors"
        
        lines = [f"❌ {len(errors)} error(s) found:"]
        for i, error in enumerate(errors, 1):
            lines.append(f"  {i}. {error}")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_search_results(candidates: List[Dict[str, Any]]) -> str:
        """
        Format search results for display.
        
        Args:
            candidates: List of search result dictionaries
            
        Returns:
            Formatted search results
        """
        if not candidates:
            return "No search results found."
        
        lines = [f"Found {len(candidates)} candidate(s):"]
        
        for i, candidate in enumerate(candidates, 1):
            lines.append(f"\n[{i}] {candidate.get('title', 'No title')}")
            lines.append(f"    URL: {candidate.get('url', 'No URL')}")
            
            snippet = candidate.get('snippet', '')
            if snippet:
                if len(snippet) > 100:
                    snippet = snippet[:97] + "..."
                lines.append(f"    {snippet}")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_file_list(files: List[Path], title: str = "Files") -> str:
        """
        Format file list for display.
        
        Args:
            files: List of file paths
            title: Title for the list
            
        Returns:
            Formatted file list
        """
        if not files:
            return f"{title}: None"
        
        lines = [f"{title} ({len(files)}):"]
        
        # Show first 10 files
        for file_path in files[:10]:
            lines.append(f"  📁 {file_path.name}")
        
        if len(files) > 10:
            lines.append(f"  ... and {len(files) - 10} more")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_statistics(result: ProcessingResult, elapsed_time: float = 0) -> str:
        """
        Format processing statistics.
        
        Args:
            result: ProcessingResult with statistics
            elapsed_time: Total elapsed time in seconds
            
        Returns:
            Formatted statistics
        """
        lines = []
        
        total = result.total_processed()
        success_count = len(result.success_books)
        failed_count = len(result.failed_books) 
        skipped_count = len(result.skipped_books)
        
        lines.append(f"📊 Processing Statistics:")
        lines.append(f"  Total books: {total}")
        lines.append(f"  ✅ Successful: {success_count}")
        lines.append(f"  ❌ Failed: {failed_count}")
        lines.append(f"  ⊘ Skipped: {skipped_count}")
        
        if total > 0:
            success_rate = (success_count / total) * 100
            lines.append(f"  📈 Success rate: {success_rate:.1f}%")
        
        if elapsed_time > 0:
            lines.append(f"  ⏱️  Total time: {OutputFormatter.format_time(elapsed_time)}")
            
            if success_count > 0:
                avg_time = elapsed_time / success_count
                lines.append(f"  ⚡ Average per book: {OutputFormatter.format_time(avg_time)}")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_time(seconds: float) -> str:
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
    
    @staticmethod
    def format_size(bytes_size: int) -> str:
        """
        Format file size as human-readable string.
        
        Args:
            bytes_size: Size in bytes
            
        Returns:
            Formatted size string
        """
        if bytes_size == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        size_index = 0
        size = float(bytes_size)
        
        while size >= 1024 and size_index < len(size_names) - 1:
            size /= 1024
            size_index += 1
        
        return f"{size:.1f} {size_names[size_index]}"
    
    @staticmethod
    def format_table(data: List[Dict[str, Any]], headers: List[str]) -> str:
        """
        Format data as a simple table.
        
        Args:
            data: List of dictionaries with table data
            headers: List of column headers
            
        Returns:
            Formatted table string
        """
        if not data or not headers:
            return "No data to display"
        
        # Calculate column widths
        col_widths = {}
        for header in headers:
            col_widths[header] = len(header)
        
        for row in data:
            for header in headers:
                value = str(row.get(header, ""))
                col_widths[header] = max(col_widths[header], len(value))
        
        # Format table
        lines = []
        
        # Header row
        header_row = " | ".join(header.ljust(col_widths[header]) for header in headers)
        lines.append(header_row)
        
        # Separator
        separator = " | ".join("-" * col_widths[header] for header in headers)
        lines.append(separator)
        
        # Data rows
        for row in data:
            data_row = " | ".join(
                str(row.get(header, "")).ljust(col_widths[header]) 
                for header in headers
            )
            lines.append(data_row)
        
        return "\n".join(lines)
    
    @staticmethod
    def format_metadata_comparison(old_metadata: BookMetadata, new_metadata: BookMetadata) -> str:
        """
        Format comparison between old and new metadata.
        
        Args:
            old_metadata: Original metadata
            new_metadata: Updated metadata
            
        Returns:
            Formatted comparison string
        """
        lines = ["📋 Metadata Changes:"]
        
        # Compare key fields
        fields_to_compare = [
            ('title', 'Title'),
            ('author', 'Author'),
            ('series', 'Series'),
            ('volumenumber', 'Volume'),
            ('publisher', 'Publisher'),
            ('publishyear', 'Year'),
            ('language', 'Language')
        ]
        
        changes_found = False
        
        for field, label in fields_to_compare:
            old_value = getattr(old_metadata, field, "")
            new_value = getattr(new_metadata, field, "")
            
            if old_value != new_value:
                changes_found = True
                lines.append(f"  {label}:")
                lines.append(f"    Old: {old_value or '(none)'}")
                lines.append(f"    New: {new_value or '(none)'}")
        
        if not changes_found:
            lines.append("  No changes detected")
        
        return "\n".join(lines)
    
    @staticmethod
    def create_separator(width: int = 80, char: str = "=") -> str:
        """
        Create a separator line.
        
        Args:
            width: Width of the separator
            char: Character to use for separator
            
        Returns:
            Separator string
        """
        return char * width
    
    @staticmethod
    def center_text(text: str, width: int = 80, char: str = " ") -> str:
        """
        Center text within a given width.
        
        Args:
            text: Text to center
            width: Total width
            char: Padding character
            
        Returns:
            Centered text string
        """
        if len(text) >= width:
            return text
        
        padding = width - len(text)
        left_padding = padding // 2
        right_padding = padding - left_padding
        
        return char * left_padding + text + char * right_padding
