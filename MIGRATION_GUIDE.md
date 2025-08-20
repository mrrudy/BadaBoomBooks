# Migration Guide: From Monolithic to Modular BadaBoomBooks

This guide helps you understand how the original monolithic code has been split into the new modular architecture.

## 📁 File Mapping

### Original Functions → New Locations

| Original Function | New Location | Notes |
|------------------|--------------|-------|
| `clipboard_queue()` | `search/manual_search.py` | Now part of `ManualSearchHandler` |
| `auto_search_and_select()` | `search/auto_search.py` | Now in `AutoSearchEngine` class |
| `api_audible()` | `scrapers/audible.py` | Now in `AudibleScraper` class |
| `scrape_goodreads_type1()` | `scrapers/goodreads.py` | Now in `GoodreadsScraper` class |
| `scrape_goodreads_type2()` | `scrapers/goodreads.py` | Now in `GoodreadsScraper` class |
| `scrape_lubimyczytac()` | `scrapers/lubimyczytac.py` | Now in `LubimyczytacScraper` class |
| `http_request()` | `scrapers/base.py` | Now `http_request_generic()` |
| `create_opf()` | `processors/metadata_operations.py` | Now in `MetadataProcessor` class |
| `create_info()` | `processors/metadata_operations.py` | Now in `MetadataProcessor` class |
| `flatten_folder()` | `processors/file_operations.py` | Now in `FileProcessor` class |
| `rename_tracks()` | `processors/file_operations.py` | Now in `FileProcessor` class |
| `update_id3_tags()` | `processors/audio_operations.py` | Now in `AudioProcessor` class |
| `read_opf_metadata()` | `processors/metadata_operations.py` | Now in `MetadataProcessor` class |

### Original Variables → New Locations

| Original Variable | New Location | Notes |
|------------------|--------------|-------|
| `SCRAPER_REGISTRY` | `config.py` | Centralized configuration |
| `failed_books`, `skipped_books`, `success_books` | `models.py` | Now in `ProcessingResult` class |
| `root_path`, `config_file`, etc. | `config.py` | Centralized paths |
| `args` parsing | `ui/cli.py` | Now in `CLIHandler` class |

## 🔄 Code Migration Examples

### Example 1: Using the New Scrapers

**Before (monolithic):**
```python
# In the original file
metadata = api_audible(metadata, page, log)
```

**After (modular):**
```python
from src.scrapers import AudibleScraper

scraper = AudibleScraper()
metadata = scraper.scrape_metadata(metadata, response, logger)
```

### Example 2: File Operations

**Before (monolithic):**
```python
# Direct function calls
flatten_folder(metadata, log, dry_run)
rename_tracks(metadata, log, dry_run)
```

**After (modular):**
```python
from src.processors import FileProcessor

file_processor = FileProcessor(args)
file_processor.flatten_folder(metadata)
file_processor.rename_audio_tracks(metadata)
```

### Example 3: Progress Reporting

**Before (monolithic):**
```python
print(f"Processing {folder}")
# Manual progress tracking
```

**After (modular):**
```python
from src.ui import ProgressReporter

progress = ProgressReporter()
progress.start_processing(total_books)
progress.start_book(metadata, index)
progress.finish_book(success=True)
```

## 🏗️ Architecture Benefits

### Separation of Concerns

**Before:** Everything in one 1000+ line file
```python
# All mixed together:
# - Argument parsing
# - Web scraping 
# - File operations
# - Progress reporting
# - Error handling
```

**After:** Clear separation
```python
# Each concern in its own module:
ui/cli.py          # Argument parsing
scrapers/          # Web scraping
processors/        # File operations  
ui/progress.py     # Progress reporting
main.py           # Error handling & orchestration
```

### Type Safety

**Before:** No type hints, unclear data flow
```python
def api_audible(metadata, page, log):
    # What type is metadata? page? Return value?
    pass
```

**After:** Clear interfaces with type hints
```python
def scrape_metadata(self, metadata: BookMetadata, 
                   response: requests.Response, 
                   logger: log.Logger) -> BookMetadata:
    pass
```

### Error Handling

