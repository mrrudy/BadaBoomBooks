#!/usr/bin/env python3
"""Test the updated UI with book context."""

import sys
from pathlib import Path

# Add the src directory to the Python path  
root_dir = Path(__file__).parent
src_dir = root_dir / 'src'
sys.path.insert(0, str(src_dir))

try:
    print("🧪 Testing updated UI with book context...")
    
    # Test the context display method
    from src.search.auto_search import AutoSearchEngine
    
    search_engine = AutoSearchEngine()
    
    # Test with book info
    book_info = {
        'title': 'All Systems Red',
        'author': 'Martha Wells',
        'series': 'The Murderbot Diaries',
        'volume': '1',
        'narrator': 'Kevin R. Free',
        'year': '2017',
        'language': 'English',
        'source': 'ID3 tags',
        'folder_name': '1 - All Systems Red'
    }
    
    print("\n=== Testing book context display ===")
    search_engine._display_book_context("All Systems Red by Martha Wells", book_info)
    
    # Test with minimal info
    minimal_info = {
        'folder_name': 'Some Unknown Book',
        'source': 'folder name'
    }
    
    print("\n=== Testing minimal context display ===") 
    search_engine._display_book_context("Some Unknown Book", minimal_info)
    
    # Test with no info
    print("\n=== Testing no context display ===")
    search_engine._display_book_context("Unknown Book")
    
    print("\n✅ UI context display test completed successfully!")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    sys.exit(1)
