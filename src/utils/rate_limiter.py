"""
Domain-based rate limiting for web scraping.

Prevents multiple workers from overwhelming a single domain with concurrent requests.
"""

import threading
import time
import logging as log
from typing import Dict
from urllib.parse import urlparse


class DomainRateLimiter:
    """
    Rate limiter that ensures only one request per domain at a time across all workers.

    Uses threading locks to serialize requests to the same domain,
    preventing HTTP 429 (rate limiting) errors from services.
    """

    _locks: Dict[str, threading.Lock] = {}
    _lock_mutex = threading.Lock()  # Protects the _locks dictionary
    _last_request: Dict[str, float] = {}  # Track last request time per domain
    _min_delay = 0.5  # Minimum delay between requests to same domain (seconds)

    @classmethod
    def acquire(cls, url: str) -> None:
        """
        Acquire rate limit lock for the domain in the given URL.

        This ensures:
        1. Only one worker accesses the domain at a time
        2. Minimum delay between consecutive requests to the same domain

        Args:
            url: Full URL to extract domain from
        """
        domain = cls._extract_domain(url)

        # Get or create lock for this domain
        with cls._lock_mutex:
            if domain not in cls._locks:
                cls._locks[domain] = threading.Lock()
                cls._last_request[domain] = 0
            domain_lock = cls._locks[domain]

        # Acquire the domain lock (blocks if another worker is using it)
        domain_lock.acquire()

        # Ensure minimum delay since last request
        elapsed = time.time() - cls._last_request[domain]
        if elapsed < cls._min_delay:
            wait_time = cls._min_delay - elapsed
            log.debug(f"Rate limiting {domain}: waiting {wait_time:.2f}s")
            time.sleep(wait_time)

        # Update last request time
        cls._last_request[domain] = time.time()

    @classmethod
    def release(cls, url: str) -> None:
        """
        Release rate limit lock for the domain in the given URL.

        Args:
            url: Full URL to extract domain from
        """
        domain = cls._extract_domain(url)

        with cls._lock_mutex:
            if domain in cls._locks:
                cls._locks[domain].release()

    @staticmethod
    def _extract_domain(url: str) -> str:
        """
        Extract domain from URL for rate limiting.

        Args:
            url: Full URL

        Returns:
            Domain name (e.g., 'lubimyczytac.pl')
        """
        parsed = urlparse(url)
        return parsed.netloc or 'unknown'
