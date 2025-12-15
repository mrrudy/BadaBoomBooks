# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BadaBoomBooks is an audiobook organization tool that scrapes metadata from multiple sources (Audible, Goodreads, LubimyCzytac.pl) and organizes audiobook collections with proper folder structure, metadata files, and ID3 tags. The project has both a CLI and a modern web interface.

## Common Commands

### Running the Application

**CLI Interface:**
```bash
# Basic processing with auto-search
python BadaBoomBooks.py --auto-search --opf --id3-tag -O "C:\Organized" "C:\Audiobook Folder"

# Complete processing with series organization
python BadaBoomBooks.py --auto-search --series --opf --infotxt --id3-tag --cover --move -O "T:\Sorted" -R "T:\Incoming"

# YOLO mode - auto-accept all prompts (great for batch processing)
python BadaBoomBooks.py --auto-search --llm-select --yolo --opf --id3-tag --move -O "T:\Sorted" -R "T:\Incoming"

# Dry run for testing
python BadaBoomBooks.py --dry-run --auto-search --series --opf "C:\Test Folder"

# Run from modular source
python src/main.py [arguments]
```

**Web Interface:**
```bash
cd web
python start_web.py
# Access at http://localhost:5000
```

### Development

**Install dependencies:**
```bash
pip install -r requirements.txt

# For web interface
cd web
pip install -r requirements.txt
```

**Test imports and module loading:**
```bash
python -c "from src.main import BadaBoomBooksApp; print('✅ Imports working')"

# Test web interface imports
cd web
python test_imports.py
```

**Enable debug logging:**
```bash
python BadaBoomBooks.py --debug [other arguments]
```

**Run tests:**
```bash
# Run all tests
python -m pytest src/tests/ -v

# Run specific test file
python -m pytest src/tests/test_file_operations.py -v

# Run specific test
python -m pytest src/tests/test_file_operations.py::test_copy_rename_from_opf -v

# Run tests with markers
python -m pytest src/tests/ -v -m integration
```

## Architecture

### Modular Structure

The application uses a **modular architecture** (migrated from legacy monolithic code). Understanding this structure is critical:

```
src/
├── main.py                 # Application orchestrator (BadaBoomBooksApp class)
├── config.py              # SCRAPER_REGISTRY, paths, logging setup
├── models.py              # BookMetadata, ProcessingArgs, ProcessingResult
├── utils.py               # Path sanitization, search term generation
├── ui/                    # CLI, progress reporting, output formatting
├── search/                # AutoSearchEngine, ManualSearchHandler, CandidateSelector
├── scrapers/              # Site-specific scrapers (Audible, Goodreads, LubimyCzytac)
└── processors/            # File, metadata, and audio operations
```

**Key Design Principles:**
- **SCRAPER_REGISTRY** in [config.py](src/config.py) is the central registry for all supported sites
- Each scraper inherits from `BaseScraper` in [scrapers/base.py](src/scrapers/base.py)
- Processing pipeline: Queue Building → Metadata Scraping → File Organization → Metadata Generation → Audio Tagging
- All processors support dry-run mode (`--dry-run` flag)

### Web Interface Architecture

The web interface (`web/` directory) is a Flask + SocketIO application that:
- Uses the same core `src/` modules as the CLI
- Provides real-time progress via WebSocket
- Implements interactive candidate selection
- Runs processing jobs in background threads

**Entry point:** [web/app.py](web/app.py) or [web/start_web.py](web/start_web.py)

### Processing Pipeline

The main processing flow in [src/main.py](src/main.py):

1. **Queue Building Phase** (`_build_processing_queue`):
   - Extract book context from OPF files or ID3 tags
   - Perform auto-search or manual search
   - Store folder→URL mappings in `queue.ini`

2. **Processing Phase** (`_process_queue`):
   - Read queue from `queue.ini`
   - For each book: Scrape → Organize → Flatten → Rename → Generate Metadata → Update Tags
   - Track results in `ProcessingResult`

3. **Metadata Extraction** (`_extract_book_info`):
   - Tries OPF files first, then ID3 tags, then folder name
   - Used for displaying context during candidate selection

### Scraper System

