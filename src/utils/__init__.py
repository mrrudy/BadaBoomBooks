"""
Utility functions and helper modules.

This package contains common utility functions and specialized modules
used across the application.
"""

# Import all helper functions from helpers module for backward compatibility
from .helpers import (
    clean_filename,
    extract_search_terms_from_audio_files,
    generate_search_term,
    detect_url_site,
    find_audio_files,
    has_audio_files,
    find_metadata_opf,
    encode_for_config,
    decode_from_config,
    wait_with_backoff,
    validate_path,
    calculate_padding_for_tracks,
    sanitize_xml_text,
    format_file_size,
    get_folder_size,
    normalize_series_volume,
    safe_encode_text,
    ProgressTracker
)

# Import genre normalization utilities
from .genre_normalizer import (
    GenreNormalizer,
    normalize_genres,
    get_normalizer
)

__all__ = [
    # Helper functions
    'clean_filename',
    'extract_search_terms_from_audio_files',
    'generate_search_term',
    'detect_url_site',
    'find_audio_files',
    'has_audio_files',
    'find_metadata_opf',
    'encode_for_config',
    'decode_from_config',
    'wait_with_backoff',
    'validate_path',
    'calculate_padding_for_tracks',
    'sanitize_xml_text',
    'format_file_size',
    'get_folder_size',
    'normalize_series_volume',
    'safe_encode_text',
    'ProgressTracker',
    # Genre normalization
    'GenreNormalizer',
    'normalize_genres',
    'get_normalizer'
]