**Before:** Scattered try/catch blocks
```python
try:
    # Some operation
    metadata['title'] = page['title']
except:
    # Handle error inline
    pass
```

**After:** Centralized error handling
```python
class BookMetadata:
    def mark_as_failed(self, exception: str):
        self.failed = True
        self.failed_exception = exception
        log.error(f"Marked {self.input_folder} as failed: {exception}")
```

## 🔧 Extending the Modular Code

### Adding a New Scraper

1. **Create the scraper class:**
```python
# src/scrapers/newsite.py
from .base import BaseScraper

class NewSiteScraper(BaseScraper):
    def __init__(self):
        super().__init__("newsite", "newsite.com")
    
    def preprocess_url(self, metadata: BookMetadata) -> None:
        # Extract any needed parameters from URL
        pass
    
    def scrape_metadata(self, metadata: BookMetadata, response, logger) -> BookMetadata:
        # Implement scraping logic
        return metadata
```

2. **Register in config:**
```python
# src/config.py
SCRAPER_REGISTRY["newsite"] = {
    "domain": "newsite.com",
    "url_pattern": r"^http.+newsite.+/book/\d+",
    "search_url": lambda term: f"https://duckduckgo.com/?q=site:newsite.com {term}",
    "scrape_func_name": "scrape_newsite",
    "http_request_func_name": "http_request_generic",
    "preprocess_func_name": None
}
```

3. **Update imports:**
```python
# src/scrapers/__init__.py
from .newsite import NewSiteScraper

__all__ = [..., 'NewSiteScraper']
```

### Adding a New Processing Feature

1. **Extend models if needed:**
```python
# src/models.py
@dataclass
class BookMetadata:
    # Add new field
    new_field: str = ""
```

2. **Add CLI argument:**
```python
# src/ui/cli.py
parser.add_argument('--new-feature', action='store_true', 
                   help='Enable new feature')
```

3. **Implement processor:**
```python
# src/processors/new_processor.py
class NewProcessor:
    def process_new_feature(self, metadata: BookMetadata) -> bool:
        # Implement new functionality
        pass
```

4. **Integrate in main pipeline:**
```python
# src/main.py
if args.new_feature:
    self.progress.report_metadata_operation("Processing", "new feature")
    if not self.new_processor.process_new_feature(metadata):
        return False
```

## 🧪 Testing Individual Modules

### Test Scrapers
```python
from src.scrapers import GoodreadsScraper
from src.models import BookMetadata

scraper = GoodreadsScraper()
metadata = BookMetadata.create_empty("test")
metadata.url = "https://goodreads.com/book/show/123"

# Test scraping (with mock response)
result = scraper.scrape_metadata(metadata, mock_response, logger)
assert result.title == "Expected Title"
```

### Test File Operations
```python
from src.processors import FileProcessor
from src.models import ProcessingArgs

args = ProcessingArgs(copy=True, output=Path("/test"))
processor = FileProcessor(args)

success = processor.process_folder_organization(metadata)
assert success == True
```

## 🚀 Benefits Realized

### For AI Code Analysis
- **Clear interfaces**: Each module has well-defined inputs/outputs
- **Single responsibility**: Each file focuses on one concern
- **Type hints**: Better understanding of data flow
- **Documentation**: Each module is self-documenting

### For Maintenance
- **Isolated changes**: Modifications don't affect other modules
- **Easy testing**: Individual components can be tested separately  
- **Clear dependencies**: Import statements show relationships
- **Reduced complexity**: Smaller, focused files are easier to understand

### For Future Development
- **Plugin architecture**: New scrapers/processors can be added easily
- **API potential**: Modules can be exposed as web services
- **Parallel processing**: Independent modules can run concurrently
- **Team development**: Different developers can work on different modules

## 📋 Checklist for Migration

When working with the new modular code:

- [ ] Use `BadaBoomBooks_modular.py` for new work
- [ ] Import from appropriate modules (`from src.scrapers import ...`)
- [ ] Use type hints for new functions
- [ ] Follow the established module boundaries
- [ ] Add tests for new functionality
- [ ] Update documentation when adding features
- [ ] Consider backward compatibility for breaking changes

This modular architecture provides a solid foundation for future development while maintaining all the functionality of the original codebase.
