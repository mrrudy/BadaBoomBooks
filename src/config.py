"""
Configuration management and application constants.

This module contains all configuration settings, constants, and paths
used throughout the BadaBoomBooks application.
"""

import os
import sys
from pathlib import Path
import logging as log

__version__ = 0.60

# === PATHS ===
# Handle both modular and direct execution
if 'src' in str(Path(__file__).resolve()):
    # Running from src directory
    root_path = Path(__file__).resolve().parent.parent
else:
    # Running from main directory
    root_path = Path(__file__).resolve().parent

# If still in src, go up one more level
if root_path.name == 'src':
    root_path = root_path.parent

config_file = root_path / 'queue.ini'
debug_file = root_path / 'debug.log'
opf_template = root_path / 'template.opf'
default_output = '_BadaBoomBooks_'  # In the same directory as the input folder

# === AUDIO FILE EXTENSIONS ===
AUDIO_EXTENSIONS = {'.mp3', '.m4a', '.m4b', '.wma', '.flac', '.ogg'}

# === SCRAPER REGISTRY ===
# Central registry of all supported scraping sites and their configurations
SCRAPER_REGISTRY = {
    "audible": {
        "domain": "audible.com",
        "url_pattern": r"^http.+audible.+/pd/[\w-]+Audiobook/\w{10}",
        "search_url": lambda search_term: f"https://duckduckgo.com/?t=ffab&q=site:audible.com {search_term}",
        "scrape_func_name": "api_audible",
        "http_request_func_name": "http_request_audible_api",
        "preprocess_func_name": "preprocess_audible_url"
    },
    "goodreads": {
        "domain": "goodreads.com", 
        "url_pattern": r"^http.+goodreads.+book/show/\d+",
        "search_url": lambda search_term: f"https://duckduckgo.com/?t=ffab&q=site:goodreads.com {search_term}",
        "scrape_func_name": "scrape_goodreads",
        "http_request_func_name": "http_request_generic",
        "preprocess_func_name": None
    },
    "lubimyczytac": {
        "domain": "lubimyczytac.pl",
        "url_pattern": r"^https?://lubimyczytac\.pl/(ksiazka|audiobook)/\d+/.+",
        "search_url": lambda search_term: f"https://duckduckgo.com/?t=ffab&q=site:lubimyczytac.pl {search_term}",
        "scrape_func_name": "scrape_lubimyczytac",
        "http_request_func_name": "http_request_generic", 
        "preprocess_func_name": None
    }
}

# === LOGGING CONFIGURATION ===
def setup_logging(debug_enabled: bool = False):
    """Setup logging configuration based on debug flag."""
    if debug_enabled:
        # Create a more focused logging configuration that doesn't flood with huge responses
        class LimitedSizeFilter(log.Filter):
            def filter(self, record):
                # Limit log message size to prevent huge debug logs
                msg_str = str(record.msg)
                
                # Completely skip logging huge HTML responses
                if 'Remote response:' in msg_str or len(msg_str) > 5000:
                    return False
                
                # Limit other large messages
                if len(msg_str) > 500:
                    record.msg = msg_str[:500] + "... [TRUNCATED]"
                
                return True
        
        # Setup logger with size filter
        logger = log.getLogger()
        logger.setLevel(log.DEBUG)
        
        # File handler with limited size
        file_handler = log.FileHandler(str(debug_file), mode='w', encoding='utf-8')
        file_handler.setLevel(log.DEBUG)
        
        # Add the filter to prevent huge logs
        file_handler.addFilter(LimitedSizeFilter())
        
        # Formatter
        formatter = log.Formatter(
            "Line: {lineno} | Level: {levelname} | Time: {asctime} | Info: {message}",
            style='{'
        )
        file_handler.setFormatter(formatter)
        
        # Add handler
        logger.addHandler(file_handler)
    else:
        log.disable(log.CRITICAL)

# === BROWSER CONFIGURATION ===
def get_chrome_options():
    """Get Chrome options for Selenium WebDriver."""
    from selenium.webdriver.chrome.options import Options
    
    chrome_options = Options()
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--enable-unsafe-swiftshader")
    
    # Add new flags to prevent GPU initialization
    chrome_options.add_argument("--disable-3d-apis")
    chrome_options.add_argument("--disable-accelerated-2d-canvas")
    chrome_options.add_argument("--disable-gl-drawing-for-tests")
    
    # Disable unnecessary services
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--disable-gpu-compositing")
    chrome_options.add_argument("--disable-cloud-import")
    chrome_options.add_argument("--disable-component-update")
    chrome_options.add_argument("--disable-background-networking")
    chrome_options.add_argument("--disable-client-side-phishing-detection")
    
    # Set log level to suppress warnings
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    # Add user agent to avoid bot detection
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
    
    return chrome_options

# === ENVIRONMENT CONFIGURATION ===
def setup_environment():
    """Setup environment variables and paths."""
    os.environ['GCM_ENCRYPTION_DISABLED'] = '1'  # Disable problematic GCM encryption

# === DEFAULT VALUES ===
DEFAULT_SEARCH_LIMIT = 5
DEFAULT_DOWNLOAD_LIMIT = 3
DEFAULT_SEARCH_DELAY = 2.0
