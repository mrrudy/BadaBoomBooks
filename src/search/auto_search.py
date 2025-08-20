"""
Automated search functionality.

This module handles automated searching across multiple sites
using Selenium WebDriver and DuckDuckGo.
"""

import re
import time
import requests
import logging as log
from pathlib import Path
from typing import List, Optional, Tuple
from selenium import webdriver
from selenium.webdriver.common.by import By

from ..config import get_chrome_options
from ..config import SCRAPER_REGISTRY
from ..models import SearchCandidate
from ..utils import wait_with_backoff


class AutoSearchEngine:
    """Handles automated search across multiple audiobook sites."""
    
    def __init__(self, debug_enabled: bool = False):
        self.debug_enabled = debug_enabled
        self.debug_dir = None
        
        if debug_enabled:
            from ..config import root_path
            self.debug_dir = root_path / 'debug_pages'
            self.debug_dir.mkdir(exist_ok=True)
    
    def search_and_select(self, search_term: str, site_keys: List[str], 
                         search_limit: int = 5, download_limit: int = 3, 
                         delay: float = 2.0) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Search for candidates across multiple sites and let user select.
        
        Args:
            search_term: Term to search for
            site_keys: List of site keys to search
            search_limit: Maximum results per site to fetch
            download_limit: Maximum pages per site to download
            delay: Delay between requests
            
        Returns:
            Tuple of (site_key, url, html) or (None, None, None) if skipped
        """
        candidates = []
        driver = None
        
        try:
            # Initialize Chrome driver
            chrome_options = get_chrome_options()
            driver = webdriver.Chrome(options=chrome_options)
            
            # Search each site
            for site_key in site_keys:
                site_candidates = self._search_single_site(
                    driver, site_key, search_term, search_limit, download_limit, delay
                )
                candidates.extend(site_candidates)
            
        except Exception as e:
            log.error(f"Error during automated search: {e}")
            print(f"Search error: {e}")
            return None, None, None
        finally:
            if driver:
                driver.quit()
        
        if not candidates:
            print("No candidate pages found.")
            log.debug(f"No candidate pages found for search term: {search_term}")
            return None, None, None
        
        # Let user select from candidates
        return self._user_select_candidate(candidates, search_term)
    
    def _search_single_site(self, driver: webdriver.Chrome, site_key: str, 
                           search_term: str, search_limit: int, download_limit: int, 
                           delay: float) -> List[SearchCandidate]:
        """Search a single site for candidates."""
        try:
            config = SCRAPER_REGISTRY[site_key]
            print(f"\nSearching {config['domain']} for: {search_term}")
            log.debug(f"Searching {config['domain']} for: {search_term}")
            
            # Perform DuckDuckGo search
            query = f"site:{config['domain']} {search_term}"
            ddg_url = f"https://duckduckgo.com/?q={requests.utils.quote(query)}"
            
            driver.get(ddg_url)
            time.sleep(delay)
            
            # Extract search results
            results = self._extract_search_results(driver, site_key, search_term, search_limit)
            
            # Filter by URL pattern
            filtered_results = self._filter_results_by_pattern(results, config["url_pattern"], site_key)
            
            if not filtered_results:
                print(f"  No matching results found for {site_key}")
                return []
            
            # Download pages
            candidates = self._download_candidate_pages(
                filtered_results, site_key, download_limit, delay
            )
            
            return candidates
            
        except Exception as e:
            log.error(f"Error searching {site_key}: {e}")
            print(f"  Error searching {site_key}: {e}")
            return []
    
    def _extract_search_results(self, driver: webdriver.Chrome, site_key: str, 
                               search_term: str, search_limit: int) -> List[dict]:
        """Extract search results from DuckDuckGo page."""
        results = []
        
        try:
            # Try multiple selectors for DuckDuckGo results
            elems = []
            snippets = []
            
            # Current DuckDuckGo format (2024/2025)
            elems = driver.find_elements(By.CSS_SELECTOR, 'article[data-testid="result"] h2 a')
            snippets = driver.find_elements(By.CSS_SELECTOR, 'article[data-testid="result"] [data-result="snippet"]')
            
            # Fallback selectors
            if not elems:
                elems = driver.find_elements(By.CSS_SELECTOR, '.result__a')
                snippets = driver.find_elements(By.CSS_SELECTOR, '.result__snippet')
            
            if not elems:
                elems = driver.find_elements(By.CSS_SELECTOR, '[data-testid="result"] a[href]')
                snippets = driver.find_elements(By.CSS_SELECTOR, '[data-testid="result"] span')
            
            if not elems:
                elems = driver.find_elements(By.CSS_SELECTOR, 'ol.react-results--main a[href]')
                snippets = driver.find_elements(By.CSS_SELECTOR, 'ol.react-results--main .result__snippet')
            
            log.debug(f"Found {len(elems)} result elements for {site_key}")
            
            # Extract result data
            for i, elem in enumerate(elems[:search_limit]):
                href = elem.get_attribute('href')
                title = elem.text or elem.get_attribute('aria-label') or 'No title'
                snippet = snippets[i].text if i < len(snippets) else ''
                
                # Skip invalid URLs
                if href and not href.startswith('javascript:') and 'http' in href:
                    results.append({
                        'title': title,
                        'href': href, 
                        'body': snippet
                    })
                    log.debug(f"Added result: {title} -> {href}")
            
            # Debug: Save search results page
            if self.debug_enabled:
                self._save_debug_page(driver, f"search_{site_key}_{search_term}")
                print(f"  Debug: Found {len(results)} valid results for {site_key}")
            
        except Exception as e:
            log.error(f"Error extracting search results for {site_key}: {e}")
        
        return results
    
    def _filter_results_by_pattern(self, results: List[dict], url_pattern: str, site_key: str) -> List[dict]:
        """Filter results by URL pattern matching."""
        filtered = []
        
        for result in results:
            if re.search(url_pattern, result["href"]):
                filtered.append(result)
                log.debug(f"Matched URL pattern for {site_key}: {result['href']}")
                
                # Stop when we have enough matches
                if len(filtered) >= 10:  # Reasonable limit
                    break
        
        if not filtered and results:
            log.debug(f"No matches for {site_key}. Pattern: {url_pattern}")
            log.debug(f"Sample URLs that didn't match: {[r['href'][:100] for r in results[:3]]}")
        
        return filtered
    
    def _download_candidate_pages(self, results: List[dict], site_key: str, 
                                 download_limit: int, delay: float) -> List[SearchCandidate]:
        """Download candidate pages from search results."""
        candidates = []
        
        for i, result in enumerate(results[:download_limit]):
            try:
                print(f"  [{len(candidates)+1}] {result['title']}")
                print(f"      {result['href']}")
                print(f"      {result['body'][:100]}...")
                print(f"  Downloading: {result['href']}")
                
                # Download page
                response = requests.get(result['href'], timeout=15)
                
                candidate = SearchCandidate(
                    site_key=site_key,
                    url=result['href'],
                    title=result['title'],
                    snippet=result['body'],
                    html=response.text
                )
                candidates.append(candidate)
                
                # Debug: Save downloaded page
                if self.debug_enabled:
                    self._save_debug_content(response.text, f"page_{site_key}_{result['title']}")
                    print(f"    Debug: Saved page to debug folder")
                
                time.sleep(delay)
                
            except Exception as e:
                print(f"    Failed to download {result['href']}: {e}")
                log.debug(f"Failed to download {result['href']}: {e}")
        
        return candidates
    
    def _user_select_candidate(self, candidates: List[SearchCandidate], search_term: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Let user select from candidate pages."""
        print("\nCandidate pages:")
        for i, candidate in enumerate(candidates, 1):
            print(f"[{i}] {candidate}")
            print()
        print("[0] Skip this book")
        
        # Future: AI selection could be implemented here
        # ai_choice = ai_select_best_candidate(candidates, search_term)
        # if ai_choice is not None:
        #     return candidates[ai_choice].site_key, candidates[ai_choice].url, candidates[ai_choice].html
        
        while True:
            try:
                choice = int(input(f"Select the best candidate [1-{len(candidates)}] or 0 to skip: "))
                if choice == 0:
                    log.debug(f"User skipped selection for search term: {search_term}")
                    return None, None, None
                if 1 <= choice <= len(candidates):
                    selected = candidates[choice-1]
                    
                    # Debug: Save chosen page
                    if self.debug_enabled:
                        self._save_debug_content(selected.html, f"chosen_{selected.site_key}_{selected.title}")
                        print(f"Debug: Saved chosen page to debug folder")
                    
                    log.debug(f"User selected candidate: {selected.url}")
                    return selected.site_key, selected.url, selected.html
            except (ValueError, IndexError):
                pass
            print("Invalid input. Try again.")
    
    def _save_debug_page(self, driver: webdriver.Chrome, filename_prefix: str):
        """Save current page HTML for debugging."""
        if not self.debug_dir:
            return
        
        try:
            safe_filename = re.sub(r'[^a-zA-Z0-9]', '_', filename_prefix)[:50]
            debug_path = self.debug_dir / f"{safe_filename}.html"
            
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            
            log.debug(f"Saved debug page: {debug_path}")
            
        except Exception as e:
            log.warning(f"Could not save debug page: {e}")
    
    def _save_debug_content(self, content: str, filename_prefix: str):
        """Save HTML content for debugging."""
        if not self.debug_dir:
            return
        
        try:
            safe_filename = re.sub(r'[^a-zA-Z0-9]', '_', filename_prefix)[:50]
            debug_path = self.debug_dir / f"{safe_filename}.html"
            
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            log.debug(f"Saved debug content: {debug_path}")
            
        except Exception as e:
            log.warning(f"Could not save debug content: {e}")
