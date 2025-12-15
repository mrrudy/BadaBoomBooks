# BadaBoomBooks - Audiobook Organization Tool

An advanced audiobook organization tool that automatically scrapes metadata from multiple sources and organizes your audiobook collection with proper folder structure, metadata files, and ID3 tags.

## 🚀 Quick Start

### 💻 **Command Line Interface** (Recommended)
```bash
# Basic usage - organize audiobooks with automatic search
python BadaBoomBooks.py --auto-search --opf --id3-tag -O "C:\Organized Books" "C:\Audiobook Folder"

# Advanced usage - series organization with all features
python BadaBoomBooks.py --auto-search --series --opf --infotxt --id3-tag --cover --move -O -R T:\Incoming -O T:\Sorted\

# AI assisted sorting with all the futures
python BadaBoomBooks.py --opf --id3-tag --series --cover --move --rename --from-opf --auto-search --llm-select -R T:\Incoming -O T:\Sorted\  

# Dry run to see what would happen
python BadaBoomBooks.py --dry-run --auto-search --series --opf "C:\Audiobook Folder"
```

### 🌐 **Web Interface** (WiP)
```bash
# Start the modern web interface
cd web
python start_web.py

# Open browser to http://localhost:5000
```

## ✨ **Features**

### 🔍 **Intelligent Search & Scraping**
- **Multi-site Support**: Audible, Goodreads, LubimyCzytac.pl
- **Automated Search**: Browser automation with candidate selection
- **Manual Search**: Clipboard monitoring for manual URL input
- **Smart Fallbacks**: Multiple scraping strategies per site

### 📁 **Advanced Organization**
- **Series Support**: Organize by author/series/volume structure
- **Flexible Output**: Copy, move, or in-place processing
- **Path Cleaning**: Automatic filename sanitization
- **Duplicate Handling**: Smart folder deduplication

### 📋 **Metadata Management**
- **OPF Generation**: Audiobookshelf-compatible metadata files
- **Info.txt Creation**: SmartAudioBookPlayer summaries
- **ID3 Tag Updates**: Complete audio file tagging
- **Cover Downloads**: High-quality cover art

### 🎵 **Audio Processing**
- **Track Renaming**: Standardized "## - Title" format
- **Folder Flattening**: Single-level audio organization
- **Multi-format Support**: MP3, M4A, M4B, FLAC, OGG, WMA
- **Metadata Embedding**: Complete ID3 tag population

## 🏗️ Architecture

This tool uses a modern modular architecture for maintainability and extensibility:

```
src/
├── main.py                 # Application orchestrator
├── config.py              # Configuration & constants
├── models.py               # Data structures & validation
├── utils.py                # Utility functions
├── ui/                     # User interface components
├── search/                 # Search & URL handling
├── scrapers/               # Web scraping functionality
└── processors/             # File & metadata processing
```

See [`MODULAR_ARCHITECTURE.md`](MODULAR_ARCHITECTURE.md) for detailed documentation.

## 📖 Usage

### Command Line Arguments

#### Input/Output Options
- `folders` - Audiobook folder(s) to process
- `-O, --output` - Output directory for organized books  
- `-R, --book-root` - Process all audiobook folders in directory

#### Operation Modes
- `-c, --copy` - Copy folders (preserve originals)
- `-m, --move` - Move folders (delete originals) 
- `-D, --dry-run` - Preview changes without modifying files

#### Processing Options
- `-f, --flatten` - Flatten nested folder structures
- `-r, --rename` - Rename tracks to standard format
- `-S, --series` - Organize by series structure
- `-I, --id3-tag` - Update ID3 tags

#### Metadata Options  
- `-i, --infotxt` - Generate info.txt summaries
- `-o, --opf` - Generate OPF metadata files
- `-C, --cover` - Download cover images
- `-F, --from-opf` - Read existing OPF metadata

#### Search Options
- `-s, --site` - Specify search site (audible/goodreads/lubimyczytac/all)
- `--auto-search` - Automated search with candidate selection
  - **Custom URL support**: Enter a URL directly during selection instead of choosing numbered options
  - Accepts both full URLs (`https://lubimyczytac.pl/ksiazka/...`) and partial URLs (`lubimyczytac.pl/ksiazka/...`)
  - Validates URL against supported sites before proceeding
