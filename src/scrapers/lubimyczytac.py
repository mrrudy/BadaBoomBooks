"""
LubimyCzytac.pl scraper implementation.

This module handles scraping metadata from Polish book site lubimyczytac.pl.
"""

import json
import re
import logging as log
from bs4 import BeautifulSoup

from .base import BaseScraper
from ..models import BookMetadata
from ..utils import normalize_series_volume


class LubimyczytacScraper(BaseScraper):
    """Scraper for lubimyczytac.pl book pages."""
    
    def __init__(self):
        super().__init__("lubimyczytac", "lubimyczytac.pl")
    
    def preprocess_url(self, metadata: BookMetadata) -> None:
        """LubimyCzytac URLs don't need preprocessing."""
        pass
    
    def scrape_metadata(self, metadata: BookMetadata, response, logger: log.Logger) -> BookMetadata:
        """
        Extract metadata from lubimyczytac.pl page response.
        
        Args:
            metadata: BookMetadata object to populate
            response: HTTP response from lubimyczytac.pl
            logger: Logger instance
            
        Returns:
            Updated BookMetadata object
        """
        soup = BeautifulSoup(response.text, 'html.parser')
        logger.debug(f"Scraping lubimyczytac.pl for metadata: {metadata.input_folder}")
        
        return self._extract_all_metadata(metadata, soup, logger)
    
    def _extract_all_metadata(self, metadata: BookMetadata, soup: BeautifulSoup, logger: log.Logger) -> BookMetadata:
        """Extract all metadata from the parsed page."""
        
        # === TITLE ===
        self._extract_title(metadata, soup, logger)
        
        # === AUTHOR ===
        self._extract_author(metadata, soup, logger)
        
        # === ORIGINAL TITLE (SUBTITLE) ===
        self._extract_original_title(metadata, soup, logger)
        
        # === SERIES AND VOLUME ===
        self._extract_series_info(metadata, soup, logger)
        
        # === SUMMARY ===
        self._extract_summary(metadata, soup, logger)
        
        # === GENRES ===
        self._extract_genres(metadata, soup, logger)
        
        # === LANGUAGE ===
        self._extract_language(metadata, soup, logger)
        
        # === ISBN ===
        self._extract_isbn(metadata, soup, logger)
        
        # === DATE PUBLISHED ===
        self._extract_publication_date(metadata, soup, logger)
        
        # === COVER URL ===
        self._extract_cover_url(metadata, soup, logger)
        
        return metadata
    
    def _extract_title(self, metadata: BookMetadata, soup: BeautifulSoup, logger: log.Logger):
        """Extract book title."""
        try:
            # Try meta og:title first (usually "Title | Author")
            meta_title = soup.find("meta", property="og:title")
            if meta_title and meta_title.get("content"):
                title = meta_title["content"].split("|")[0].strip()
                metadata.title = title
            else:
                # Fallback to page title
                element = soup.select_one('h1.book__title')
                if element:
                    metadata.title = element.get_text(strip=True)
        except Exception as e:
            logger.info(f"No title scraped ({metadata.input_folder}) | {e}")
    
    def _extract_author(self, metadata: BookMetadata, soup: BeautifulSoup, logger: log.Logger):
        """Extract book author."""
        try:
            # Try meta books:author first
            meta_author = soup.find("meta", property="books:author")
            if meta_author and meta_author.get("content"):
                metadata.author = meta_author["content"].strip()
            else:
                # Fallback to page author link
                element = soup.select_one('a.author__link')
                if element:
                    metadata.author = element.get_text(strip=True)
        except Exception as e:
            logger.info(f"No author scraped ({metadata.input_folder}) | {e}")
    
    def _extract_original_title(self, metadata: BookMetadata, soup: BeautifulSoup, logger: log.Logger):
        """Extract original title (stored as subtitle)."""
        try:
            original_title = ""
            for dt in soup.select('dt'):
                if dt.get_text(strip=True).lower().startswith("tytuł oryginału"):
                    dd = dt.find_next_sibling('dd')
                    if dd:
                        original_title = dd.get_text(strip=True)
                        break
            metadata.subtitle = original_title
        except Exception as e:
            logger.info(f"No original title scraped ({metadata.input_folder}) | {e}")
    
    def _extract_series_info(self, metadata: BookMetadata, soup: BeautifulSoup, logger: log.Logger):
        """Extract series name and volume number."""
        try:
            series = ""
            volumenumber = ""
            
            # Look for "Cykl:" in the details
            for dt in soup.select('dt'):
                if dt.get_text(strip=True).lower().startswith("cykl"):
                    dd = dt.find_next_sibling('dd')
                    if dd:
                        series_text = dd.get_text(strip=True)
                        series, volumenumber = self._parse_series_text(series_text)
                        break
            
            # Fallback: try the old selector
            if not series:
                series_element = soup.select_one('a.book__series-link')
                if series_element:
                    series_text = series_element.get_text(strip=True)
                    series, volumenumber = self._parse_series_text(series_text)
            
            # Set default volume if still empty
            if not volumenumber:
                volumenumber = "0"
            
            metadata.series = series
            metadata.volumenumber = volumenumber
            
        except Exception as e:
            logger.info(f"No series scraped ({metadata.input_folder}) | {e}")
    
    def _parse_series_text(self, series_text: str) -> tuple:
        """Parse series text to extract series name and volume number."""
        series = ""
        volumenumber = ""
        
        # Example: "Pamiętniki Mordbota (tom 1-2)"
        match = re.match(r'(.+?)\s*\(tom\s*([^\)]+)\)', series_text)
        if match:
            series = match.group(1)
            raw_number = match.group(2).replace(' ', '')
            volumenumber = normalize_series_volume(raw_number)
        else:
            series = series_text
        
        return series, volumenumber
    
    def _extract_summary(self, metadata: BookMetadata, soup: BeautifulSoup, logger: log.Logger):
        """Extract book summary/description."""
        try:
            # Prefer the full description from the collapse-content
            desc_element = soup.select_one('div#book-description div.collapse-content')
            if desc_element:
                # Get all text, preserving line breaks between <p> tags
                paragraphs = desc_element.find_all(['p', 'br'])
                description = '\n'.join(p.get_text(separator=' ', strip=True) for p in paragraphs if p.name == 'p')
                if not description:
                    # fallback to all text
                    description = desc_element.get_text(separator='\n', strip=True)
                metadata.summary = description
            else:
                # Fallback to meta og:description
                meta_desc = soup.find("meta", property="og:description")
                if meta_desc and meta_desc.get("content"):
                    metadata.summary = meta_desc["content"].strip()
                else:
                    # Fallback to visible description
                    element = soup.select_one('div.book__description')
                    if element:
                        metadata.summary = element.get_text(strip=True)
        except Exception as e:
            logger.info(f"No summary scraped ({metadata.input_folder}) | {e}")
    
    def _extract_genres(self, metadata: BookMetadata, soup: BeautifulSoup, logger: log.Logger):
        """Extract book genres/tags."""
        try:
            genres_list = []
            
            # Try meta genre first
            meta_genre = soup.find("meta", property="genre")
            if meta_genre and meta_genre.get("content"):
                genres_list.append(meta_genre["content"].strip())
            
            # Fallback to visible tags
            genres_container = soup.select('a.book__category')
            for genre in genres_container:
                genre_text = genre.get_text(strip=True)
                if genre_text:
                    genres_list.append(genre_text)
            
            metadata.genres = ','.join(genres_list)
        except Exception as e:
            logger.info(f"No genres scraped ({metadata.input_folder}) | {e}")
    
    def _extract_language(self, metadata: BookMetadata, soup: BeautifulSoup, logger: log.Logger):
        """Extract book language."""
        try:
            from ..language_map import LANGUAGE_MAP
            
            # Try meta inLanguage first
            meta_lang = soup.find("meta", attrs={"property": "inLanguage"})
            if meta_lang and meta_lang.get("content"):
                language = meta_lang["content"].strip()
            else:
                # Fallback: look for "Język:" in details
                language = ""
                for dt in soup.select('dt'):
                    if dt.get_text(strip=True).lower().startswith("język"):
                        dd = dt.find_next_sibling('dd')
                        if dd:
                            language = dd.get_text(strip=True)
                            break
            
            # Default to Polish if no language found
            if not language:
                language = 'pol'
            
            # Convert to ISO code using LANGUAGE_MAP
            lang_key = language.strip().lower()
            iso_code = LANGUAGE_MAP.get(lang_key, language)
            metadata.language = iso_code
            
        except Exception as e:
            logger.info(f"No language scraped ({metadata.input_folder}) | {e}")
    
    def _extract_isbn(self, metadata: BookMetadata, soup: BeautifulSoup, logger: log.Logger):
        """Extract ISBN."""
        try:
            # Try meta books:isbn first
            meta_isbn = soup.find("meta", property="books:isbn")
            if meta_isbn and meta_isbn.get("content"):
                metadata.isbn = meta_isbn["content"].strip()
            else:
                # Fallback: look for "ISBN:" in details
                for dt in soup.select('dt'):
                    if dt.get_text(strip=True).lower().startswith("isbn"):
                        dd = dt.find_next_sibling('dd')
                        if dd:
                            metadata.isbn = dd.get_text(strip=True)
                            break
        except Exception as e:
            logger.info(f"No ISBN scraped ({metadata.input_folder}) | {e}")
    
    def _extract_publication_date(self, metadata: BookMetadata, soup: BeautifulSoup, logger: log.Logger):
        """Extract publication date."""
        try:
            # Try JSON-LD first
            jsonld_script = soup.find("script", {"type": "application/ld+json"})
            date_published = ""
            
            if jsonld_script:
                try:
                    jsonld = json.loads(jsonld_script.get_text(strip=True))
                    if isinstance(jsonld, dict) and "datePublished" in jsonld:
                        date_published = jsonld["datePublished"]
                except Exception as e:
                    logger.info(f"Could not parse JSON-LD for datePublished: {e}")
            
            # Store publication date if found
            if date_published:
                metadata.datepublished = date_published.strip()
            
        except Exception as e:
            logger.info(f"No datePublished scraped ({metadata.input_folder}) | {e}")
    
    def _extract_cover_url(self, metadata: BookMetadata, soup: BeautifulSoup, logger: log.Logger):
        """Extract cover image URL."""
        try:
            cover_url = ""
            
            # Try meta og:image first
            meta_img = soup.find("meta", property="og:image")
            if meta_img and meta_img.get("content"):
                cover_url = meta_img["content"].strip()
            
            # Fallback: look for image in the book cover section
            if not cover_url:
                img_tag = soup.select_one('div.book-cover img')
                if img_tag and img_tag.get("src"):
                    cover_url = img_tag["src"].strip()
            
            metadata.cover_url = cover_url
            
        except Exception as e:
            logger.info(f"No cover scraped ({metadata.input_folder}) | {e}")


# Legacy function for backward compatibility
def scrape_lubimyczytac(soup: BeautifulSoup, metadata: BookMetadata, logger: log.Logger) -> BookMetadata:
    """
    Legacy function for backward compatibility.
    
    Args:
        soup: BeautifulSoup parsed page
        metadata: BookMetadata object
        logger: Logger instance
        
    Returns:
        Updated BookMetadata object
    """
    scraper = LubimyczytacScraper()
    return scraper._extract_all_metadata(metadata, soup, logger)
