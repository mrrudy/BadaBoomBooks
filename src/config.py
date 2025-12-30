"""
Configuration management and application constants.

This module contains all configuration settings, constants, and paths
used throughout the BadaBoomBooks application.
"""

import os
import sys
from pathlib import Path
import logging as log

# === ENCODING CONFIGURATION ===
# Reconfigure stdout/stderr to handle Unicode properly on Windows
# This prevents UnicodeEncodeError when printing non-ASCII characters
if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'replace')
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'replace')

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

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    env_file = root_path / '.env'
    if env_file.exists():
        load_dotenv(env_file)
        log.debug(f"Loaded environment variables from {env_file}")
except ImportError:
    log.debug("python-dotenv not available, skipping .env file loading")
except Exception as e:
    log.debug(f"Error loading .env file: {e}")

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
        "preprocess_func_name": "preprocess_audible_url",
        "weight": 2.0  # Weight for tiebreaking in LLM scoring
    },
    "goodreads": {
        "domain": "goodreads.com",
        "url_pattern": r"^http.+goodreads.+book/show/\d+",
        "search_url": lambda search_term: f"https://duckduckgo.com/?t=ffab&q=site:goodreads.com {search_term}",
        "scrape_func_name": "scrape_goodreads",
        "http_request_func_name": "http_request_generic",
        "preprocess_func_name": None,
        "weight": 1.5  # Weight for tiebreaking in LLM scoring
    },
    "lubimyczytac": {
        "domain": "lubimyczytac.pl",
        "url_pattern": r"^https?://lubimyczytac\.pl/(ksiazka|audiobook)/\d+/.+",
        "search_url": lambda search_term: f"https://duckduckgo.com/?t=ffab&q=site:lubimyczytac.pl {search_term}",
        "scrape_func_name": "scrape_lubimyczytac",
        "http_request_func_name": "http_request_generic",
        "preprocess_func_name": None,
        "weight": 3.0  # Weight for tiebreaking in LLM scoring (highest - most favored)
    }
}

# === LLM CONFIGURATION ===
def load_llm_config():
    """Load LLM configuration from environment variables."""
    import os
    return {
        'api_key': os.getenv('LLM_API_KEY'),
        'model': os.getenv('LLM_MODEL', 'gpt-3.5-turbo'),
        'base_url': os.getenv('OPENAI_BASE_URL'),  # For local models (LM Studio, Ollama)
        'max_tokens': int(os.getenv('LLM_MAX_TOKENS', '4096')),  # Maximum tokens for LLM responses
        'enabled': bool(os.getenv('LLM_API_KEY'))  # Auto-enable if API key present
    }

LLM_CONFIG = load_llm_config()

# === LLM SCORING THRESHOLDS ===
# All threshold values for LLM-based candidate selection
# These control automated vs manual decision-making
LLM_SCORING_THRESHOLDS = {
    # === Primary Acceptance Thresholds ===
    # Applied to RAW LLM scores (before weight application)
    'llm_acceptance_threshold': 0.5,          # Minimum LLM score to accept candidate (manual mode)
                                               # Below this: show "skip" as default choice
                                               # Above this: show candidate as default choice

    # Applied to FINAL WEIGHTED scores (after weight application)
    'yolo_auto_accept_threshold': 0.95,       # Minimum final score for YOLO auto-accept
                                               # In YOLO mode: only auto-select if final_score >= 0.95
                                               # Otherwise: auto-skip (too risky for automated processing)

    # === Weight Application Thresholds ===
    'weight_min_score_threshold': 0.65,       # Minimum LLM score to apply scraper weights
                                               # Prevents boosting low-quality matches
                                               # Below this: final_score = llm_score (no boost)

    'weight_similarity_bracket': 0.1,         # Quality bracket for weight tiebreaker (±0.1)
                                               # Only apply weights to candidates within this bracket
                                               # of best score (avoids boosting clear losers)

    'weight_boost_factor': 0.1,               # Multiplier in weight formula:
                                               # final_score = llm_score * (1.0 + (weight - 1.0) * factor)
                                               # Max boost: ~0.2 for LubimyCzytac (weight=3.0)

    # === LLM API Parameters ===
    'single_score_temperature': 0.1,          # Temperature for single candidate scoring
                                               # Low value for consistent results

    'batch_score_temperature': 0.3,           # Temperature for batch candidate scoring
                                               # Higher value allows better reasoning/comparison
}

