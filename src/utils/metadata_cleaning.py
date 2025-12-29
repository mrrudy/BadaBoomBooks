"""
Metadata cleaning utilities for search term generation.

This module provides functions to clean and validate metadata from various sources
(folder names, ID3 tags) to improve search accuracy and detect garbage data.
"""

import re
from typing import Optional, Dict, List
from pathlib import Path


# Patterns for detecting garbage data
GARBAGE_PATTERNS = [
    # Domain names
    r'\b[a-z0-9-]+\.(pl|com|net|org|io|de|uk|eu|ru)\b',
    # URLs
    r'https?://',
    r'www\.',
    # Common audiobook team markers
    r'\b(audiobook|exsite|audioteka|empik|legimi|storytel)\b',
    # File sharing/torrent markers
    r'\b(rarbg|yify|eztv|ettv|rip|hdtv)\b',
]

# Compiled regex for performance
GARBAGE_REGEX = re.compile('|'.join(GARBAGE_PATTERNS), re.IGNORECASE)

# Common bracket types to remove
BRACKET_PATTERNS = [
    r'\[.*?\]',  # Square brackets
    r'\(.*?\)',  # Parentheses
    r'\{.*?\}',  # Curly braces
]


def is_garbage_data(text: str) -> bool:
    """
    Check if text contains garbage data (domains, URLs, team names, etc.).

    Args:
        text: Text to validate

    Returns:
        True if text appears to be garbage data, False otherwise

    Examples:
        >>> is_garbage_data("exsite.pl")
        True
        >>> is_garbage_data("Harry Potter")
        False
        >>> is_garbage_data("audiobook.com")
        True
    """
    if not text or not isinstance(text, str):
        return True

    text = text.strip()

    # Empty or very short strings
    if len(text) < 3:
        return True

    # Check against garbage patterns
    if GARBAGE_REGEX.search(text):
        return True

    # Text is only punctuation/special characters
    if re.match(r'^[\W_]+$', text):
        return True

    return False


def is_duplicate_fields(title: Optional[str], author: Optional[str]) -> bool:
    """
    Check if title and author are identical (common in garbage metadata).

    Args:
        title: Book title
        author: Book author

    Returns:
        True if both fields exist and are identical, False otherwise

    Examples:
        >>> is_duplicate_fields("exsite.pl", "exsite.pl")
        True
        >>> is_duplicate_fields("Book Title", "Author Name")
        False
    """
    if not title or not author:
        return False

    return title.strip().lower() == author.strip().lower()


def clean_metadata_text(text: str, remove_brackets: bool = True,
                       remove_special_chars: bool = True) -> str:
    """
    Clean metadata text for search term generation.

    Args:
        text: Text to clean
        remove_brackets: Remove content in brackets [](){}
        remove_special_chars: Remove special characters that hurt search

    Returns:
        Cleaned text suitable for search

    Examples:
        >>> clean_metadata_text("[AudioBook] Title - Subtitle (2023)")
        'Title Subtitle'
        >>> clean_metadata_text("Author: John Doe - Writer")
        'Author John Doe Writer'
    """
    if not text or not isinstance(text, str):
        return ""

    result = text.strip()

    # Remove content in brackets
    if remove_brackets:
        for pattern in BRACKET_PATTERNS:
            result = re.sub(pattern, '', result)

    # Remove special characters that hurt search
    if remove_special_chars:
        # Replace dashes and underscores with spaces
        result = re.sub(r'[-_]+', ' ', result)
        # Remove colons (often used in "Author: Name" format)
        result = re.sub(r':', ' ', result)
        # Remove multiple spaces
        result = re.sub(r'\s+', ' ', result)

    return result.strip()


def clean_folder_name(folder_name: str) -> str:
    """
    Clean folder name for search term generation.

    Applies aggressive cleaning suitable for folder names which often contain
    extra metadata, markers, and formatting.

    Args:
        folder_name: Raw folder name

    Returns:
        Cleaned folder name suitable for search

    Examples:
        >>> clean_folder_name("[AudioBook] Frankiewicz Janusz - Gorejące ognie")
        'Frankiewicz Janusz Gorejące ognie'
        >>> clean_folder_name("Author Name - Book Title (Series #1) [2023]")
        'Author Name Book Title Series #1'
    """
    return clean_metadata_text(folder_name, remove_brackets=True, remove_special_chars=True)


def clean_id3_field(field_value: str) -> str:
    """
    Clean ID3 tag field value.

    Applies moderate cleaning suitable for ID3 tags which are more structured
    than folder names but may still contain garbage.

    Args:
        field_value: Raw ID3 field value

    Returns:
        Cleaned field value, or empty string if garbage detected

    Examples:
        >>> clean_id3_field("exsite.pl")
        ''
        >>> clean_id3_field("Author Name")
        'Author Name'
    """
    if not field_value:
        return ""

    # Check if garbage before cleaning
    if is_garbage_data(field_value):
        return ""

    # Light cleaning - don't remove dashes/special chars from ID3
    # (they might be legitimate parts of titles like "Harry Potter - Book 1")
    result = field_value.strip()

    # Only remove leading/trailing special characters
    result = re.sub(r'^[\W_]+|[\W_]+$', '', result)

    # Remove multiple spaces
    result = re.sub(r'\s+', ' ', result)

    return result.strip()


