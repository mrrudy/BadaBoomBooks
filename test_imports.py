#!/usr/bin/env python3
"""Test imports for the modular BadaBoomBooks."""

import sys
from pathlib import Path

# Add the src directory to the Python path
root_dir = Path(__file__).parent
src_dir = root_dir / 'src'
sys.path.insert(0, str(src_dir))

try:
    print("Testing imports...")
    
    # Test basic imports
    from src.config import SCRAPER_REGISTRY, __version__
    print(f"✓ Config imported successfully. Version: {__version__}")
    print(f"✓ Found {len(SCRAPER_REGISTRY)} scrapers: {list(SCRAPER_REGISTRY.keys())}")
    
    # Test models
    from src.models import BookMetadata, ProcessingArgs
    print("✓ Models imported successfully")
    
    # Test UI
    from src.ui import CLIHandler, ProgressReporter
    print("✓ UI modules imported successfully")
    
    # Test search
    from src.search import AutoSearchEngine, ManualSearchHandler
    print("✓ Search modules imported successfully")
    
    # Test scrapers
    from src.scrapers import AudibleScraper, GoodreadsScraper, LubimyczytacScraper
    print("✓ Scrapers imported successfully")
    
    # Test processors
    from src.processors import FileProcessor, MetadataProcessor, AudioProcessor
    print("✓ Processors imported successfully")
    
    # Test main
    from src.main import BadaBoomBooksApp
    print("✓ Main app imported successfully")
    
    print("\n🎉 All imports successful! The modular architecture is working.")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    sys.exit(1)