**Three active scrapers:**
1. **AudibleScraper** ([scrapers/audible.py](src/scrapers/audible.py)) - Uses Audible API, requires ASIN extraction
2. **GoodreadsScraper** ([scrapers/goodreads.py](src/scrapers/goodreads.py)) - Handles Type 1 and Type 2 page formats
3. **LubimyczytacScraper** ([scrapers/lubimyczytac.py](src/scrapers/lubimyczytac.py)) - Polish site, handles volume ranges

**To add a new scraper:**
1. Create class in `src/scrapers/new_site.py` inheriting from `BaseScraper`
2. Add entry to `SCRAPER_REGISTRY` in [config.py](src/config.py)
3. Implement `scrape_metadata(metadata, response, log)` method
4. Update imports in [scrapers/__init__.py](src/scrapers/__init__.py)

### Search and Candidate Selection

**Auto-search flow** ([search/auto_search.py](src/search/auto_search.py)):
- Uses Selenium to search DuckDuckGo with `site:domain.com search_term`
- Downloads top N result pages
- Extracts metadata candidates from each page
- Uses `CandidateSelector` for intelligent selection

**Candidate selection** ([search/candidate_selection.py](src/search/candidate_selection.py)):
- **LLM-based selection** (`--llm-select` flag): Uses AI to score candidates (0.0-1.0 scale)
- **Scraper weights**: Tiebreaker system favors preferred sources when LLM scores are similar (within 0.1)
  - LubimyCzytac: 3.0 (highest - most favored)
  - Audible: 2.0 (medium)
  - Goodreads: 1.5 (lowest)
- **Score transparency**: Displays all LLM scores and applied weights to user before confirmation
- **Heuristic fallback**: Title/author similarity using difflib if LLM unavailable
- Interactive CLI prompts showing book context
- Web interface shows rich side-by-side comparison

**Custom URL input** (feature in [search/auto_search.py](src/search/auto_search.py:298)):
- Users can provide custom URLs during auto-search candidate selection
- Supports both full URLs (`https://lubimyczytac.pl/ksiazka/...`) and partial URLs (`lubimyczytac.pl/ksiazka/...`)
- URLs are validated against `SCRAPER_REGISTRY` patterns before acceptance
- Dynamically supports all registered scrapers (Audible, Goodreads, LubimyCzytac)
- Downloads and validates the page before proceeding with scraping

**LLM Selection Details** (see [SCRAPER_WEIGHTS.md](SCRAPER_WEIGHTS.md)):
- Configured via `.env` file: `LLM_API_KEY`, `LLM_MODEL`, `OPENAI_BASE_URL`
- Supports OpenAI, Anthropic, local models (LM Studio, Ollama) via litellm
- Test connection with: `python BadaBoomBooks.py --llm-conn-test`
- Minimum acceptance threshold: 0.5 (50% confidence)
- Weight formula: `final_score = llm_score * (1.0 + (weight - 1.0) * 0.1)`
- Only applies to candidates within quality bracket (0.1 score difference)

**YOLO Mode** (`--yolo` flag):
- Auto-accepts all user prompts for fully automated batch processing
- Skips confirmation prompts (processing confirmation, LLM candidate selection)
- Skips all "Press enter to exit" prompts for unattended operation
- When used with `--llm-select`: Auto-accepts LLM's top candidate
- When used without `--llm-select`: Auto-selects first search result candidate
- Perfect for automated workflows, cron jobs, or large batch processing
- Example: `python BadaBoomBooks.py --auto-search --llm-select --yolo --opf --id3-tag -O "C:\Output" -R "C:\Input"`

## Configuration Files

- `queue.ini` - Processing queue (folder→URL mappings), auto-generated
- `template.opf` - OPF template for metadata files
- `debug.log` - Debug output when `--debug` flag is used
- `.cursorrules` - Not present (no cursor-specific rules)

## Important Notes

### File Operations

- **Series organization** (`--series`): Creates `Author/Series Name/Volume - Title/` structure
- **Standard organization**: Creates `Author/Title/` structure
- **File processors** support copy (`--copy`), move (`--move`), or in-place processing
- **Path sanitization**: All paths cleaned via `clean_path()` in [utils.py](src/utils.py) - removes invalid characters