def extract_metadata_from_sources(
    folder_path: Path,
    id3_title: Optional[str] = None,
    id3_author: Optional[str] = None,
    id3_album: Optional[str] = None
) -> Dict[str, Dict[str, str]]:
    """
    Extract and clean metadata from multiple sources.

    Returns metadata from both folder name and ID3 tags as separate sources
    with validation status.

    Args:
        folder_path: Path to audiobook folder
        id3_title: Title from ID3 tags (if available)
        id3_author: Author from ID3 tags (if available)
        id3_album: Album from ID3 tags (if available)

    Returns:
        Dictionary with two sources:
        {
            'folder': {
                'raw': 'original folder name',
                'cleaned': 'cleaned folder name',
                'valid': bool
            },
            'id3': {
                'title': 'cleaned title or empty',
                'author': 'cleaned author or empty',
                'album': 'cleaned album or empty',
                'valid': bool,
                'garbage_detected': bool
            }
        }

    Examples:
        >>> extract_metadata_from_sources(
        ...     Path("Frankiewicz Janusz - Gorejące ognie"),
        ...     id3_title="exsite.pl",
        ...     id3_author="exsite.pl"
        ... )
        {
            'folder': {
                'raw': 'Frankiewicz Janusz - Gorejące ognie',
                'cleaned': 'Frankiewicz Janusz Gorejące ognie',
                'valid': True
            },
            'id3': {
                'title': '',
                'author': '',
                'album': '',
                'valid': False,
                'garbage_detected': True
            }
        }
    """
    result = {
        'folder': {},
        'id3': {}
    }

    # Process folder name
    folder_name = folder_path.name
    cleaned_folder = clean_folder_name(folder_name)

    result['folder'] = {
        'raw': folder_name,
        'cleaned': cleaned_folder,
        'valid': len(cleaned_folder) >= 3
    }

    # Process ID3 tags
    cleaned_title = clean_id3_field(id3_title) if id3_title else ""
    cleaned_author = clean_id3_field(id3_author) if id3_author else ""
    cleaned_album = clean_id3_field(id3_album) if id3_album else ""

    # Check for garbage indicators
    garbage_detected = False
    if id3_title and is_garbage_data(id3_title):
        garbage_detected = True
    if id3_author and is_garbage_data(id3_author):
        garbage_detected = True
    if is_duplicate_fields(id3_title, id3_author):
        garbage_detected = True

    result['id3'] = {
        'title': cleaned_title,
        'author': cleaned_author,
        'album': cleaned_album,
        'valid': bool(cleaned_title and cleaned_author),
        'garbage_detected': garbage_detected
    }

    return result


def generate_search_alternatives(metadata: Dict[str, Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Generate search term alternatives from multiple metadata sources.

    Args:
        metadata: Dictionary from extract_metadata_from_sources()

    Returns:
        List of search alternatives with priority order:
        [
            {'source': 'id3', 'term': 'Title by Author', 'priority': 1},
            {'source': 'folder', 'term': 'Cleaned Folder Name', 'priority': 2}
        ]

    Examples:
        >>> metadata = {
        ...     'folder': {'cleaned': 'Frankiewicz Janusz Gorejące ognie', 'valid': True},
        ...     'id3': {'title': '', 'author': '', 'valid': False, 'garbage_detected': True}
        ... }
        >>> generate_search_alternatives(metadata)
        [{'source': 'folder', 'term': 'Frankiewicz Janusz Gorejące ognie', 'priority': 1}]
    """
    alternatives = []

    # Priority 1: Valid ID3 data (if not garbage)
    id3_data = metadata.get('id3', {})
    if id3_data.get('valid') and not id3_data.get('garbage_detected'):
        if id3_data['title'] and id3_data['author']:
            alternatives.append({
                'source': 'id3',
                'term': f"{id3_data['title']} by {id3_data['author']}",
                'priority': 1,
                'details': f"Title: {id3_data['title']}, Author: {id3_data['author']}"
            })

    # Priority 2: Folder name (always include if valid)
    folder_data = metadata.get('folder', {})
    if folder_data.get('valid'):
        alternatives.append({
            'source': 'folder',
            'term': folder_data['cleaned'],
            'priority': 2 if alternatives else 1,  # Priority 1 if ID3 invalid
            'details': f"Folder: {folder_data['raw']}"
        })

    # Sort by priority
    alternatives.sort(key=lambda x: x['priority'])

    return alternatives
