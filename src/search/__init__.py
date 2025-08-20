"""
Search package initialization.

This package contains all search and URL handling functionality
including automated search, candidate selection, and manual input.
"""

from .auto_search import AutoSearchEngine
from .manual_search import ManualSearchHandler  
from .candidate_selection import CandidateSelector

__all__ = [
    'AutoSearchEngine',
    'ManualSearchHandler',
    'CandidateSelector'
]