# Convenience accessors (for backward compatibility and cleaner imports)
LLM_ACCEPTANCE_THRESHOLD = LLM_SCORING_THRESHOLDS['llm_acceptance_threshold']
YOLO_AUTO_ACCEPT_THRESHOLD = LLM_SCORING_THRESHOLDS['yolo_auto_accept_threshold']
WEIGHT_MIN_SCORE_THRESHOLD = LLM_SCORING_THRESHOLDS['weight_min_score_threshold']
WEIGHT_SIMILARITY_BRACKET = LLM_SCORING_THRESHOLDS['weight_similarity_bracket']
WEIGHT_BOOST_FACTOR = LLM_SCORING_THRESHOLDS['weight_boost_factor']

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
def get_chrome_options(use_profile=False, user_data_dir=None):
    """
    Get Chrome options for Selenium WebDriver with stealth mode.

    Args:
        use_profile: If True, configure to use user's real Chrome profile
        user_data_dir: Path to Chrome user data directory (auto-detected if None)

    Returns:
        Chrome Options object
    """
    from selenium.webdriver.chrome.options import Options

    chrome_options = Options()

    # === USER PROFILE CONFIGURATION ===
    if use_profile:
        if user_data_dir is None:
            user_data_dir = get_chrome_profile_path()

        if user_data_dir:
            chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
            # Prevent Chrome from restoring previous session windows
            chrome_options.add_argument("--no-first-run")
            chrome_options.add_argument("--no-default-browser-check")
            chrome_options.add_argument("--disable-session-crashed-bubble")
            chrome_options.add_argument("--disable-infobars")
            log.debug(f"Configured Chrome to use profile: {user_data_dir}")
        else:
            log.warning("Profile requested but path not found, using ephemeral profile")

    # === STEALTH MODE: Anti-Bot Detection ===
    # Exclude automation flags that expose WebDriver
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    # Disable blink features that detect automation
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")

    # === REALISTIC USER AGENT ===
    # Use a recent, realistic Chrome user agent (update periodically)
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )

    # === WINDOW AND DISPLAY ===
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--start-maximized")

    # === LANGUAGE AND LOCALE ===
    # Set language to match typical user
    chrome_options.add_argument("--lang=en-US")

    # Build prefs dictionary
    prefs = {
        'intl.accept_languages': 'en-US,en;q=0.9',
        'profile.default_content_setting_values.notifications': 2,  # Block notifications
    }

    # When using profile, prevent session restore to avoid opening extra windows
    if use_profile:
        prefs['session.restore_on_startup'] = 4  # 4 = Open New Tab Page (don't restore session)
        prefs['browser.startup.page'] = 0  # 0 = blank page

    chrome_options.add_experimental_option('prefs', prefs)

    # === PERFORMANCE AND STABILITY ===
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-software-rasterizer")

    # Disable unnecessary features
    chrome_options.add_argument("--disable-3d-apis")
    chrome_options.add_argument("--disable-accelerated-2d-canvas")
    chrome_options.add_argument("--disable-gl-drawing-for-tests")
    chrome_options.add_argument("--disable-gpu-compositing")
    chrome_options.add_argument("--disable-cloud-import")
    chrome_options.add_argument("--disable-component-update")
    chrome_options.add_argument("--disable-background-networking")
    chrome_options.add_argument("--disable-client-side-phishing-detection")
    chrome_options.add_argument("--disable-sync")
    chrome_options.add_argument("--disable-extensions")

    # === LOGGING ===
    chrome_options.add_argument("--log-level=3")

    return chrome_options

