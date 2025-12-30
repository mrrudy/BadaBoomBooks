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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from ..config import get_chrome_options, initialize_chrome_driver
from ..config import SCRAPER_REGISTRY, DEFAULT_SEARCH_WAIT_TIMEOUT
from ..models import SearchCandidate
from ..utils import wait_with_backoff


class AutoSearchEngine:
    """Handles automated search across multiple audiobook sites."""

    def __init__(self, debug_enabled: bool = False, enable_ai_selection: bool = False, yolo: bool = False, task_id: Optional[str] = None, in_worker_context: bool = False):
        self.debug_enabled = debug_enabled
        self.debug_dir = None
        self.enable_ai_selection = enable_ai_selection
        self.yolo = yolo
        self.task_id = task_id  # Optional task ID for queue tracking
        self.in_worker_context = in_worker_context  # True when running in background worker thread

        if debug_enabled:
            from ..config import root_path
            self.debug_dir = root_path / 'debug_pages'
            self.debug_dir.mkdir(exist_ok=True)

        # Initialize candidate selector with AI if enabled
        from .candidate_selection import CandidateSelector
        self.candidate_selector = CandidateSelector(enable_ai_selection)
    
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
        return self.search_and_select_with_context(search_term, site_keys, None, 
                                                  search_limit, download_limit, delay)
    
    def search_and_select_with_context(self, search_term: str, site_keys: List[str],
                                      book_info: dict = None, search_limit: int = 5,
                                      download_limit: int = 3, delay: float = 2.0,
                                      search_alternatives: List[dict] = None) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Search for candidates across multiple sites and let user select with book context.

        Args:
            search_term: Primary term to search for
            site_keys: List of site keys to search
            book_info: Current book information for context display
            search_limit: Maximum results per site to fetch
            download_limit: Maximum pages per site to download
            delay: Delay between requests
            search_alternatives: Optional list of alternative search terms from different sources
                                (ID3 tags vs folder name). Each dict contains:
                                {'source': 'id3'|'folder', 'term': 'search term', 'priority': int, 'details': str}

        Returns:
            Tuple of (site_key, url, html) or (None, None, None) if skipped
        """
        candidates = []
        driver = None

        try:
            # Initialize Chrome driver with smart profile selection
            driver, profile_mode = initialize_chrome_driver()

            # Inform user of profile mode
            if profile_mode == 'real':
                log.info("🌍 Using real Chrome profile (DuckDuckGo preferences preserved)")
            elif profile_mode == 'copied':
                log.info("🌍 Using copied Chrome profile (DuckDuckGo preferences preserved)")
            else:
                log.info("⚠️  Using temporary Chrome profile (could not access profile)")

            # Execute stealth JavaScript to bypass WebDriver detection
            driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });

                    // Override plugins to appear more realistic
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });

                    // Override languages
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-US', 'en']
                    });

                    // Chrome runtime should not be exposed
                    window.chrome = {
                        runtime: {}
                    };
                '''
            })

            # If search_alternatives provided, search with ALL alternatives
            # This creates parallel search strategies: (ID3 data) OR (folder name)
            search_terms_to_try = []
            if search_alternatives:
                # Use all alternatives for comprehensive search
                for alt in search_alternatives:
                    search_terms_to_try.append({
                        'term': alt['term'],
                        'source': alt['source'],
                        'details': alt.get('details', '')
                    })
                log.info(f"Using {len(search_terms_to_try)} search alternatives from multiple sources")
            else:
                # Single search term (legacy behavior or OPF-based)
                search_terms_to_try.append({
                    'term': search_term,
                    'source': 'single',
                    'details': ''
                })

            # Search each site with each alternative
            for site_key in site_keys:
                for search_info in search_terms_to_try:
                    site_candidates = self._search_single_site(
                        driver, site_key, search_info['term'], search_limit, download_limit, delay
                    )
                    # Tag candidates with their source
                    for candidate in site_candidates:
                        candidate.search_source = search_info['source']
                        candidate.search_term_used = search_info['term']
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
        
        # Let user select from candidates with book context
        return self._user_select_candidate(candidates, search_term, book_info)
    
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

            # Wait for search results to load with explicit wait condition
            try:
                wait = WebDriverWait(driver, DEFAULT_SEARCH_WAIT_TIMEOUT)
                # Wait for article elements with data-testid="result" to be present
                wait.until(EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'article[data-testid="result"]')
                ))
                # Additional short delay for any lazy-loaded content
                time.sleep(0.5)
                if self.debug_enabled:
                    log.debug(f"Search results loaded successfully for: {search_term}")
            except TimeoutException:
                # Fallback to old behavior if new selector fails
                log.warning(f"Timeout waiting for search results, using fallback delay for: {search_term}")
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

            # Enhanced debug logging for first result
            if self.debug_enabled and elems:
                first_elem = elems[0]
                first_title = first_elem.text or first_elem.get_attribute('aria-label') or 'No title'
                first_href = first_elem.get_attribute('href')
                log.debug(f"First search result: '{first_title}' -> {first_href}")

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
                    log.debug(f"Added result #{i+1}: {title} -> {href}")
            
            # Debug: Save search results page
            if self.debug_enabled:
                self._save_debug_page(driver, f"search_{site_key}_{search_term}")
                print(f"  Debug: Found {len(results)} valid results for {site_key}")

            # Validate results
            if len(results) == 0:
                log.warning(f"No search results found for '{search_term}' on {site_key}. "
                          f"Page may not have loaded completely.")

        except Exception as e:
            log.error(f"Error extracting search results for {site_key}: {e}")

        return results
    
    def _filter_results_by_pattern(self, results: List[dict], url_pattern: str, site_key: str) -> List[dict]:
        """Filter results by URL pattern matching."""
        filtered = []
        config = SCRAPER_REGISTRY.get(site_key, {})
        expected_domain = config.get('domain', '')

        for result in results:
            # Validate domain if available
            if expected_domain and expected_domain not in result["href"]:
                log.debug(f"Skipping result - domain mismatch. Expected '{expected_domain}', got: {result['href']}")
                continue

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
    
    def _generate_search_url(self, search_term: str) -> str:
        """
        Generate DuckDuckGo search URL for manual searching.
        Uses same logic as ManualSearchHandler._open_search_in_browser()
        to ensure consistency with manual search behavior.

        URL-encodes the query to make it fully clickable in PowerShell terminals.
        """
        from ..config import SCRAPER_REGISTRY

        # Build combined search query for all sites (same as manual search)
        domains = [f"site:{cfg['domain']}" for cfg in SCRAPER_REGISTRY.values()]
        query = "(" + " OR ".join(domains) + f") {search_term}"

        # URL-encode the query for clickable links in terminals
        return f"https://duckduckgo.com/?q={requests.utils.quote(query)}"

    def _user_select_candidate(self, candidates: List[SearchCandidate], search_term: str, book_info: dict = None) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Let user select from candidate pages with LLM scoring displayed upfront.

        Shows candidates sorted by weighted score (if LLM available), with scores
        visible and smart default selection. User can press Enter to accept default.
        """
        from ..utils import safe_encode_text

        # Step 1: Try to score candidates with LLM (don't auto-select yet)
        scored_candidates = []
        recommended_candidate = None

        if self.enable_ai_selection:
            recommended_candidate = self.candidate_selector.select_best_candidate(
                candidates, search_term, book_info
            )
            # Get scored candidates (already sorted by weighted score)
            scored_candidates = self.candidate_selector.last_scored_candidates or []

        # Step 2: Display book context
        self._display_book_context(search_term, book_info)

        # Step 3: Determine display order and default selection
        default_choice = None

        if scored_candidates:
            # Use scored order (already sorted by final_score descending)
            display_candidates = scored_candidates  # List[(candidate, llm_score, final_score)]

            # Determine default based on best score
            best_candidate, best_llm_score, best_final_score = scored_candidates[0]
            ACCEPTANCE_THRESHOLD = 0.5

            if best_llm_score >= ACCEPTANCE_THRESHOLD:
                default_choice = 1  # Best candidate
            else:
                default_choice = 0  # Skip - no high-confidence match
                print(safe_encode_text("\n⚠️  No high-confidence matches found (all scores < 0.5)\n"))
        else:
            # No LLM scoring available - use original order, no default
            display_candidates = [(c, None, None) for c in candidates]
            default_choice = None

        # Step 4: Handle YOLO mode (auto-accept default without prompt)
        if self.yolo:
            if default_choice == 0:
                print("🚀 YOLO mode: Auto-skipping (no high-confidence match)")
                log.debug(f"YOLO mode: Auto-skipped - all scores < 0.5")
                return None, None, None
            elif default_choice == 1:
                # Auto-select best scored candidate
                selected_candidate = display_candidates[0][0]  # Get candidate from tuple
                print(f"🚀 YOLO mode: Auto-selecting [{selected_candidate.site_key}] {selected_candidate.title}")
                if scored_candidates:
                    _, llm_score, final_score = display_candidates[0]
                    print(f"   Score: {llm_score:.2f} (weighted: {final_score:.2f})")
                log.debug(f"YOLO mode: Auto-selected best candidate: {selected_candidate.url}")
                return selected_candidate.site_key, selected_candidate.url, selected_candidate.html
            else:
                # No default, fall back to first candidate
                selected_candidate = candidates[0]
                print(f"🚀 YOLO mode: Auto-selecting first candidate [{selected_candidate.site_key}]")
                log.debug(f"YOLO mode: Auto-selected first candidate (no LLM): {selected_candidate.url}")
                return selected_candidate.site_key, selected_candidate.url, selected_candidate.html

        # Step 5: Display candidates with scores
        print("\nCandidate pages:\n")

        for i, (candidate, llm_score, final_score) in enumerate(display_candidates, 1):
            # Determine if this is the default
            is_default = (default_choice == i)
            default_marker = safe_encode_text(" 🏆 ⭐ DEFAULT") if is_default else ""

            # Format score display
            score_str = ""
            if llm_score is not None:
                score_str = f" {llm_score:.2f}"
                if final_score and abs(llm_score - final_score) > 0.001:
                    # Weight was applied
                    score_str += f" (weighted: {final_score:.2f})"

            # Print candidate with score
            print(safe_encode_text(f"[{i}]{default_marker} [{candidate.site_key}]{score_str}"))
            print(safe_encode_text(f"    {candidate.title}"))
            print(f"    {candidate.url}")
            if candidate.snippet:
                snippet_preview = candidate.snippet[:100]
                print(safe_encode_text(f"    {snippet_preview}..."))
            print()

        # Step 6: Display skip option with search URL if needed
        skip_default = safe_encode_text(" ⭐ DEFAULT") if default_choice == 0 else ""
        print(safe_encode_text(f"[0] Skip this book{skip_default}"))

        # Show manual search URL if all scores failed threshold
        if scored_candidates and default_choice == 0:
            search_url = self._generate_search_url(search_term)
            print(safe_encode_text(f"    🔍 Search manually: {search_url}"))

        print("\nOr enter a custom URL from a supported site")

        # Step 7: Get user input with smart default
        if default_choice is not None:
            prompt = f"Select [0-{len(candidates)}] (default: {default_choice}): "
        else:
            prompt = f"Select [0-{len(candidates)}]: "

        # Mark task as waiting for user input if task_id is available
        if self.task_id:
            self._mark_task_waiting_for_user(
                input_type='manual_selection',
                prompt=prompt,
                display_candidates=display_candidates,  # Use display order, not original
                book_info=book_info,
                search_term=search_term,
                default_choice=default_choice
            )

            # If running in worker thread context, return early after marking task
            # The task will be picked up later by main thread or web interface
            if self.in_worker_context:
                log.info("Worker context: Task marked as waiting_for_user, returning early")
                return None, None, None

        while True:
            user_input = input(prompt).strip()

            # Handle empty input (default selection)
            if user_input == "" and default_choice is not None:
                choice = default_choice
            else:
                # Try to parse as number
                try:
                    choice = int(user_input)
                except ValueError:
                    # Not a number, try to parse as URL
                    result = self._process_custom_url(user_input)
                    if result:
                        return result
                    # If _process_custom_url returns None, it already printed error message
                    continue

            # Process choice
            if choice == 0:
                log.debug(f"User skipped selection for search term: {search_term}")
                return None, None, None

            if 1 <= choice <= len(candidates):
                # Get the actual candidate (handle both scored and unscored display)
                selected_candidate = display_candidates[choice - 1][0]

                # Debug: Save chosen page
                if self.debug_enabled:
                    self._save_debug_content(selected_candidate.html,
                                           f"chosen_{selected_candidate.site_key}_{selected_candidate.title}")
                    print("Debug: Saved chosen page to debug folder")

                log.debug(f"User selected candidate: {selected_candidate.url}")
                return selected_candidate.site_key, selected_candidate.url, selected_candidate.html
            else:
                print(f"Invalid number. Please enter 0-{len(candidates)}")
                continue

    def _process_custom_url(self, url_input: str) -> Optional[Tuple[str, str, str]]:
        """
        Process a custom URL provided by the user.

        Args:
            url_input: URL string (with or without http/https prefix)

        Returns:
            Tuple of (site_key, url, html) if valid, None otherwise
        """
        from ..utils import detect_url_site

        # Normalize URL - add https:// if missing
        normalized_url = url_input
        if not url_input.startswith(('http://', 'https://')):
            normalized_url = 'https://' + url_input

        # Validate URL against supported sites
        site_key = detect_url_site(normalized_url)

        if not site_key:
            print(f"\n❌ URL not recognized as a supported site.")
            print(f"Supported sites:")
            for key, config in SCRAPER_REGISTRY.items():
                print(f"  - {config['domain']} (pattern: {config['url_pattern']})")
            print()
            return None

        # Download the page HTML
        print(f"\n📥 Downloading page from {SCRAPER_REGISTRY[site_key]['domain']}...")
        try:
            response = requests.get(normalized_url, timeout=15)
            response.raise_for_status()
            html = response.text

            # Debug: Save custom URL page
            if self.debug_enabled:
                self._save_debug_content(html, f"custom_{site_key}")
                print(f"Debug: Saved custom URL page to debug folder")

            log.debug(f"User provided custom URL: {normalized_url}")
            print(f"✅ Successfully loaded page from {SCRAPER_REGISTRY[site_key]['domain']}")

            return site_key, normalized_url, html

        except requests.RequestException as e:
            print(f"\n❌ Failed to download page: {e}")
            print("Please check the URL and try again.\n")
            log.error(f"Failed to download custom URL {normalized_url}: {e}")
            return None

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
    
    def _display_book_context(self, search_term: str, book_info: dict = None):
        """Display context about the book being processed."""
        from ..utils import safe_encode_text
        print("\n" + "="*80)
        print(safe_encode_text("📚 SELECTING METADATA FOR:"))
        print("="*80)

        if book_info:
            # Display available metadata
            if book_info.get('title'):
                print(safe_encode_text(f"📖 Title: {book_info['title']}"))
            if book_info.get('author'):
                print(safe_encode_text(f"✍️  Author: {book_info['author']}"))
            if book_info.get('series'):
                series_info = book_info['series']
                if book_info.get('volume'):
                    series_info += f" (Volume {book_info['volume']})"
                print(safe_encode_text(f"📚 Series: {series_info}"))
            if book_info.get('narrator'):
                print(safe_encode_text(f"🎤 Narrator: {book_info['narrator']}"))
            if book_info.get('publisher'):
                print(safe_encode_text(f"🏢 Publisher: {book_info['publisher']}"))
            if book_info.get('year'):
                print(safe_encode_text(f"📅 Year: {book_info['year']}"))
            if book_info.get('language'):
                print(safe_encode_text(f"🌍 Language: {book_info['language']}"))
            if book_info.get('source'):
                print(safe_encode_text(f"📂 Source: {book_info['source']}"))
            
            # Show folder name if different from title
            if book_info.get('folder_name') and book_info.get('folder_name') != book_info.get('title'):
                print(safe_encode_text(f"📁 Folder: {book_info['folder_name']}"))
        else:
            # Fallback to search term and folder name
            print(safe_encode_text(f"🔍 Search term: {search_term}"))

        print("="*80)

    def _mark_task_waiting_for_user(
        self,
        input_type: str,
        prompt: str,
        display_candidates: List[tuple],
        book_info: dict = None,
        search_term: str = None,
        default_choice: int = None
    ):
        """
        Mark the task as waiting for user input in the queue database.

        Args:
            input_type: Type of input ('manual_selection' or 'llm_confirmation')
            prompt: The prompt text to show user
            display_candidates: List of (candidate, llm_score, final_score) tuples in display order
            book_info: Book context information
            search_term: The search term used
            default_choice: The default selection number (or None)
        """
        if not self.task_id:
            return  # No task tracking available

        try:
            from ..queue_manager import QueueManager

            queue_manager = QueueManager()

            # Build options list for database - use display order with scores
            options = []
            for i, (candidate, llm_score, final_score) in enumerate(display_candidates, 1):
                option_dict = {
                    'number': i,
                    'site_key': candidate.site_key,
                    'title': candidate.title,
                    'url': candidate.url,
                    'author': getattr(candidate, 'author', None),
                    'series': getattr(candidate, 'series', None),
                    'snippet': candidate.snippet[:100] if candidate.snippet else None,
                    'is_default': (i == default_choice)
                }

                # Add scores if available (they're already matched to candidates)
                if llm_score is not None:
                    option_dict['llm_score'] = llm_score
                if final_score is not None:
                    option_dict['final_score'] = final_score

                options.append(option_dict)

            # Add skip option
            options.append({
                'number': 0,
                'action': 'skip',
                'label': 'Skip this book',
                'is_default': (0 == default_choice)
            })

            # Build context dictionary
            context = {
                'search_term': search_term,
                'book_info': book_info or {},
                'has_llm_scores': bool(display_candidates and display_candidates[0][1] is not None),
                'folder_path': book_info.get('folder_name') if book_info else None,
                'default_choice': default_choice
            }

            # Mark task as waiting for user
            queue_manager.set_task_waiting_for_user(
                task_id=self.task_id,
                input_type=input_type,
                prompt=prompt,
                options=options,
                context=context
            )

            log.debug(f"Marked task {self.task_id[:8]} as waiting for user input: {input_type}")

        except Exception as e:
            # Don't fail the whole operation if tracking fails
            log.warning(f"Failed to mark task as waiting for user: {e}")
            log.debug(f"Task tracking error details:", exc_info=True)
