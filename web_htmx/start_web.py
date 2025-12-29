#!/usr/bin/env python3
"""
BadaBoomBooks Web Interface Launcher

Simple launcher script for the web interface.
"""

import os
import sys
from pathlib import Path

# Add src to path
root_dir = Path(__file__).parent.parent
src_dir = root_dir / 'src'
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(root_dir))

# Import and run app
from app import app

if __name__ == '__main__':
    print("=" * 60)
    print("BadaBoomBooks Web Interface - HTMX Edition")
    print("=" * 60)
    print()
    print("Starting server...")
    print("Access the interface at: http://localhost:5000")
    print()
    print("Press Ctrl+C to stop the server")
    print("=" * 60)
    print()

    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        use_reloader=True
    )
