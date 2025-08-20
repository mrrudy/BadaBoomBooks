"""
BadaBoomBooks - Modular audiobook organization tool.

This package provides a complete audiobook organization solution with
web scraping, metadata management, and file processing capabilities.
"""

from .config import __version__
from .main import BadaBoomBooksApp

__all__ = ['BadaBoomBooksApp', '__version__']
