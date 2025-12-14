#!/usr/bin/env python3
"""
BadaBoomBooks Web Interface Launcher

Convenience script to start the web interface with proper configuration.
"""

import os
import sys
import subprocess
from pathlib import Path

def check_requirements():
    """Check if required packages are installed."""
    required_packages = {
        'flask': 'flask',
        'flask_socketio': 'flask_socketio', 
        'requests': 'requests',
        'beautifulsoup4': 'bs4',  # Package name vs import name
        'selenium': 'selenium',
        'tinytag': 'tinytag',
        'mutagen': 'mutagen'
    }
    
    missing_packages = []
    
    for package_name, import_name in required_packages.items():
        try:
            __import__(import_name.replace('-', '_'))
        except ImportError:
            missing_packages.append(package_name)
    
    if missing_packages:
        print("❌ Missing required packages:")
        for package in missing_packages:
            print(f"   - {package}")
        print("\n🔧 Install missing packages with:")
        print(f"   pip install {' '.join(missing_packages)}")
        print("\n📦 Or install all web requirements with:")
        print("   pip install -r requirements.txt")
        return False
    
    return True

def main():
    """Main launcher function."""
    print("🌐 BadaBoomBooks Web Interface Launcher")
    print("=" * 50)
    
    # Check if we're in the right directory
    web_dir = Path(__file__).parent
    if not (web_dir / 'app.py').exists():
        print("❌ Error: Cannot find app.py")
        print("   Make sure you're running this from the web/ directory")
        return 1
    
    # Check requirements
    print("🔍 Checking requirements...")
    if not check_requirements():
        return 1
    
    print("✅ All requirements satisfied")
    
    # Start the web interface
    print("\n🚀 Starting BadaBoomBooks Web Interface...")
    print("\n📍 The interface will be available at:")
    print("   • Local:   http://localhost:5000")
    print("   • Network: http://0.0.0.0:5000")
    print("\n⚠️  Press Ctrl+C to stop the server")
    print("=" * 50)
    
    try:
        # Change to web directory
        os.chdir(web_dir)
        
        # Start the Flask app
        subprocess.run([sys.executable, 'app.py'], check=True)
        
    except KeyboardInterrupt:
        print("\n\n🛑 Server stopped by user")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Error starting server: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
