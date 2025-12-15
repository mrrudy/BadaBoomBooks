"""
Utility functions and helper methods.

This module contains common utility functions used across the application,
including path manipulation, text cleaning, and validation functions.
"""

import re
import time
import base64
from pathlib import Path
from typing import List, Optional, Tuple
import logging as log

from .config import AUDIO_EXTENSIONS, SCRAPER_REGISTRY
from .models import BookMetadata


def clean_filename(text: str) -> str:
    """
    Clean text for use in filenames by removing invalid characters.
    
    Args:
        text: Raw text to clean
        
    Returns:
        Cleaned text safe for use in filenames
    """
    if not text:
        return ""
    return re.sub(r"[^\w\-\.\(\) ]+", '', text).strip()


def extract_search_terms_from_audio_files(folder_path: Path) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract search terms (title, author) from audio file ID3 tags.
    
    Args:
        folder_path: Path to folder containing audio files
        
    Returns:
        Tuple of (title, author) or (None, None) if not found
    """
    try:
        from tinytag import TinyTag
    except ImportError:
        log.warning("TinyTag not available, cannot extract search terms from audio files")
        return None, None
    
    for file in folder_path.glob('**/*'):
        if file.suffix.lower() in {ext.lower() for ext in AUDIO_EXTENSIONS}:
            try:
                track = TinyTag.get(str(file))
                
                # Extract and clean album/title
                album = re.sub(r"\&", 'and', track.album).strip() if track.album else ''
                track_title = re.sub(r"\&", 'and', track.title).strip() if track.title else ''
                
                # Determine best title
                title = None
                if album and track_title:
                    if album.lower() != track_title.lower():
                        title = f"{track_title} ({album})"
                    else:
                        title = track_title
                elif track_title:
                    title = track_title
                elif album:
                    title = album
                
                # Extract and clean author
                author = re.sub(r"\&", 'and', track.artist).strip() if track.artist else None
                
                if title or author:
                    return title, author
                    
            except Exception as e:
                log.debug(f"Couldn't get search term metadata from ID3 tags ({file}): {e}")
                continue
    
    return None, None


def generate_search_term(folder_path: Path) -> str:
    """
    Generate a search term for a book folder.
    
    Args:
        folder_path: Path to the audiobook folder
        
    Returns:
        Search term string
    """
    title, author = extract_search_terms_from_audio_files(folder_path)
    
    if title and author:
        return f"{title} by {author}"
    elif title:
        return title
    else:
        return str(folder_path.name)


def detect_url_site(url: str) -> Optional[str]:
    """
    Detect which scraping site a URL belongs to.
    
    Args:
        url: URL to check
        
    Returns:
        Site key if recognized, None otherwise
    """
    for site_key, config in SCRAPER_REGISTRY.items():
        if re.search(config["url_pattern"], url):
            return site_key
    return None


def find_audio_files(folder_path: Path) -> List[Path]:
    """
    Find all audio files in a folder and its subfolders.
    
    Args:
        folder_path: Path to search
        
    Returns:
        List of audio file paths, sorted
    """
    audio_files = []
    for ext in AUDIO_EXTENSIONS:
        audio_files.extend(folder_path.rglob(f"*{ext}"))
    
    return sorted(audio_files)


def has_audio_files(folder_path: Path) -> bool:
    """
    Check if a folder contains any audio files.

    Args:
        folder_path: Path to check

    Returns:
        True if folder contains audio files
    """
    for ext in AUDIO_EXTENSIONS:
        if any(folder_path.rglob(f"*{ext}")):
            return True
    return False


def find_metadata_opf(folder_path: Path) -> Optional[Path]:
    """
    Find metadata.opf file in folder or its subdirectories.

    Searches in the following order:
    1. Direct child: folder/metadata.opf
    2. In same folder as audio files (for nested structures)

    Args:
        folder_path: Path to search

    Returns:
        Path to metadata.opf if found, None otherwise
    """
    # First check direct child
    direct_opf = folder_path / 'metadata.opf'
    if direct_opf.exists():
        return direct_opf

    # Search in subdirectories where audio files are located
    # This handles nested structures like: Author/Book - Author/Book/metadata.opf
    for ext in AUDIO_EXTENSIONS:
        audio_files = list(folder_path.rglob(f"*{ext}"))
        if audio_files:
            # Check for metadata.opf in the same directory as the first audio file
            audio_folder = audio_files[0].parent
            opf_file = audio_folder / 'metadata.opf'
            if opf_file.exists():
                return opf_file

    return None


def encode_for_config(text: str) -> str:
    """
    Encode text for safe storage in configuration files.
    
    Args:
        text: Text to encode
        
    Returns:
        Base64 encoded string
    """
    return base64.standard_b64encode(bytes(text, 'utf-8')).decode()


def decode_from_config(encoded_text: str) -> str:
    """
    Decode text from configuration files.
    
    Args:
        encoded_text: Base64 encoded text
        
    Returns:
        Decoded string
    """
    return base64.standard_b64decode(bytes(encoded_text, 'utf-8')).decode()


def wait_with_backoff(attempt: int, base_delay: float = 2.0, max_delay: float = 10.0) -> float:
    """
    Calculate wait time with exponential backoff.
    
    Args:
        attempt: Current attempt number (starting from 1)
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        
    Returns:
        Delay time in seconds
    """
    delay = min(base_delay * (1.5 ** (attempt - 1)), max_delay)
    time.sleep(delay)
    return delay


def validate_path(path_str: str, must_exist: bool = True) -> Optional[Path]:
    """
    Validate and normalize a path string.
    
    Args:
        path_str: Path string to validate
        must_exist: Whether the path must exist
        
    Returns:
        Path object if valid, None otherwise
    """
    try:
        path = Path(path_str.rstrip(r'\/"\'')).resolve()
        if must_exist and not path.exists():
            return None
        return path
    except Exception:
        return None


def calculate_padding_for_tracks(num_tracks: int) -> int:
    """
    Calculate appropriate zero-padding for track numbers.
    
    Args:
        num_tracks: Total number of tracks
        
    Returns:
        Number of digits to pad to
    """
    if num_tracks >= 1000:
        return 4
    elif num_tracks >= 100:
        return 3
    else:
        return 2


def sanitize_xml_text(text: str) -> str:
    """
    Sanitize text for safe use in XML files.
    
    Args:
        text: Text to sanitize
        
    Returns:
        XML-safe text
    """
    import html
    return html.escape(text if text is not None else '', quote=True)


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Human-readable size string
    """
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    size_index = 0
    size = float(size_bytes)
    
    while size >= 1024 and size_index < len(size_names) - 1:
        size /= 1024
        size_index += 1
    
    return f"{size:.1f} {size_names[size_index]}"