### Metadata Processing

- **OPF files** use Calibre-style metadata format for Audiobookshelf compatibility
- **info.txt** files are formatted for SmartAudioBookPlayer app
- **ID3 tagging** uses mutagen library, supports MP3/M4A/M4B/FLAC/OGG/WMA
- **Cover images** downloaded from scraped `cover_url` field

### Web Interface Specifics

- Real-time updates via SocketIO (`socketio.emit()`)
- Jobs stored in `WebState.jobs` dictionary
- Candidate selection blocks job until user responds
- File browser implemented in Flask routes (`/api/browse`, `/api/list_drives`)

### Error Handling

- All processors return boolean success/failure
- `BookMetadata.mark_as_failed()` sets failure state
- `ProcessingResult` tracks successes/failures/skipped books
- Dry-run mode prevents all file system modifications

### Legacy Code

Original monolithic code preserved in `legacy/` folder. All new development uses modular architecture in `src/`.

## Testing

### Automated Tests

The project uses **pytest** for automated testing. Tests are located in `src/tests/`.

**Test Structure:**
```
src/tests/
├── __init__.py
├── conftest.py              # Shared fixtures (test data dirs, cleanup utilities)
├── test_file_operations.py  # Integration tests for copy/rename/organize
└── data/
    ├── existing/            # Static test data (committed to repo)
    │   └── [test audiobook folders with metadata.opf]
    └── expected/            # Output directory (cleaned before each test)
```

**Running Tests:**
```bash
# Run all tests
python -m pytest src/tests/ -v

# Run specific test file
python -m pytest src/tests/test_file_operations.py -v

# Run specific test
python -m pytest src/tests/test_file_operations.py::test_copy_rename_from_opf -v

# Run only integration tests
python -m pytest src/tests/ -v -m integration
```

**Available Tests:**
- `test_copy_rename_from_opf`: Tests `--copy --rename --from-opf` pipeline
  - Validates folder organization (Author/Title/ structure)
  - Verifies file renaming (01 - Title.mp3 format)
  - Checks UTF-8 encoding preservation in OPF files
  - Tests path sanitization with problematic characters
- `test_copy_rename_from_opf_with_series`: Tests series organization (`--series` flag)
  - Validates Author/Series/Volume - Title/ structure
- `test_copy_rename_from_opf_with_trailing_slashes`: Tests handling of trailing slashes in paths
  - Verifies paths ending with '/' are handled correctly
  - Same validation as base test but with trailing slashes on -O and -R arguments

**Test Data:**
- Static test data in `src/tests/data/existing/` includes:
  - Audiobook folder with problematic name: `[ignore] Book Title's - Author (Series)_`
  - UTF-8 encoded `metadata.opf` with Polish characters (ą, ę, ć, ł, ó, ń, ś, ź, ż)
  - Empty `.mp3` stub files for testing copy/rename operations

**Writing New Tests:**
1. Add test functions to appropriate `test_*.py` file in `src/tests/`
2. Use fixtures from `conftest.py` (`expected_dir`, `existing_dir`, `cleanup_queue_ini`)
3. Mark tests with appropriate markers: `@pytest.mark.integration`, `@pytest.mark.unit`, etc.
4. Always use `--yolo` flag when running app in tests to skip interactive prompts
5. Clean up any generated files (tests should be isolated and repeatable)

**Test-Driven Development (TDD):**
1. Write test first (define expected behavior)
2. Run test to see it fail
3. Implement feature to make test pass
4. Refactor if needed
5. Verify test still passes

### Manual Testing Recommendations

When making changes:
1. Test with `--dry-run` first to verify logic
2. Test both CLI and web interface if modifying core modules
3. Verify scraper changes by running with `--debug` and examining `debug.log`
4. For search changes, check `debug_pages/` folder for saved HTML
5. Test series organization separately from standard organization

## Windows Considerations

This codebase runs on Windows (working directory shows `C:\Users\rudy\...`):
- Use `Path` objects from pathlib for cross-platform compatibility
- File paths in CLI arguments may use backslashes
- Selenium requires Chrome/Chromium installed
- Some bash commands may need Windows equivalents (use `dir` instead of `ls`, etc.)
