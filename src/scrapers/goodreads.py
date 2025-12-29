"""
Goodreads.com scraper implementation.

This module handles scraping metadata from Goodreads book pages.
"""

import json
import re
import logging as log
from datetime import datetime
from bs4 import BeautifulSoup

from .base import BaseScraper
from ..models import BookMetadata


class GoodreadsScraper(BaseScraper):
    """Scraper for Goodreads.com book pages."""
    
    def __init__(self):
        super().__init__("goodreads", "goodreads.com")
    
    def preprocess_url(self, metadata: BookMetadata) -> None:
        """Goodreads URLs don't need preprocessing."""
        pass
    
    def scrape_metadata(self, metadata: BookMetadata, response, logger: log.Logger) -> BookMetadata:
        """
        Extract metadata from Goodreads page response.
        
        Args:
            metadata: BookMetadata object to populate
            response: HTTP response from Goodreads
            logger: Logger instance
            
        Returns:
            Updated BookMetadata object
        """
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Detect which type of Goodreads page this is
        if soup.select_one('#bookTitle'):
            return self._scrape_type1_page(metadata, soup, logger)
        else:
            return self._scrape_type2_page(metadata, soup, logger)
    
    def _scrape_type1_page(self, metadata: BookMetadata, soup: BeautifulSoup, logger: log.Logger) -> BookMetadata:
        """Scrape older Goodreads page format."""
        logger.debug(f"Scraping Goodreads Type 1 for metadata: {metadata.input_folder}")
        
        # === AUTHOR ===
        try:
            element = soup.select_one('#bookAuthors')
            if element:
                author_link = element.find('a')
                if author_link:
                    raw_text = author_link.get_text(strip=False)
                    metadata.author = ' '.join(raw_text.split())
                    logger.info(f"Author element: {str(element)}")
        except Exception as e:
            logger.info(f"No author found, using '_unknown_' ({metadata.input_folder}) | {e}")
            print(f" - Warning: No author scraped, placing in author folder '_unknown_': {metadata.input_folder}")
            metadata.author = '_unknown_'
        
        # === TITLE ===
        try:
            element = soup.select_one('#bookTitle')
            if element:
                metadata.title = element.get_text(strip=True)
                logger.info(f"Title element: {str(element)}")
        except Exception as e:
            logger.info(f"No title scraped, using folder name ({metadata.input_folder}) | {e}")
            print(f" - Warning: No title scraped, using folder name: {metadata.input_folder}")
            metadata.title = metadata.input_folder
        
        # === SUMMARY ===
        try:
            element = soup.select_one('#description')
            if element:
                summary_spans = element.find_all('span')
                if len(summary_spans) > 1:
                    metadata.summary = summary_spans[1].get_text()
                elif summary_spans:
                    metadata.summary = summary_spans[0].get_text()
                logger.info(f"Summary element: {str(element)}")
        except Exception as e:
            logger.info(f"No summary scraped, leaving blank ({metadata.input_folder}) | {e}")
        
        # === SERIES ===
        try:
            element = soup.select_one('#bookSeries')
            if element:
                series_text = element.get_text(strip=True)
                series_match = re.search(r'(\w.+),? #\d+', series_text)
                if series_match:
                    metadata.series = series_match.group(1)
                    
                    # Extract volume number
                    volume_match = re.search(r'\w.+,? #([\d\.]+)', series_text)
                    if volume_match:
                        metadata.volumenumber = volume_match.group(1)
                        
                logger.info(f"Series element: {str(element)}")
        except Exception as e:
            logger.info(f"No series scraped, leaving blank ({metadata.input_folder}) | {e}")
        
        # === GENRES ===
        try:
            genres_list = []
            genres_container = soup.select('div[data-testid="genresList"]')
            if genres_container:
                genre_buttons = genres_container[0].select('a.Button--tag span.Button__labelItem')
                for button in genre_buttons:
                    genre_text = button.get_text(strip=True)
                    if genre_text and genre_text != "Genres":
                        genres_list.append(genre_text)
                metadata.genres = ','.join(genres_list)
        except Exception as e:
            logger.info(f"No genres scraped, leaving blank ({metadata.input_folder}) | {e}")

        # === COVER URL ===
        try:
            cover_url = ""

            # Try ResponsiveImage img tag first (more reliable for actual book covers)
            img_tag = soup.select_one('img.ResponsiveImage')
            if img_tag and img_tag.get("src"):
                cover_url = img_tag["src"].strip()

            # Fallback: Try meta og:image
            if not cover_url:
                meta_img = soup.find("meta", property="og:image")
                if meta_img and meta_img.get("content"):
                    cover_url = meta_img["content"].strip()

            metadata.cover_url = cover_url
            logger.info(f"Cover URL scraped: {cover_url}")
        except Exception as e:
            logger.info(f"No cover scraped ({metadata.input_folder}) | {e}")

        return metadata
    
    def _scrape_type2_page(self, metadata: BookMetadata, soup: BeautifulSoup, logger: log.Logger) -> BookMetadata:
        """Scrape newer Goodreads page format with JSON-LD."""
        logger.debug(f"Scraping Goodreads Type 2 for metadata: {metadata.input_folder}")
        
        # Parse JSON-LD data
        jsonld = self._extract_jsonld_data(soup, logger)
        
        # Parse structured data from script tag
        try:
            script_tag = soup.select_one("script[type='application/ld+json']")
            if script_tag:
                data = json.loads(script_tag.get_text(strip=True))
            else:
                data = None
        except Exception as exc:
            logger.error(f"JSON parsing error: {exc}")
            print(f"Could not prepare JSON object, skipping {metadata.input_folder}...")
            metadata.mark_as_failed(f"BS4 to JSON loads: {exc}")
            return metadata
        
        # === AUTHOR ===
        try:
            if data and 'author' in data and data['author']:
                author_name = data['author'][0]['name']
                metadata.author = ' '.join(author_name.split())
                logger.info(f"Author from JSON: {author_name}")
        except Exception as e:
            logger.info(f"No author found, using '_unknown_' ({metadata.input_folder}) | {e}")
            print(f" - Warning: No author scraped, placing in author folder '_unknown_': {metadata.input_folder}")
            metadata.author = '_unknown_'
        
        # === TITLE ===
        try:
            if data and 'name' in data:
                # Strip series information in parentheses like "(Series Name #N)" or "(Series Name, #N)"
                title_match = re.search(r'^(.+?)\s*\([^)]*#[\d\.,\-]+\)$', data['name'])
                if title_match:
                    metadata.title = title_match.group(1)
                else:
                    metadata.title = data['name']
                logger.info(f"Title from JSON: {metadata.title}")
        except Exception as e:
            logger.info(f"No title scraped, using folder name ({metadata.input_folder}) | {e}")
            print(f" - Warning: No title scraped, using folder name: {metadata.input_folder}")
            metadata.title = metadata.input_folder

        # === SUBTITLE (Original Title) ===
        try:
            html_text = str(soup)
            subtitle_match = re.search(r'"originalTitle"\s*:\s*"([^"]+)"', html_text)
            if subtitle_match:
                metadata.subtitle = subtitle_match.group(1)
                logger.info(f"Subtitle (original title) scraped: {metadata.subtitle}")
        except Exception as e:
            logger.info(f"Exception while scraping subtitle ({metadata.input_folder}) | {e}")
        
        # === SUMMARY ===
        try:
            element = soup.select_one("div[data-testid='description']")
            if element:
                summary_element = element.select_one("span[class='Formatted']")
                if summary_element:
                    metadata.summary = summary_element.get_text()
                    logger.info(f"Summary element found")
        except Exception as e:
            logger.info(f"No summary scraped, leaving blank ({metadata.input_folder}) | {e}")
        
        # === SERIES ===
        try:
            element = soup.select_one("div[class='BookPageTitleSection__title']")
            if element:
                series_element = element.select_one('h3')
                if series_element:
                    series_text = series_element.get_text(strip=True)
                    series_match = re.search(r'^(.+?)\s*#([\d\-,\.]+)$', series_text)
                    if series_match:
                        metadata.series = series_match.group(1)
                        raw_number = series_match.group(2).replace('-', ',').replace(' ', '')
                        metadata.volumenumber = raw_number
                    else:
                        metadata.series = series_text
                    logger.info(f"Series element: {series_text}")
        except Exception as e:
            logger.info(f"No series scraped, leaving blank ({metadata.input_folder}) | {e}")
        
        # === GENRES ===
        try:
            genres_list = []
            genres_container = soup.select('div[data-testid="genresList"]')
            if genres_container:
                genre_buttons = genres_container[0].select('a.Button--tag span.Button__labelItem')
                for button in genre_buttons:
                    genre_text = button.get_text(strip=True)
                    if genre_text and genre_text != "Genres":
                        genres_list.append(genre_text)
                metadata.genres = ','.join(genres_list)
        except Exception as e:
            logger.info(f"No genres scraped, leaving blank ({metadata.input_folder}) | {e}")
        
        # === LANGUAGE ===
        try:
            from ..language_map import LANGUAGE_MAP
            
            language = None
            if jsonld and "inLanguage" in jsonld:
                language = jsonld["inLanguage"]
            
            if not language:
                html_text = str(soup)
                lang_match = re.search(r'"language":\s*{[^}]*"name":"([^"]+)"', html_text)
                if lang_match:
                    language = lang_match.group(1)
            
            if language:
                lang_key = language.strip().lower()
                iso_code = LANGUAGE_MAP.get(lang_key, language)
                metadata.language = iso_code
                logger.info(f"Language scraped: {language} -> {iso_code}")
        except Exception as e:
            logger.info(f"Exception while scraping language ({metadata.input_folder}) | {e}")
        
        # === ISBN ===
        try:
            isbn = None
            if jsonld and "isbn" in jsonld:
                isbn = jsonld["isbn"]

            if not isbn:
                html_text = str(soup)
                isbn_match = re.search(r'"isbn"\s*:\s*"(\d+)"', html_text)
                if isbn_match:
                    isbn = isbn_match.group(1)

            if isbn:
                metadata.isbn = isbn
                logger.info(f"ISBN scraped: {isbn}")
        except Exception as e:
            logger.info(f"Exception while scraping ISBN ({metadata.input_folder}) | {e}")

        # === PUBLISHER ===
        try:
            html_text = str(soup)
            # Try simple key-value format first
            publisher_match = re.search(r'"publisher"\s*:\s*"([^"]+)"', html_text)
            if not publisher_match:
                # Try nested object format
                publisher_match = re.search(r'"publisher":\s*{[^}]*"name":"([^"]+)"', html_text)
            if publisher_match:
                metadata.publisher = publisher_match.group(1)
                logger.info(f"Publisher scraped: {metadata.publisher}")
        except Exception as e:
            logger.info(f"Exception while scraping publisher ({metadata.input_folder}) | {e}")

        # === PUBLISH DATE ===
        try:
            html_text = str(soup)
            date_match = re.search(r'first published\s+([^<"]+)', html_text, re.IGNORECASE)
            if date_match:
                date_str = date_match.group(1).strip()
                # Try to parse and convert to YYYY-MM-DD format
                try:
                    # Try common date formats
                    for fmt in ['%B %d, %Y', '%b %d, %Y', '%Y-%m-%d', '%Y']:
                        try:
                            parsed_date = datetime.strptime(date_str, fmt)
                            metadata.publishyear = parsed_date.strftime('%Y-%m-%d')
                            logger.info(f"Publish date scraped and formatted: {date_str} -> {metadata.publishyear}")
                            break
                        except ValueError:
                            continue
                    else:
                        # If no format matched, store as-is
                        metadata.publishyear = date_str
                        logger.info(f"Publish date scraped (unparsed): {date_str}")
                except Exception as parse_error:
                    # If parsing fails, store raw string
                    metadata.publishyear = date_str
                    logger.info(f"Publish date scraped (parse failed): {date_str}")
        except Exception as e:
            logger.info(f"Exception while scraping publish date ({metadata.input_folder}) | {e}")

        # === ASIN ===
        try:
            html_text = str(soup)
            asin_match = re.search(r'"asin"\s*:\s*"([^"]+)"', html_text, re.IGNORECASE)
            if asin_match:
                metadata.asin = asin_match.group(1)
                logger.info(f"ASIN scraped: {metadata.asin}")
        except Exception as e:
            logger.info(f"Exception while scraping ASIN ({metadata.input_folder}) | {e}")

        # === COVER URL ===
        try:
            cover_url = ""

            # Try ResponsiveImage img tag first (most reliable for actual book covers)
            img_tag = soup.select_one('img.ResponsiveImage')
            if img_tag and img_tag.get("src"):
                cover_url = img_tag["src"].strip()

            # Fallback: Try JSON-LD data
            if not cover_url and jsonld and "image" in jsonld:
                cover_url = jsonld["image"].strip()

            # Fallback: Try meta og:image
            if not cover_url:
                meta_img = soup.find("meta", property="og:image")
                if meta_img and meta_img.get("content"):
                    cover_url = meta_img["content"].strip()

            metadata.cover_url = cover_url
            logger.info(f"Cover URL scraped: {cover_url}")
        except Exception as e:
            logger.info(f"No cover scraped ({metadata.input_folder}) | {e}")

        return metadata
    
    def _extract_jsonld_data(self, soup: BeautifulSoup, logger: log.Logger) -> dict:
        """Extract JSON-LD structured data from the page."""
        try:
            jsonld_script = soup.find("script", {"type": "application/ld+json"})
            if jsonld_script:
                return json.loads(jsonld_script.get_text(strip=True))
        except Exception as e:
            logger.error(f"JSON-LD parsing error: {e}")
        return {}


# Legacy functions for backward compatibility
def scrape_goodreads_type1(soup: BeautifulSoup, metadata: BookMetadata, logger: log.Logger) -> BookMetadata:
    """Legacy function for backward compatibility."""
    scraper = GoodreadsScraper()
    return scraper._scrape_type1_page(metadata, soup, logger)


def scrape_goodreads_type2(soup: BeautifulSoup, metadata: BookMetadata, logger: log.Logger) -> BookMetadata:
    """Legacy function for backward compatibility."""
    scraper = GoodreadsScraper()
    return scraper._scrape_type2_page(metadata, soup, logger)
