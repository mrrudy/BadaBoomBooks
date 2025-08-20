"""
Processors package initialization.

This package contains all file processing operations including
file organization, metadata creation, and audio file manipulation.
"""

from .file_operations import FileProcessor
from .metadata_operations import MetadataProcessor
from .audio_operations import AudioProcessor

__all__ = [
    'FileProcessor',
    'MetadataProcessor', 
    'AudioProcessor'
]