- `--search-limit` - Results per site (default: 5)
- `--download-limit` - Pages to download per site (default: 3)
- `--search-delay` - Delay between requests (default: 2.0s)

#### Debug Options
- `-d, --debug` - Enable debug logging
- `-v, --version` - Show version information

### Examples

#### Basic Organization
```bash
# Organize single folder with manual search
python BadaBoomBooks.py "C:\My Audiobook"

# Organize multiple folders
python BadaBoomBooks.py "Book1" "Book2" "Book3"
```

#### Automated Processing
```bash
# Auto-search with series organization
python BadaBoomBooks.py --auto-search --series --move \
  -O "C:\Organized" -R "C:\Incoming"

# Complete processing with all features
python BadaBoomBooks.py --auto-search --series --opf --infotxt \
  --id3-tag --cover --flatten --rename --move \
  -O "T:\Library" "C:\Audiobook"
```

#### Dry Run Testing
```bash
# See what would happen without making changes
python BadaBoomBooks.py --dry-run --auto-search --series \
  --opf --id3-tag "C:\Test Folder"
```

## 📚 Supported Sites

### 🎧 Audible.com
- **API Integration**: Direct API access for reliable data
- **Rich Metadata**: Series, narrators, publication info
- **High Quality**: Official source data

### 📖 Goodreads.com  
- **Dual Format Support**: Handles old and new page layouts
- **Comprehensive Data**: Reviews, genres, series information
- **Language Detection**: Automatic language identification

### 🇵🇱 LubimyCzytac.pl
- **Polish Content**: Specialized for Polish audiobooks
- **Series Parsing**: Advanced volume range handling
- **Original Titles**: Tracks translated vs original titles

## 🔧 Installation

### Requirements
```bash
pip install -r requirements.txt
```

### Dependencies
- `requests` - HTTP client
- `beautifulsoup4` - HTML parsing
- `selenium` - Browser automation
- `tinytag` - Audio metadata reading
- `mutagen` - ID3 tag writing
- `pyperclip` - Clipboard monitoring

### Browser Setup
Chrome/Chromium required for automated search functionality.

## 📁 Output Structure

### Standard Organization
```
Output/
├── Author Name/
│   ├── Book Title/
│   │   ├── 01 - Book Title.mp3
│   │   ├── 02 - Book Title.mp3
│   │   ├── metadata.opf
│   │   ├── info.txt
│   │   └── cover.jpg
│   └── Another Book/
└── Another Author/
```

### Series Organization (`--series`)
```
Output/
├── Author Name/
│   └── Series Name/
│       ├── 1 - First Book/
│       ├── 2 - Second Book/
│       └── 3,4 - Combined Volume/
└── Another Author/
```

## 🛠️ Development

### Adding New Scrapers
1. Create scraper class inheriting from `BaseScraper`
2. Register in `SCRAPER_REGISTRY` 
3. Implement required methods
4. Update imports

See [`MIGRATION_GUIDE.md`](MIGRATION_GUIDE.md) for detailed development information.

### Testing
```bash
# Test individual components
python -m pytest tests/

# Test imports
python -c "from src.main import BadaBoomBooksApp; print('✅ Imports working')"

# Scrapers - Full regression (all samples per service)
python -m pytest src/tests/test_scrapers.py::test_lubimyczytac_scraper_regression_all_samples -v -s

# TDD workflow
mkdir -p src/tests/data/scrapers/tdd/my-test
# Create metadata.opf with expected values
python -m pytest src/tests/test_scrapers.py::test_manual_tdd_sample -v -s
```

## 📜 Legacy Code

Original monolithic code has been archived in `legacy/` folder. The new modular architecture maintains full backward compatibility while providing enhanced maintainability.

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Follow the modular architecture patterns
4. Add tests for new functionality
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- Community for providing content and building tools
- Contributors to the libraries this project depends on
- Users who provided feedback and testing

---

**Happy organizing!** 📚🎧
