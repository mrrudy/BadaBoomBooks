#!/usr/bin/env python3
"""Test the cleaned up modular architecture."""

import sys
from pathlib import Path

# Add the src directory to the Python path
root_dir = Path(__file__).parent
src_dir = root_dir / 'src'
sys.path.insert(0, str(src_dir))

try:
    print("🧪 Testing cleaned up modular architecture...")
    
    # Test basic imports
    from src.config import SCRAPER_REGISTRY, __version__
    print(f"✅ Config: Version {__version__}, {len(SCRAPER_REGISTRY)} scrapers")
    
    # Test all modules
    from src.models import BookMetadata
    from src.ui import CLIHandler
    from src.search import AutoSearchEngine
    from src.scrapers import AudibleScraper, GoodreadsScraper, LubimyczytacScraper
    from src.processors import FileProcessor, MetadataProcessor, AudioProcessor
    from src.main import BadaBoomBooksApp
    print("✅ All modules imported successfully")
    
    # Test language map
    from src.language_map import LANGUAGE_MAP
    print(f"✅ Language map: {len(LANGUAGE_MAP)} languages")
    
    # Test app instantiation
    app = BadaBoomBooksApp()
    print("✅ App instantiation successful")
    
    print("\n🎉 All tests passed! The cleaned up architecture is working perfectly.")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    sys.exit(1)
