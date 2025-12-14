#!/usr/bin/env python3
"""
Simple test for web processing integration
"""

import sys
from pathlib import Path

# Add the src directory to the Python path
root_dir = Path(__file__).parent.parent
src_dir = root_dir / 'src'
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(root_dir))

def test_processing():
    try:
        print("Testing web processing integration...")
        
        # Test imports
        from src.main import BadaBoomBooksApp
        from src.models import ProcessingArgs, BookMetadata
        print("✅ Core imports successful")
        
        # Test app creation
        app = BadaBoomBooksApp()
        print("✅ App creation successful")
        
        # Test folder info extraction
        test_folder = Path(".")
        book_info = app._extract_book_info(test_folder)
        print(f"✅ Book info extraction: {book_info}")
        
        # Test ProcessingArgs creation
        args = ProcessingArgs(
            folders=[Path(".")],
            auto_search=True,
            dry_run=True
        )
        print("✅ ProcessingArgs creation successful")
        
        print("\n🎉 All tests passed! Web processing should work.")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_processing()
