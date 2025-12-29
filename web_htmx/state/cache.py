"""
LLM Connection Cache Module

Provides a singleton cache for LLM connection test results with 5-minute TTL.
Thread-safe implementation for web environment.
"""

import threading
import time
from typing import Optional, Dict
from datetime import datetime, timedelta


class LLMConnectionCache:
    """
    Singleton cache for LLM connection test results.

    Caches connection status for 5 minutes to avoid excessive API calls.
    Thread-safe for concurrent web requests.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize cache state."""
        self._cache: Optional[Dict] = None
        self._cached_at: Optional[datetime] = None
        self._ttl_seconds = 300  # 5 minutes
        self._data_lock = threading.Lock()

    def get(self, force: bool = False) -> Dict:
        """
        Get LLM connection status from cache or test fresh.

        Args:
            force: If True, bypass cache and test connection

        Returns:
            Dict with keys:
                - available (bool): Whether LLM is available
                - cached (bool): Whether result came from cache
                - cache_age (int): Age of cache in seconds (0 if fresh)
                - tested_at (str): ISO timestamp of test
                - error (str, optional): Error message if unavailable
        """
        with self._data_lock:
            # Check if cached result is still valid
            if not force and self._cache is not None and self._cached_at is not None:
                age = (datetime.now() - self._cached_at).total_seconds()
                if age < self._ttl_seconds:
                    return {
                        **self._cache,
                        'cached': True,
                        'cache_age': int(age)
                    }

            # Test connection fresh
            result = self._test_connection()

            # Update cache
            self._cache = result
            self._cached_at = datetime.now()

            return {
                **result,
                'cached': False,
                'cache_age': 0
            }

    def _test_connection(self) -> Dict:
        """
        Test LLM connection by attempting to import and initialize.

        Returns:
            Dict with connection status and metadata
        """
        try:
            # Import here to avoid circular dependencies
            import sys
            import os

            # Get the root project directory
            root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            src_dir = os.path.join(root_dir, 'src')

            # Ensure both root and src are in path
            if root_dir not in sys.path:
                sys.path.insert(0, root_dir)
            if src_dir not in sys.path:
                sys.path.insert(0, src_dir)

            # Import using absolute import from src package
            from src.search.llm_scoring import test_llm_connection

            # Test connection
            available = test_llm_connection()

            return {
                'available': available,
                'tested_at': datetime.now().isoformat(),
                'error': None if available else 'LLM connection test failed'
            }

        except ImportError as e:
            return {
                'available': False,
                'tested_at': datetime.now().isoformat(),
                'error': f'Import error: {str(e)}'
            }
        except Exception as e:
            return {
                'available': False,
                'tested_at': datetime.now().isoformat(),
                'error': f'Connection test failed: {str(e)}'
            }

    def clear(self):
        """Clear the cache."""
        with self._data_lock:
            self._cache = None
            self._cached_at = None

    def get_cache_info(self) -> Dict:
        """
        Get cache metadata without testing.

        Returns:
            Dict with cache status information
        """
        with self._data_lock:
            if self._cache is None or self._cached_at is None:
                return {
                    'has_cache': False,
                    'cache_age': None,
                    'expires_in': None
                }

            age = (datetime.now() - self._cached_at).total_seconds()
            expires_in = max(0, self._ttl_seconds - age)

            return {
                'has_cache': True,
                'cache_age': int(age),
                'expires_in': int(expires_in),
                'cached_result': self._cache
            }


# Global instance
llm_cache = LLMConnectionCache()
