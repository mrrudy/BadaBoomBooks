"""
Scrapers package initialization.

This package contains all web scraping functionality for different audiobook sites.
Each scraper is responsible for extracting metadata from a specific website.
"""

from .base import BaseScraper, http_request_generic, http_request_audible_api
from .audible import AudibleScraper
from .goodreads import GoodreadsScraper
from .lubimyczytac import LubimyczytacScraper

__all__ = [
    'BaseScraper',
    'http_request_generic',
    'http_request_audible_api', 
    'AudibleScraper',
    'GoodreadsScraper',
    'LubimyczytacScraper'
]
