"""
Metadata operations processor.

This module handles creation of metadata files including OPF files,
info.txt files, and reading/writing metadata from various sources.
"""

import re
import xml.etree.ElementTree as ET
import logging as log
from pathlib import Path
from typing import Optional

from ..models import BookMetadata
from ..utils import sanitize_xml_text
from ..utils.genre_normalizer import normalize_genres


class MetadataProcessor:
    """Handles metadata file operations."""

    def __init__(self, dry_run: bool = False, use_llm: bool = False):
        self.dry_run = dry_run
        self.use_llm = use_llm
    
    def create_opf_file(self, metadata: BookMetadata, template_path: Path) -> bool:
        """
        Create an OPF metadata file for the audiobook.
        
        Args:
            metadata: BookMetadata object with book information
            template_path: Path to the OPF template file
            
        Returns:
            True if successful, False otherwise
        """
        if self.dry_run:
            print(f"[DRY-RUN] Would create OPF file in: {metadata.final_output}")
            return True
        
        try:
            print("Creating 'metadata.opf'")
            log.info(f"Creating OPF file for: {metadata.input_folder}")
            
            # Read template
            if not template_path.exists():
                log.error(f"OPF template not found: {template_path}")
                return False
            
            with template_path.open('r', encoding='utf-8') as file:
                template = file.read()
            
            # Fill template with metadata
            filled_template = self._fill_opf_template(template, metadata)
            
            # Write OPF file
            opf_output = metadata.final_output / 'metadata.opf'
            with opf_output.open('w', encoding='utf-8') as file:
                file.write(filled_template)
            
            log.info(f"Successfully created OPF file: {opf_output}")
            return True
            
        except Exception as e:
            log.error(f"Error creating OPF file for {metadata.input_folder}: {e}")
            metadata.mark_as_failed(f"OPF creation error: {e}")
            return False
    
    def create_info_file(self, metadata: BookMetadata) -> bool:
        """
        Create an info.txt file with book summary.
        
        Args:
            metadata: BookMetadata object with book information
            
        Returns:
            True if successful, False otherwise
        """
        if self.dry_run:
            print(f"[DRY-RUN] Would create info.txt in: {metadata.final_output}")
            return True
        
        try:
            print("Creating 'info.txt'")
            log.info(f"Creating info.txt for: {metadata.input_folder}")
            
            txt_file = metadata.final_output / 'info.txt'
            with txt_file.open('w', encoding='utf-8') as file:
                file.write(metadata.summary or "No summary available.")
            
            log.info(f"Successfully created info.txt: {txt_file}")
            return True
            
        except Exception as e:
            log.error(f"Error creating info.txt for {metadata.input_folder}: {e}")
            metadata.mark_as_failed(f"Info.txt creation error: {e}")
            return False
    
    def read_opf_metadata(self, opf_path: Path) -> BookMetadata:
        """
        Read metadata from an existing OPF file.
        
        Args:
            opf_path: Path to the OPF file
            
        Returns:
            BookMetadata object populated from OPF file
        """
        metadata = BookMetadata.create_empty(str(opf_path.parent))
        
        if not opf_path.exists():
            metadata.mark_as_failed(f"OPF file not found: {opf_path}")
            return metadata
        
        try:
            tree = ET.parse(opf_path)
            root = tree.getroot()
            
            # Define namespaces
            ns = {
                'dc': 'http://purl.org/dc/elements/1.1/',
                'opf': 'http://www.idpf.org/2007/opf',
                'calibre': 'http://calibre.kovidgoyal.net/2008/metadata'
            }
            
            # Extract standard fields
            metadata.title = self._get_element_text(root, './/dc:title', ns)
            metadata.subtitle = self._get_element_text(root, './/dc:subtitle', ns)
            metadata.summary = self._get_element_text(root, './/dc:description', ns)
            metadata.author = self._get_element_text(root, './/dc:creator[@opf:role="aut"]', ns)
            metadata.narrator = self._get_element_text(root, './/dc:creator[@opf:role="nrt"]', ns)
            metadata.publisher = self._get_element_text(root, './/dc:publisher', ns)
            metadata.publishyear = self._get_element_text(root, './/dc:date', ns)
            metadata.language = self._get_element_text(root, './/dc:language', ns)
            
            # Extract identifiers
            metadata.isbn = self._get_element_text(root, './/dc:identifier[@opf:scheme="ISBN"]', ns)
            metadata.asin = self._get_element_text(root, './/dc:identifier[@opf:scheme="ASIN"]', ns)
            
            # Extract genres
            genre_elements = root.findall('.//dc:subject', ns)
            if genre_elements:
                metadata.genres = ','.join([g.text for g in genre_elements if g.text])
            
            # Extract series and volume (Calibre style)
            series_meta = root.find('.//opf:meta[@name="calibre:series"]', ns)
            if series_meta is not None and 'content' in series_meta.attrib:
                metadata.series = series_meta.attrib['content']
            
            volume_meta = root.find('.//opf:meta[@name="calibre:series_index"]', ns)
            if volume_meta is not None and 'content' in volume_meta.attrib:
                metadata.volumenumber = volume_meta.attrib['content']
            
            # Extract source URL
            url_elem = root.find('.//dc:source', ns)
            if url_elem is not None and url_elem.text:
                metadata.url = url_elem.text.strip()
            
            log.info(f"Successfully read OPF metadata from: {opf_path}")
            
        except Exception as e:
            log.error(f"Error reading OPF file {opf_path}: {e}")
            metadata.mark_as_failed(f"OPF parsing error: {e}")
        
        return metadata
    
    def _fill_opf_template(self, template: str, metadata: BookMetadata) -> str:
        """Fill OPF template with metadata values."""
        filled = template
        
        # Basic metadata
        filled = self._replace_template_var(filled, "__AUTHOR__", metadata.get_safe_author())
        filled = self._replace_template_var(filled, "__TITLE__", metadata.get_safe_title())
        filled = self._replace_template_var(filled, "__SUMMARY__", metadata.summary)
        filled = self._replace_template_var(filled, "__SUBTITLE__", metadata.subtitle)
        filled = self._replace_template_var(filled, "__NARRATOR__", metadata.narrator)
        filled = self._replace_template_var(filled, "__PUBLISHER__", metadata.publisher)
        filled = self._replace_template_var(filled, "__LANGUAGE__", metadata.language)
        
        # Publication date - prefer datepublished over publishyear
        date_value = metadata.get_publication_date()
        filled = self._replace_template_var(filled, "__PUBLISHYEAR__", date_value)
        
        # Identifiers
        filled = self._replace_template_var(filled, "__ISBN__", metadata.isbn)
        filled = self._replace_template_var(filled, "__ASIN__", metadata.asin)
        
        # Series information
        filled = self._replace_template_var(filled, "__SERIES__", metadata.series)
        filled = self._replace_template_var(filled, "__VOLUMENUMBER__", metadata.volumenumber)
        
        # Source URL
        filled = self._replace_template_var(filled, "__SOURCE__", metadata.url)
        
        # Genres (convert to XML format)
        genres_xml = self._format_genres_for_opf(metadata.get_genres_list())
        filled = re.sub(r"__GENRES__", genres_xml, filled)
        
        return filled
    
    def _replace_template_var(self, template: str, placeholder: str, value: str) -> str:
        """Replace a template placeholder with sanitized XML value."""
        safe_value = sanitize_xml_text(value) if value else ""
        return re.sub(re.escape(placeholder), safe_value, template)
    
    def _format_genres_for_opf(self, genres: list) -> str:
        """
        Format genres list as XML elements for OPF.

        Applies genre normalization and mapping before formatting:
        - Lowercases all genres
        - Maps alternatives to canonical forms
        - Removes duplicates
        - Uses LLM for categorization if enabled and unmapped genres found
        """
        if not genres:
            return ""

        # Normalize and deduplicate genres (with LLM if enabled)
        normalized_genres = normalize_genres(genres, use_llm=self.use_llm)

        genre_xml = ""
        for genre in normalized_genres:
            genre_xml += f"<dc:subject>{sanitize_xml_text(genre)}</dc:subject>\n    "

        return genre_xml.rstrip()
    
    def _get_element_text(self, root: ET.Element, xpath: str, namespaces: dict) -> str:
        """Safely get text from XML element."""
        element = root.find(xpath, namespaces)
        return element.text if element is not None and element.text else ""
    
    def download_cover_image(self, metadata: BookMetadata) -> bool:
        """
        Download cover image from URL.
        
        Args:
            metadata: BookMetadata with cover_url
            
        Returns:
            True if successful, False otherwise
        """
        if not metadata.cover_url:
            log.info(f"No cover URL available for {metadata.input_folder}")
            return False
        
        if self.dry_run:
            print(f"[DRY-RUN] Would download cover from {metadata.cover_url} to {metadata.final_output}/cover.jpg")
            return True
        
        try:
            import requests
            
            print(f"Downloading cover image...")
            log.info(f"Downloading cover from: {metadata.cover_url}")
            
            response = requests.get(metadata.cover_url, timeout=15)
            if response.status_code == 200:
                cover_path = metadata.final_output / 'cover.jpg'
                with open(cover_path, 'wb') as f:
                    f.write(response.content)
                
                log.info(f"Successfully downloaded cover to: {cover_path}")
                print(f"Downloaded cover image to {cover_path}")
                return True
            else:
                log.warning(f"Failed to download cover: HTTP {response.status_code}")
                print(f"Failed to download cover image: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            log.error(f"Error downloading cover for {metadata.input_folder}: {e}")
            print(f"Error downloading cover image: {e}")
            return False


# Legacy functions for backward compatibility
def create_opf(metadata: BookMetadata, opf_template: Path, dry_run: bool = False) -> None:
    """Legacy function for backward compatibility."""
    processor = MetadataProcessor(dry_run=dry_run)
    processor.create_opf_file(metadata, opf_template)


def create_info(metadata: BookMetadata, dry_run: bool = False) -> None:
    """Legacy function for backward compatibility."""
    processor = MetadataProcessor(dry_run=dry_run)
    processor.create_info_file(metadata)


def read_opf_metadata(opf_path: Path) -> BookMetadata:
    """Legacy function for backward compatibility."""
    processor = MetadataProcessor()
    return processor.read_opf_metadata(opf_path)
