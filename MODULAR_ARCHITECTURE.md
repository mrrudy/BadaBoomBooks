# BadaBoomBooks - Modular Architecture

This document explains the new modular architecture that splits the monolithic `BadaBoomBooks.py` into logical, maintainable components.

## 🏗️ Architecture Overview

The application has been reorganized into the following modules:

```
src/
├── __init__.py                 # Package initialization
├── main.py                     # Main application orchestrator
├── config.py                   # Configuration and constants
├── models.py                   # Data structures and models
├── utils.py                    # Utility functions
├── ui/                         # User interface components
│   ├── __init__.py
│   ├── cli.py                  # Command line interface
│   ├── progress.py             # Progress reporting
│   └── output.py               # Output formatting
├── search/                     # Search and URL handling
│   ├── __init__.py
│   ├── auto_search.py          # Automated search engine
│   ├── manual_search.py        # Manual search handling
│   └── candidate_selection.py  # Candidate selection logic
├── scrapers/                   # Web scraping functionality
│   ├── __init__.py
│   ├── base.py                 # Base scraper classes
│   ├── audible.py              # Audible.com scraper
│   ├── goodreads.py            # Goodreads.com scraper
│   └── lubimyczytac.py         # LubimyCzytac.pl scraper
└── processors/                 # File and metadata processing
    ├── __init__.py
    ├── file_operations.py      # File system operations
    ├── metadata_operations.py  # Metadata file creation
    └── audio_operations.py     # Audio file processing
```

## 📦 Module Descriptions

### Core Modules

#### `config.py`
- **Purpose**: Centralized configuration management
- **Contains**: Application constants, scraper registry, logging setup, browser configuration
- **Key Features**: 
  - `SCRAPER_REGISTRY` - Central registry of all supported sites
  - Chrome options for Selenium
  - File paths and default values

#### `models.py`
- **Purpose**: Data structures and validation
- **Contains**: `BookMetadata`, `ProcessingResult`, `ProcessingArgs`, `SearchCandidate`
- **Key Features**:
  - Type-safe data structures with validation
  - Helper methods for data manipulation
  - Serialization support

#### `utils.py`
- **Purpose**: Common utility functions
- **Contains**: Path manipulation, text cleaning, validation functions
- **Key Features**:
  - Filename sanitization
  - Audio file detection
  - Search term generation
  - Progress tracking utilities

#### `main.py`
- **Purpose**: Application orchestration and workflow
- **Contains**: `BadaBoomBooksApp` class that coordinates all other modules
- **Key Features**:
  - Complete processing pipeline
  - Error handling and recovery
  - Queue management

### UI Package (`ui/`)

#### `cli.py`
- **Purpose**: Command line interface handling
- **Contains**: Argument parsing, validation, user prompts
- **Key Features**:
  - Comprehensive argument validation
  - Folder discovery from book roots
  - User confirmation dialogs

#### `progress.py`
- **Purpose**: Progress tracking and reporting
- **Contains**: Progress reporters for different verbosity levels
- **Key Features**:
  - Real-time progress updates
  - Time estimation
  - Multiple output modes (normal, quiet, verbose)

#### `output.py`
- **Purpose**: Output formatting and display
- **Contains**: Formatters for various data types
- **Key Features**:
  - Metadata summaries
  - Error reports
  - Statistical summaries
  - Table formatting

### Search Package (`search/`)

#### `auto_search.py`
- **Purpose**: Automated search across multiple sites
- **Contains**: `AutoSearchEngine` for Selenium-based searching
- **Key Features**:
  - DuckDuckGo integration
  - Multi-site searching
  - Page downloading and caching
  - Debug page saving

#### `manual_search.py`
- **Purpose**: Manual URL input and clipboard monitoring
- **Contains**: `ManualSearchHandler` for user-driven search
- **Key Features**:
  - Clipboard monitoring
  - URL validation
  - Browser automation
  - Manual URL prompts

#### `candidate_selection.py`
- **Purpose**: Intelligent candidate selection
- **Contains**: `CandidateSelector` with heuristic and AI selection
- **Key Features**:
  - Scoring algorithms
  - Future AI integration placeholder
  - Selection explanation

### Scrapers Package (`scrapers/`)

#### `base.py`
- **Purpose**: Base scraper functionality
- **Contains**: `BaseScraper` abstract class and HTTP utilities
- **Key Features**:
  - Standardized scraper interface
  - HTTP request handling with retries
  - Error recovery

