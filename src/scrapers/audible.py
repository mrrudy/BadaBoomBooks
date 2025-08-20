"""
Audible.com scraper implementation.

This module handles scraping metadata from Audible's API endpoints.
"""

import json
import re
import logging as log
from typing import Any, Dict
from bs4 import BeautifulSoup

from .base import BaseScraper
from ..models import BookMetadata


class AudibleScraper(BaseScraper):
    """Scraper for Audible.com API."""
    
    def __init__(self):
        super().__init__("audible", "audible.com")
    
    def preprocess_url(self, metadata: BookMetadata) -> None:
        """Extract ASIN from Audible URL."""
        match = re.search(r"^http.+audible.+/pd/[\w-]+Audiobook/(\w{10})", metadata.url)
        if match:
            metadata.asin = match.group(1)
        else:
            log.warning(f"Could not extract ASIN from Audible URL: {metadata.url}")
    
    def scrape_metadata(self, metadata: BookMetadata, response, logger: log.Logger) -> BookMetadata:
        """
        Extract metadata from Audible API response.
        
        Args:
            metadata: BookMetadata object to populate
            response: HTTP response from Audible API
            logger: Logger instance
            
        Returns:
            Updated BookMetadata object
        """
        try:
            page = response.json()['product']
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse Audible API response: {e}")
            metadata.mark_as_failed(f"JSON parsing error: {e}")
            return metadata
        
        return self._extract_metadata_from_api_data(metadata, page, logger)
    
    def _extract_metadata_from_api_data(self, metadata: BookMetadata, page: Dict[str, Any], logger: log.Logger) -> BookMetadata:
        """Extract metadata from parsed API data."""
        
        # === AUTHOR ===
        try:
            authors = page.get('authors', [])
            if authors:
                metadata.author = authors[0]['name']
                if len(authors) > 1:
                    metadata.authors_multi = authors
        except Exception as e:
            logger.info(f"No author in API response, using '_unknown_' ({metadata.input_folder}) | {e}")
            print(f" - Warning: No author found, placing in author folder '_unknown_': {metadata.input_folder}")
            metadata.author = '_unknown_'
        
        # === TITLE ===
        try:
            metadata.title = page.get('title', '')
        except Exception as e:
            logger.info(f"No title in API response, using folder name ({metadata.input_folder}) | {e}")
            print(f" - Warning: No title found, using folder name: {metadata.input_folder}")
            metadata.title = metadata.input_folder
        
        # === SUMMARY ===
        try:
            publisher_summary = page.get('publisher_summary', '')
            if publisher_summary:
                summary_soup = BeautifulSoup(publisher_summary, 'html.parser')
                metadata.summary = summary_soup.get_text()
                logger.info(f"Summary element: {str(summary_soup)}")
        except Exception as e:
            logger.info(f"No summary in API response, leaving blank ({metadata.input_folder}) | {e}")
        
        # === SUBTITLE ===
        try:
            metadata.subtitle = page.get('subtitle', '')
        except Exception as e:
            logger.info(f"No subtitle in API response, leaving blank ({metadata.input_folder}) | {e}")
        
        # === NARRATOR ===
        try:
            narrators = page.get('narrators', [])
            if narrators:
                metadata.narrator = narrators[0]['name']
                if len(narrators) > 1:
                    metadata.narrators_multi = narrators
        except Exception as e:
            logger.info(f"No narrator in API response, leaving blank ({metadata.input_folder}) | {e}")
        
        # === PUBLISHER ===
        try:
            metadata.publisher = page.get('publisher_name', '')
            logger.info(f"Publisher: {metadata.publisher}")
        except Exception as e:
            logger.info(f"No publisher in API response, leaving blank ({metadata.input_folder}) | {e}")
        
        # === PUBLISH YEAR ===
        try:
            release_date = page.get('release_date', '')
            if release_date:
                year_match = re.search(r"(\d{4})", release_date)
                if year_match:
                    metadata.publishyear = year_match.group(1)
                    logger.info(f"Publish year: {metadata.publishyear}")
        except Exception as e:
            logger.info(f"No publish year in API response, leaving blank ({metadata.input_folder}) | {e}")
        
        # === SERIES ===
        try:
            series = page.get('series', [])
            if series:
                metadata.series = series[0]['title']
                if len(series) > 1:
                    metadata.series_multi = series
        except Exception as e:
            logger.info(f"No series in API response, leaving blank ({metadata.input_folder}) | {e}")
        
        # === VOLUME NUMBER ===
        try:
            series = page.get('series', [])
            if series and 'sequence' in series[0]:
                metadata.volumenumber = str(series[0]['sequence'])
                logger.info(f"Volume number: {metadata.volumenumber}")
        except Exception as e:
            logger.info(f"No volume number in API response, leaving blank ({metadata.input_folder}) | {e}")
        
        # === LANGUAGE ===
        try:
            metadata.language = page.get('language', '')
        except Exception as e:
            logger.info(f"No language in API response, leaving blank ({metadata.input_folder}) | {e}")
        
        # === COVER URL ===
        try:
            product_images = page.get('product_images', {})
            if product_images and '500' in product_images:
                metadata.cover_url = product_images['500']
            elif product_images and '300' in product_images:
                metadata.cover_url = product_images['300']
        except Exception as e:
            logger.info(f"No cover URL in API response, leaving blank ({metadata.input_folder}) | {e}")
        
        return metadata


# Legacy function for backward compatibility
def api_audible(metadata: BookMetadata, page: Dict[str, Any], logger: log.Logger) -> BookMetadata:
    """
    Legacy function for backward compatibility.
    
    Args:
        metadata: BookMetadata object
        page: Parsed API response data
        logger: Logger instance
        
    Returns:
        Updated BookMetadata object
    """
    scraper = AudibleScraper()
    return scraper._extract_metadata_from_api_data(metadata, page, logger)