def get_chrome_profile_path():
    """
    Auto-detect Chrome profile path for current OS.
    Returns None if profile doesn't exist.
    """
    import platform
    from pathlib import Path

    # Check for environment variable override
    env_path = os.getenv('CHROME_PROFILE_PATH')
    if env_path:
        path = Path(env_path)
        if path.exists():
            return str(path)
        else:
            log.warning(f"CHROME_PROFILE_PATH set but doesn't exist: {env_path}")
            return None

    # Auto-detect based on OS
    system = platform.system()

    if system == 'Windows':
        path = Path(os.getenv('LOCALAPPDATA')) / 'Google' / 'Chrome' / 'User Data'
    elif system == 'Darwin':  # macOS
        path = Path.home() / 'Library' / 'Application Support' / 'Google' / 'Chrome'
    elif system == 'Linux':
        path = Path.home() / '.config' / 'google-chrome'
    else:
        log.debug(f"Unknown OS: {system}, cannot auto-detect Chrome profile")
        return None

    if path.exists():
        log.debug(f"Chrome profile detected at: {path}")
        return str(path)
    else:
        log.debug(f"Chrome profile not found at: {path}")
        return None

def copy_chrome_profile_to_temp(source_profile_path):
    """
    Copy Chrome profile to temp directory for use when real profile is locked.
    Only copies if existing copy is older than 30 days.
    Removes lock files from the copy.

    Args:
        source_profile_path: Path to real Chrome profile

    Returns:
        str: Path to copied profile, or None if copy failed
    """
    import tempfile
    import shutil
    from pathlib import Path
    import time

    try:
        # Define temp profile path
        temp_dir = Path(tempfile.gettempdir()) / 'badaboombooksprofile_chrome'

        # Check if we need to refresh the copy (older than 30 days)
        needs_copy = True
        if temp_dir.exists():
            # Check age of temp profile
            profile_age_days = (time.time() - temp_dir.stat().st_mtime) / (60 * 60 * 24)
            if profile_age_days < 30:
                log.debug(f"Using existing temp profile (age: {profile_age_days:.1f} days)")
                needs_copy = False
            else:
                log.debug(f"Temp profile is {profile_age_days:.1f} days old, refreshing...")
                # Remove old copy
                shutil.rmtree(temp_dir, ignore_errors=True)

        # Copy profile if needed
        if needs_copy:
            log.debug(f"Copying Chrome profile to temp: {temp_dir}")
            shutil.copytree(source_profile_path, temp_dir, dirs_exist_ok=True)
            log.debug("Profile copy completed")

        # Remove lock files from the copy
        lock_files = ['SingletonLock', 'SingletonCookie', 'SingletonSocket']
        for lock_file in lock_files:
            lock_path = temp_dir / lock_file
            if lock_path.exists():
                lock_path.unlink()
                log.debug(f"Removed lock file: {lock_file}")

        return str(temp_dir)

    except Exception as e:
        log.debug(f"Failed to copy profile to temp: {e}")
        return None

def is_chrome_running():
    """
    Check if Chrome browser is currently running.

    Returns:
        bool: True if Chrome is running, False otherwise
    """
    try:
        import psutil

        # Check for chrome.exe process (Windows) or chrome/chromium (Linux/Mac)
        chrome_names = ['chrome.exe', 'chrome', 'chromium', 'chromium-browser', 'Google Chrome']

        for proc in psutil.process_iter(['name']):
            try:
                proc_name = proc.info['name']
                if proc_name and any(chrome_name.lower() in proc_name.lower() for chrome_name in chrome_names):
                    log.debug(f"Detected running Chrome process: {proc_name}")
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        return False

    except ImportError:
        # psutil not available, assume Chrome might be running (safer to use copied profile)
        log.debug("psutil not available, cannot detect Chrome - assuming it might be running")
        return True
    except Exception as e:
        log.debug(f"Error checking if Chrome is running: {e}")
        return True  # Assume running on error (safer)