#### `audible.py`
- **Purpose**: Audible.com API integration
- **Contains**: `AudibleScraper` for API-based metadata extraction
- **Key Features**:
  - API endpoint handling
  - ASIN extraction
  - Comprehensive metadata parsing

#### `goodreads.py`
- **Purpose**: Goodreads.com scraping
- **Contains**: `GoodreadsScraper` with support for multiple page formats
- **Key Features**:
  - Type 1 and Type 2 page format support
  - JSON-LD parsing
  - Language and ISBN extraction

#### `lubimyczytac.py`
- **Purpose**: Polish book site scraping
- **Contains**: `LubimyczytacScraper` for Polish metadata
- **Key Features**:
  - Polish language support
  - Series parsing with volume ranges
  - Original title extraction

### Processors Package (`processors/`)

#### `file_operations.py`
- **Purpose**: File system operations
- **Contains**: `FileProcessor` for copying, moving, organizing files
- **Key Features**:
  - Safe file operations with validation
  - Folder flattening
  - Track renaming
  - Series-based organization

#### `metadata_operations.py`
- **Purpose**: Metadata file creation and reading
- **Contains**: `MetadataProcessor` for OPF, info.txt files
- **Key Features**:
  - OPF template processing
  - XML sanitization
  - Cover image downloading
  - Metadata comparison

#### `audio_operations.py`
- **Purpose**: Audio file processing
- **Contains**: `AudioProcessor` for ID3 tag updates
- **Key Features**:
  - MP3 tag updates
  - Multi-format support
  - Audio file analysis
  - Metadata embedding

## 🔄 Usage

### Running the Modular Version

```bash
# Use the new modular entry point
python BadaBoomBooks_modular.py [arguments]

# Or run directly
python src/main.py [arguments]
```

### Backward Compatibility

The original `BadaBoomBooks.py` remains functional, but new development should use the modular architecture.

### Examples

```bash
# Process folders with series organization
python BadaBoomBooks_modular.py --series --move -O "/output/path" folder1/ folder2/

# Auto-search with debug enabled
python BadaBoomBooks_modular.py --auto-search --debug --opf --infotxt folder/

# Dry run to see what would happen
python BadaBoomBooks_modular.py --dry-run --series --flatten folder/
```

## 🧪 Testing

Each module can be tested independently:

```python
# Test configuration
from src.config import SCRAPER_REGISTRY
print(SCRAPER_REGISTRY.keys())

# Test models
from src.models import BookMetadata
metadata = BookMetadata.create_empty("test_folder")
print(metadata.is_valid_for_processing())

# Test scrapers
from src.scrapers import GoodreadsScraper
scraper = GoodreadsScraper()
```

## 🚀 Benefits of Modular Architecture

### For AI Analysis
- **Clear boundaries**: Each module has a single responsibility
- **Self-contained**: Modules can be understood without reading the entire codebase
- **Documented interfaces**: Clear input/output contracts
- **Type hints**: Better code understanding for AI tools

### For Development
- **Maintainability**: Changes are isolated to specific modules
- **Testability**: Individual components can be tested in isolation
- **Extensibility**: New features can be added as new modules
- **Readability**: Code is organized by functionality

### For Future Enhancements
- **Plugin architecture**: New scrapers can be added easily
- **AI integration**: Candidate selection can be enhanced with ML
- **API support**: Modules can be exposed as REST APIs
- **GUI support**: UI modules can be replaced with graphical interfaces

## 🔧 Development Guidelines

### Adding New Scrapers
1. Create new scraper class inheriting from `BaseScraper`
2. Add entry to `SCRAPER_REGISTRY` in `config.py`
3. Implement required abstract methods
4. Add backward compatibility function if needed

### Adding New Features
1. Identify the appropriate module (or create new one)
2. Update models if new data structures are needed
3. Add CLI arguments in `ui/cli.py`
4. Update the main processing pipeline in `main.py`

### Code Style
- Use type hints for all public interfaces
- Document complex functions with docstrings
- Keep functions focused on single responsibilities
- Use defensive programming with proper error handling

## 📝 Migration Notes

### From Original Code
- All original functionality is preserved
- Configuration file format remains the same
- Command line interface is identical
- Processing workflow is unchanged

### Key Changes
- Better error handling and recovery
- More detailed progress reporting
- Improved logging and debugging
- Enhanced validation and type safety

This modular architecture provides a solid foundation for future development while maintaining full backward compatibility with existing workflows.
