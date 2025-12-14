#!/usr/bin/env python3
"""Test imports for web interface."""

import sys
from pathlib import Path

# Add the src directory to the Python path
root_dir = Path(__file__).parent.parent
src_dir = root_dir / 'src'
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(root_dir))

try:
    print("Testing imports...")
    
    # Test core imports
    from src.main import BadaBoomBooksApp
    print("✅ BadaBoomBooksApp imported")
    
    from src.models import ProcessingArgs, BookMetadata
    print("✅ Models imported")
    
    from src.config import SCRAPER_REGISTRY, __version__
    print("✅ Config imported")
    
    # Test Flask imports
    from flask import Flask
    print("✅ Flask imported")
    
    from flask_socketio import SocketIO
    print("✅ SocketIO imported")
    
    print(f"\n🎉 All imports successful! BadaBoomBooks v{__version__}")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("\nMake sure you're in the web/ directory and all dependencies are installed.")
    sys.exit(1)
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    sys.exit(1)