def initialize_chrome_driver():
    """
    Initialize Chrome WebDriver with smart profile selection.

    Strategy:
    1. Check if Chrome is running (profile would be locked)
    2. If not running, try real profile directly
    3. If running, copy profile to temp and use copy
    4. If copy fails, fall back to ephemeral profile

    Returns:
        tuple: (driver, profile_mode) where profile_mode is 'real', 'copied', or 'ephemeral'
    """
    from selenium import webdriver

    use_real_profile = os.getenv('CHROME_USE_REAL_PROFILE', 'true').lower() == 'true'

    if not use_real_profile:
        # User explicitly disabled real profile
        chrome_options = get_chrome_options(use_profile=False)
        driver = webdriver.Chrome(options=chrome_options)
        return driver, 'ephemeral'

    # Get real profile path
    profile_path = get_chrome_profile_path()
    if not profile_path:
        # Profile not found, use ephemeral
        log.debug("Chrome profile not found, using ephemeral profile")
        chrome_options = get_chrome_options(use_profile=False)
        driver = webdriver.Chrome(options=chrome_options)
        return driver, 'ephemeral'

    # Check if Chrome is running (profile would be locked)
    chrome_running = is_chrome_running()

    if chrome_running:
        # Chrome is running, profile is locked - use copied profile
        log.debug("Chrome is running, will use copied profile to avoid conflicts")
        copied_profile_path = copy_chrome_profile_to_temp(profile_path)

        if copied_profile_path:
            try:
                # Try using the copied profile
                chrome_options = get_chrome_options(use_profile=True, user_data_dir=copied_profile_path)
                driver = webdriver.Chrome(options=chrome_options)
                log.debug("Successfully initialized Chrome with copied profile")
                return driver, 'copied'

            except Exception as copy_error:
                # Even copied profile failed - fall back to ephemeral
                log.debug(f"Failed to use copied profile: {copy_error}")
                log.debug("Falling back to ephemeral profile")
                chrome_options = get_chrome_options(use_profile=False)
                driver = webdriver.Chrome(options=chrome_options)
                return driver, 'ephemeral'

        else:
            # Profile copy failed - fall back to ephemeral
            log.debug("Profile copy failed, falling back to ephemeral profile")
            chrome_options = get_chrome_options(use_profile=False)
            driver = webdriver.Chrome(options=chrome_options)
            return driver, 'ephemeral'

    else:
        # Chrome not running, can use real profile directly
        try:
            chrome_options = get_chrome_options(use_profile=True, user_data_dir=profile_path)
            driver = webdriver.Chrome(options=chrome_options)
            log.debug("Successfully initialized Chrome with real profile")
            return driver, 'real'

        except Exception as e:
            # Real profile failed (unexpected) - try copying as fallback
            log.debug(f"Failed to use real profile despite Chrome not running: {e}")
            log.debug("Attempting to copy profile to temp directory...")

            copied_profile_path = copy_chrome_profile_to_temp(profile_path)

            if copied_profile_path:
                try:
                    # Try using the copied profile
                    chrome_options = get_chrome_options(use_profile=True, user_data_dir=copied_profile_path)
                    driver = webdriver.Chrome(options=chrome_options)
                    log.debug("Successfully initialized Chrome with copied profile")
                    return driver, 'copied'

                except Exception as copy_error:
                    # Even copied profile failed - fall back to ephemeral
                    log.debug(f"Failed to use copied profile: {copy_error}")
                    log.debug("Falling back to ephemeral profile")
                    chrome_options = get_chrome_options(use_profile=False)
                    driver = webdriver.Chrome(options=chrome_options)
                    return driver, 'ephemeral'

            else:
                # Profile copy failed - fall back to ephemeral
                log.debug("Profile copy failed, falling back to ephemeral profile")
                chrome_options = get_chrome_options(use_profile=False)
                driver = webdriver.Chrome(options=chrome_options)
                return driver, 'ephemeral'

# === ENVIRONMENT CONFIGURATION ===
def setup_environment():
    """Setup environment variables and paths."""
    os.environ['GCM_ENCRYPTION_DISABLED'] = '1'  # Disable problematic GCM encryption

# === DEFAULT VALUES ===
DEFAULT_SEARCH_LIMIT = 5
DEFAULT_DOWNLOAD_LIMIT = 3
DEFAULT_SEARCH_DELAY = 2.0
DEFAULT_SEARCH_WAIT_TIMEOUT = 10  # Max seconds to wait for search results to load
