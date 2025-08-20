"""
Manual search handling.

This module handles manual URL input from users via clipboard monitoring
and browser automation for manual searches.
"""

import re
import time
import webbrowser
import logging as log
from pathlib import Path
from typing import Optional, Tuple

try:
    import pyperclip
    PYPERCLIP_AVAILABLE = True
except ImportError:
    PYPERCLIP_AVAILABLE = False
    log.warning("pyperclip not available - manual clipboard monitoring disabled")

from ..config import SCRAPER_REGISTRY
from ..models import BookMetadata
from ..utils import generate_search_term, detect_url_site


class ManualSearchHandler:
    """Handles manual search processes and clipboard monitoring."""
    
    def __init__(self):
        self.clipboard_available = PYPERCLIP_AVAILABLE
    
    def handle_manual_search(self, folder_path: Path, site_filter: str = 'all') -> Tuple[Optional[str], Optional[str]]:
        """
        Handle manual search process for a folder.
        
        Args:
            folder_path: Path to audiobook folder
            site_filter: Site to search ('all' or specific site key)
            
        Returns:
            Tuple of (site_key, url) or (None, None) if skipped
        """
        if not self.clipboard_available:
            print("Clipboard functionality not available. Please install pyperclip.")
            return None, None
        
        # Generate search term
        search_term = generate_search_term(folder_path)
        
        # Open browser with search
        self._open_search_in_browser(search_term, site_filter)
        
        # Monitor clipboard for URL
        return self._monitor_clipboard_for_url(folder_path, search_term)
    
    def _open_search_in_browser(self, search_term: str, site_filter: str):
        """Open search in web browser."""
        log.info(f"Search term: {search_term}")
        
        if site_filter == 'all':
            # Build combined search query for all sites
            domains = [f"site:{cfg['domain']}" for cfg in SCRAPER_REGISTRY.values()]
            query = "(" + " OR ".join(domains) + f") {search_term}"
            webbrowser.open(f"https://duckduckgo.com/?t=ffab&q={query}", new=2)
        elif site_filter in SCRAPER_REGISTRY:
            # Search specific site
            search_url = SCRAPER_REGISTRY[site_filter]["search_url"](search_term)
            webbrowser.open(search_url, new=2)
        else:
            log.warning(f"Unknown site filter: {site_filter}")
            # Fallback to general search
            webbrowser.open(f"https://duckduckgo.com/?t=ffab&q={search_term}", new=2)
    
    def _monitor_clipboard_for_url(self, folder_path: Path, search_term: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Monitor clipboard for valid URL or skip command.
        
        Args:
            folder_path: Path to folder being processed
            search_term: Search term being used
            
        Returns:
            Tuple of (site_key, url) or (None, None) if skipped
        """
        if not self.clipboard_available:
            return None, None
        
        # Clear clipboard if it already contains a valid URL
        clipboard_old = pyperclip.paste()
        log.debug(f"Initial clipboard content: {clipboard_old}")
        
        if self._is_valid_url_or_skip(clipboard_old):
            clipboard_old = '__clipboard_cleared__'
            pyperclip.copy(clipboard_old)
        
        # Wait for URL to be copied
        print(f"\nCopy the URL for \"{folder_path.name}\" | \"{search_term}\"")
        print("Copy 'skip' to skip the current book...           ", end='')
        
        while True:
            time.sleep(1)
            clipboard_current = pyperclip.paste()
            
            # Check if clipboard content changed
            if clipboard_current == clipboard_old:
                continue
            
            # Handle skip command
            if clipboard_current.lower().strip() == 'skip':
                log.info(f"Skipping: {folder_path.name}")
                print(f"\n\nSkipping: {folder_path.name}")
                break
            
            # Check for valid URL
            site_key = detect_url_site(clipboard_current)
            if site_key:
                url = clipboard_current.strip()
                print(f"\n\n{SCRAPER_REGISTRY[site_key]['domain']} URL: {url}")
                
                # Restore old clipboard content
                pyperclip.copy(clipboard_old)
                return site_key, url
        
        # Restore old clipboard content and return None (skipped)
        pyperclip.copy(clipboard_old)
        return None, None
    
    def _is_valid_url_or_skip(self, text: str) -> bool:
        """Check if text is a valid URL or skip command."""
        if not text:
            return False
        
        # Check for skip command
        if text.lower().strip() == 'skip':
            return True
        
        # Check for valid site URLs
        return any(
            re.search(cfg["url_pattern"], text) 
            for cfg in SCRAPER_REGISTRY.values()
        )
    
    def validate_manual_url(self, url: str) -> Optional[str]:
        """
        Validate a manually entered URL.
        
        Args:
            url: URL to validate
            
        Returns:
            Site key if valid, None otherwise
        """
        return detect_url_site(url)
    
    def prompt_for_manual_url(self, folder_name: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Prompt user for manual URL input via console.
        
        Args:
            folder_name: Name of folder being processed
            
        Returns:
            Tuple of (site_key, url) or (None, None) if skipped
        """
        print(f"\nEnter URL for '{folder_name}' (or 'skip' to skip):")
        
        while True:
            user_input = input("> ").strip()
            
            if user_input.lower() == 'skip':
                print(f"Skipping: {folder_name}")
                return None, None
            
            if not user_input:
                print("Please enter a URL or 'skip'")
                continue
            
            site_key = self.validate_manual_url(user_input)
            if site_key:
                print(f"Valid {SCRAPER_REGISTRY[site_key]['domain']} URL: {user_input}")
                return site_key, user_input
            else:
                print("Invalid URL. Please enter a valid audiobook site URL or 'skip'")
                print("Supported sites:", ", ".join(cfg['domain'] for cfg in SCRAPER_REGISTRY.values()))


# Legacy function for backward compatibility
def clipboard_queue(folder: Path, config, dry_run: bool = False):
    """
    Legacy function for backward compatibility.
    
    Args:
        folder: Folder path to process
        config: Configuration object to update
        dry_run: Whether this is a dry run
        
    Returns:
        Updated configuration object
    """
    from ..utils import encode_for_config
    
    handler = ManualSearchHandler()
    site_key, url = handler.handle_manual_search(folder)
    
    if site_key and url:
        b64_folder = encode_for_config(str(folder.resolve()))
        b64_url = encode_for_config(url)
        config['urls'][b64_folder] = b64_url
    
    return config
