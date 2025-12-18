"""
Base scraper functionality and HTTP request utilities.

This module provides the base classes and common functionality 
used by all site-specific scrapers.
"""

import time
import requests
import logging as log
from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, Optional

from ..models import BookMetadata
from ..utils import wait_with_backoff
from ..utils.rate_limiter import DomainRateLimiter


class BaseScraper(ABC):
    """
    Abstract base class for all website scrapers.
    
    Each scraper should inherit from this class and implement
    the required abstract methods for their specific site.
    """
    
    def __init__(self, site_name: str, domain: str):
        self.site_name = site_name
        self.domain = domain
    
    @abstractmethod
    def scrape_metadata(self, metadata: BookMetadata, response: requests.Response, logger: log.Logger) -> BookMetadata:
        """
        Extract metadata from a website response.
        
        Args:
            metadata: BookMetadata object to populate
            response: HTTP response from the website
            logger: Logger instance
            
        Returns:
            Updated BookMetadata object
        """
        pass
    
    @abstractmethod 
    def preprocess_url(self, metadata: BookMetadata) -> None:
        """
        Preprocess the URL to extract necessary parameters.
        
        Args:
            metadata: BookMetadata object with URL to preprocess
        """
        pass
    
    def make_http_request(self, metadata: BookMetadata, logger: log.Logger, 
                         url: Optional[str] = None, params: Optional[Dict] = None) -> Tuple[BookMetadata, requests.Response]:
        """
        Make HTTP request with error handling and retries.
        
        Args:
            metadata: BookMetadata object
            logger: Logger instance
            url: Optional URL override
            params: Optional query parameters
            
        Returns:
            Tuple of (metadata, response)
        """
        return http_request_generic(metadata, logger, url, params)


def http_request_generic(metadata: BookMetadata, logger: log.Logger, 
                        url: Optional[str] = None, query: Optional[Dict] = None) -> Tuple[BookMetadata, requests.Response]:
    """
    Generic HTTP request function with retry logic.
    
    Args:
        metadata: BookMetadata object containing URL
        logger: Logger instance
        url: Optional URL override
        query: Optional query parameters
        
    Returns:
        Tuple of (metadata, response)
    """
    request_url = url or metadata.url
    logger.info(f"Making HTTP request to: {request_url}")
    
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:108.0) Gecko/20100101 Firefox/108.0'
    }
    
    max_attempts = 5
    attempt = 1

    while attempt <= max_attempts:
        # Acquire domain rate limit lock to prevent concurrent requests to same domain
        DomainRateLimiter.acquire(request_url)

        try:
            if url and query:
                response = requests.get(url, params=query, headers=headers)
            else:
                response = requests.get(request_url, headers=headers)

            logger.info(f"HTTP status code: {response.status_code}")
            # Log response size instead of full content to keep logs manageable
            logger.debug(f"Response received: {len(response.text)} characters")

            if response.status_code != requests.codes.ok:
                logger.error(f"HTTP error: {response.status_code}")
                DomainRateLimiter.release(request_url)  # Release lock before retry
                if attempt == max_attempts:
                    metadata.mark_as_failed(f"HTTP error: {response.status_code}")
                else:
                    wait_with_backoff(attempt)
                    attempt += 1
                    continue

            response.raise_for_status()
            DomainRateLimiter.release(request_url)  # Release lock on success
            return metadata, response
            
        except requests.exceptions.RequestException as exc:
            logger.error(f"HTTP request error (attempt {attempt}): {exc}")
            DomainRateLimiter.release(request_url)  # Release lock on exception
            if attempt == max_attempts:
                print(f"Failed to get webpage after {max_attempts} attempts, skipping {metadata.input_folder}...")
                metadata.mark_as_failed(f"HTTP request failed: {exc}")
                break
            else:
                if attempt == 1:
                    print(f'\nBad response from webpage, retrying for up to 25 seconds...')
                wait_with_backoff(attempt)
                attempt += 1

    return metadata, requests.Response()


def http_request_audible_api(metadata: BookMetadata, logger: log.Logger) -> Tuple[BookMetadata, requests.Response]:
    """
    Make HTTP request to Audible API with specific parameters.
    
    Args:
        metadata: BookMetadata object with ASIN
        logger: Logger instance
        
    Returns:
        Tuple of (metadata, response)
    """
    api_url = f"https://api.audible.com/1.0/catalog/products/{metadata.asin}"
    params = {
        'response_groups': 'contributors,product_desc,series,product_extended_attrs,media'
    }
    
    return http_request_generic(metadata, logger, api_url, params)


def preprocess_audible_url(metadata: BookMetadata) -> None:
    """
    Extract ASIN from Audible URL and add to metadata.
    
    Args:
        metadata: BookMetadata object with Audible URL
    """
    import re
    
    match = re.search(r"^http.+audible.+/pd/[\w-]+Audiobook/(\w{10})", metadata.url)
    if match:
        metadata.asin = match.group(1)
    else:
        log.warning(f"Could not extract ASIN from Audible URL: {metadata.url}")
