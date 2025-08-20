#!/usr/bin/env python3
"""
BadaBoomBooks - Audiobook Organization Tool

New modular entry point that uses the reorganized codebase.
This script maintains backward compatibility while using the new architecture.
"""

import sys
from pathlib import Path

# Add the src directory to the Python path
root_dir = Path(__file__).parent
src_dir = root_dir / 'src'
sys.path.insert(0, str(src_dir))

# Import and run the main application
from src.main import main

if __name__ == "__main__":
    sys.exit(main())