def get_folder_size(folder_path: Path) -> int:
    """
    Calculate total size of all files in a folder.
    
    Args:
        folder_path: Path to folder
        
    Returns:
        Total size in bytes
    """
    total_size = 0
    try:
        for file_path in folder_path.rglob('*'):
            if file_path.is_file():
                total_size += file_path.stat().st_size
    except Exception as e:
        log.warning(f"Could not calculate folder size for {folder_path}: {e}")
    
    return total_size


def normalize_series_volume(volume_str: str) -> str:
    """
    Normalize series volume numbers for consistent formatting.
    
    Args:
        volume_str: Raw volume string
        
    Returns:
        Normalized volume string
    """
    if not volume_str:
        return "0"
    
    # Handle ranges like "1-2" -> "1,2"
    if '-' in volume_str:
        parts = volume_str.split('-')
        if len(parts) == 2 and parts[0].replace('.', '', 1).isdigit() and parts[1].replace('.', '', 1).isdigit():
            try:
                start = float(parts[0])
                end = float(parts[1])
                if start.is_integer() and end.is_integer():
                    return ','.join(str(int(i)) for i in range(int(start), int(end) + 1))
            except Exception:
                pass
    
    return volume_str.strip()


def safe_encode_text(text: str) -> str:
    """
    Safely encode text for Windows terminal output.
    Replaces problematic emojis with ASCII equivalents.

    Args:
        text: Text that may contain emojis

    Returns:
        Text with emojis replaced with safe alternatives
    """
    # Map emojis to ASCII equivalents for Windows terminal
    emoji_replacements = {
        '📚': '[Books]',
        '📁': '[Folder]',
        '⚙️': '[Settings]',
        '📄': '[Files]',
        '🎵': '[Audio]',
        '🔍': '[Search]',
        '✅': '[OK]',
        '❌': '[X]',
        '⊘': '[Skip]',
        '📋': '[Pending]',
        '📊': '[Stats]',
        '📈': '[Rate]',
        '⏱️': '[Time]',
        '⚡': '[Speed]',
        '🤖': '[AI]',
        '📖': '[Book]',
        '✍️': '[Author]',
        '🎤': '[Narrator]',
        '🏢': '[Publisher]',
        '📅': '[Year]',
        '🌍': '[Language]',
        '📂': '[Source]'
    }

    result = text
    for emoji, replacement in emoji_replacements.items():
        result = result.replace(emoji, replacement)

    return result


class ProgressTracker:
    """Simple progress tracking utility."""

    def __init__(self, total: int, description: str = "Processing"):
        self.total = total
        self.current = 0
        self.description = description

    def update(self, increment: int = 1):
        """Update progress counter."""
        self.current += increment
        self.current = min(self.current, self.total)

    def get_progress_str(self) -> str:
        """Get progress as string."""
        percentage = (self.current / self.total * 100) if self.total > 0 else 0
        return f"{self.description}: {self.current}/{self.total} ({percentage:.1f}%)"

    def is_complete(self) -> bool:
        """Check if progress is complete."""
        return self.current >= self.total
