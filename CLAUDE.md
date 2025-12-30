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

# Force refresh - re-scrape metadata even if OPF exists
python BadaBoomBooks.py --from-opf --opf --force-refresh "C:\Audiobook Folder"

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

**No-Resume Mode** (`--no-resume` flag):
- Disables resume prompts and always starts fresh job
- Useful with `--yolo` for fully automated runs without user interaction
- Prevents accidentally resuming incomplete jobs in automated workflows
- When combined with `--yolo`: Completely unattended operation (no prompts at all)
- Example: `python BadaBoomBooks.py --auto-search --yolo --no-resume --opf --id3-tag -O "C:\Output" -R "C:\Input"`
- Note: Overrides `--resume` flag if both are specified

## Configuration Files

- `queue.ini` - Processing queue (folder→URL mappings), auto-generated
- `template.opf` - OPF template for metadata files
- `debug.log` - Debug output when `--debug` flag is used
- `.cursorrules` - Not present (no cursor-specific rules)

### Chrome Profile Configuration

The application can use your **real Chrome browser profile** to preserve DuckDuckGo region settings and other preferences for better search results.

**Configuration (.env file):**
```bash
CHROME_USE_REAL_PROFILE=true   # Default: try real profile with smart fallback
CHROME_PROFILE_PATH=           # Optional: override auto-detected path
```

**Smart Profile Selection Behavior:**
1. **Chrome closed:** Uses real profile directly → DuckDuckGo region preferences preserved
2. **Chrome open (profile locked):** Copies profile to temp directory (once/month max) → Uses copy with lock files removed → DuckDuckGo preferences still preserved
3. **Copy fails:** Falls back to temporary ephemeral profile → May show different search results
4. **Disabled:** Set `CHROME_USE_REAL_PROFILE=false` to always use temporary profile

**Profile Copy Details:**
- **Location:** System temp directory (`%TEMP%\badaboombooksprofile_chrome\` on Windows)
- **Refresh frequency:** Maximum once per 30 days (reuses existing copy if younger)
- **Lock files removed:** `SingletonLock`, `SingletonCookie`, `SingletonSocket`
- **Cleanup:** Temp directory can be deleted on system restart (acceptable)

**Security Implications:**
Using real profile gives automation access to:
- Cookies and logged-in sessions
- Browsing history and bookmarks
- ⚠️ Saved passwords (if Chrome extensions enabled)

**Recommendation:** This feature is designed for **local use only** (not remote/cloud deployments).

**Auto-detected Paths:**
- Windows: `%LOCALAPPDATA%\Google\Chrome\User Data`
- macOS: `~/Library/Application Support/Google/Chrome`
- Linux: `~/.config/google-chrome`

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
- **Force refresh** (`--force-refresh` flag): Re-scrapes metadata even when complete `metadata.opf` exists
  - Requires `<dc:source>` URL in existing OPF file
  - Uses OPF's title/author for context during scraping
  - Falls back to auto-search if no source URL found
  - Useful for fixing broken/incomplete metadata or updating to latest information

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

### Queue System and User Input Tracking

The application uses a **database-backed queue system** for parallel processing and user input tracking:

**Database:** `badaboombooksqueue.db` (SQLite, WAL mode)
- **Jobs table**: One row per processing request (CLI run or web job)
- **Tasks table**: One row per audiobook folder
- **Task statuses**: `pending`, `running`, `completed`, `failed`, `skipped`, `waiting_for_user`

**User Input Tracking:**

Tasks requiring user interaction are marked with `waiting_for_user` status and stored with:
- `user_input_type`: Type of input (`llm_confirmation`, `manual_selection`, `manual_url`)
- `user_input_prompt`: The exact prompt text
- `user_input_options`: JSON array of options/candidates
- `user_input_context`: JSON object with book info, scores, etc.

**Three types of user input:**
1. **LLM Confirmation** ([auto_search.py:290](src/search/auto_search.py#L290)): Confirm AI-selected candidate
   - Override: `--yolo` flag auto-accepts
2. **Manual Selection** ([auto_search.py:317](src/search/auto_search.py#L317)): Choose from multiple candidates
   - Override: `--yolo` picks first candidate
3. **Manual URL Entry** ([manual_search.py:234](src/search/manual_search.py#L234)): Enter URL manually
   - Override: None (manual mode always requires input)

**Interactive Mode (`--interactive` flag):**

The `--interactive` flag controls whether workers can handle tasks requiring user input:

- **Interactive Mode** (`--interactive`): Worker processes both `pending` and `waiting_for_user` tasks
  - Prompts user for input when needed (LLM confirmations, manual selections, manual URLs)
  - **Requirement**: Must use `--workers 1` (single worker only)
  - **Use case**: CLI with human operator present to respond to prompts

- **Daemon Mode** (default, no `--interactive`): Worker processes only `pending` tasks
  - Skips all `waiting_for_user` tasks automatically
  - **Best for**: Batch processing, multiple workers, automated/unattended runs
  - **Use case**: Server deployments, cron jobs, parallel processing

**Auto-detection behavior:**
- If `--workers > 1`: Interactive mode is **automatically disabled** (forced to daemon mode)
  - Prevents multiple workers from fighting for user input (mixed prompts)
  - Warning displayed if user explicitly requests `--interactive` with multiple workers
- If `--workers 1`: Interactive mode respects `--interactive` flag (default: daemon)

**Examples:**
```bash
# Daemon mode (default) - skip user input tasks
python BadaBoomBooks.py --auto-search --opf --id3-tag -O "C:\Output" -R "C:\Input"

# Interactive mode - single worker handles user prompts
python BadaBoomBooks.py --interactive --workers 1 --auto-search --opf -O "C:\Output" -R "C:\Input"

# Multiple workers - daemon mode (interactive auto-disabled)
python BadaBoomBooks.py --workers 4 --auto-search --opf -O "C:\Output" -R "C:\Input"

# Error: Cannot use interactive with multiple workers
python BadaBoomBooks.py --interactive --workers 4 --auto-search --opf -O "C:\Output" -R "C:\Input"
# Output: ❌ Cannot use --interactive with multiple workers
```

**Worker Types (legacy terminology):**
- **Non-interactive workers** (`--yolo` or daemon mode): Filter for `status=['pending']` only
- **Interactive workers** (CLI with `--interactive` flag, web): Handle both `pending` and `waiting_for_user`

**Key APIs** ([queue_manager.py](src/queue_manager.py)):
```python
# Mark task waiting for user input
queue_manager.set_task_waiting_for_user(
    task_id=task_id,
    input_type='manual_selection',
    prompt='Select [1-3]:',
    options=[...],
    context={...}
)

# Get tasks waiting for user input
waiting = queue_manager.get_tasks_waiting_for_user(job_id=job_id)

# Resume after user responds
queue_manager.resume_task_from_user_input(
    task_id=task_id,
    user_response='https://...'
)
```

**Documentation:**
- Full guide: [USER_INPUT_TASKS.md](USER_INPUT_TASKS.md)
- Quick reference: [TASK_TYPES_QUICK_REF.md](TASK_TYPES_QUICK_REF.md)

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
- `test_copy_rename_from_opf_with_windows_paths`: Tests Windows-style absolute paths
  - Verifies handling of absolute paths with drive letters (C:\...)
  - Tests backslashes as path separators with trailing backslash
  - Critical for Windows users copying paths from File Explorer
- `test_copy_rename_from_opf_with_mixed_path_separators`: Tests edge cases with multiple trailing backslashes
  - Verifies handling of double/multiple trailing backslashes (path\\)
  - Tests path normalization when users manually construct or concatenate paths
  - Handles edge cases from manual path entry or script-generated paths

**Test Data:**
- Static test data in `src/tests/data/existing/` includes:
  - Audiobook folder with problematic name: `[ignore] Book Title's - Author (Series)_`
  - UTF-8 encoded `metadata.opf` with Polish characters (ą, ę, ć, ł, ó, ń, ś, ź, ż)
  - Empty `.mp3` stub files for testing copy/rename operations

**Database Isolation:**
Tests use isolated databases to prevent interference with production operations:
- Environment variable `BADABOOMBOOKS_DB_PATH` overrides database location for tests
- Each test gets a temporary database in pytest's `tmp_path`
- Production database (`badaboombooksqueue.db`) is NEVER touched by tests
- Tests can run while production operations are ongoing without conflicts
- Database fixture (`test_database`) is automatically included in all integration tests

**Writing New Tests:**
1. Add test functions to appropriate `test_*.py` file in `src/tests/`
2. Use fixtures from `conftest.py` (`expected_dir`, `existing_dir`, `cleanup_queue_ini`, `test_database`)
3. Mark tests with appropriate markers: `@pytest.mark.integration`, `@pytest.mark.unit`, etc.
4. Always use `--yolo` flag when running app in tests to skip interactive prompts
5. Include `test_database` fixture in test parameters to enable database isolation
6. Clean up any generated files (tests should be isolated and repeatable)

**Test-Driven Development (TDD):**
1. Write test first (define expected behavior)
2. Run test to see it fail
3. Implement feature to make test pass
4. Refactor if needed
5. Verify test still passes

### Scraper Regression Testing

The project includes comprehensive scraper regression tests that compare live-scraped metadata against reference OPF files to distinguish between scraper failures and legitimate service updates.

**Test Structure:**
```
src/tests/
├── utils/
│   ├── metadata_comparison.py   # Comparison logic
│   └── diff_reporter.py         # Human-readable diff reports
├── test_scrapers.py             # Scraper regression tests
└── data/
    └── scrapers/                # Test samples by service
        ├── lubimyczytac/
        │   ├── martha-wells-1-2/metadata.opf
        │   ├── martha-wells-3-4/metadata.opf
        │   └── martha-wells-5/metadata.opf
        ├── audible/
        └── goodreads/
```

**Running Scraper Tests:**
```bash
# Quick smoke test (one random sample per service)
python -m pytest src/tests/ -v

# Full regression for specific service (all samples)
python -m pytest src/tests/test_scrapers.py::test_scraper_regression_all_samples[lubimyczytac] -v -s
python -m pytest src/tests/test_scrapers.py::test_scraper_regression_all_samples[goodreads] -v -s
python -m pytest src/tests/test_scrapers.py::test_scraper_regression_all_samples[audible] -v -s

# Full regression for all services (all samples)
python -m pytest src/tests/test_scrapers.py::test_scraper_regression_all_samples -v -s

# Test specific service with random sample
python -m pytest src/tests/test_scrapers.py::test_scraper_regression_random_sample[goodreads] -v

# Skip network tests (for offline development)
python -m pytest src/tests/ -v -m "not requires_network"

# Run only scraper tests
python -m pytest src/tests/ -v -m scraper
```

**Understanding Test Results:**

Tests compare scraped metadata against reference OPF files using field-by-field comparison:

| Status | Meaning | Action |
|--------|---------|--------|
| **PASS (Perfect Match)** | All fields match | ✓ Scraper working perfectly |
| **PASS (Minor Changes)** | Non-critical fields differ | ✓ Expected variation, review if concerned |
| **PASS (Major Changes)** | Summary/genres updated | ⚠ Service updated content, verify legitimacy |
| **FAIL (Critical Fields)** | Title/author missing/wrong | ✗ Scraper broken, fix immediately |

**Field Severity Levels:**
- **CRITICAL** (test fails): `title`, `author`, `url` - must match exactly
- **MAJOR** (test passes with warning): `series`, `volumenumber`, `summary`, `genres`, `language`, `isbn`
- **MINOR** (test passes): `subtitle`, `narrator`, `publisher`, `publishyear`
- **DYNAMIC** (allowed to change): `cover_url`

**Adding Test Samples:**

To add new test samples from your production library:

1. Process an audiobook with the app (ensure `<dc:source>` is populated)
2. Copy `metadata.opf` to test directory:
```bash
# Example for any service (LubimyCzytac, Goodreads, Audible)
mkdir -p "src/tests/data/scrapers/SERVICE_NAME/author-title-identifier"
cp "T:\Sorted\Books\newAudio\Sorted\Author\Series\Volume\metadata.opf" \
   "src/tests/data/scrapers/SERVICE_NAME/author-title-identifier/metadata.opf"

# Specific examples:
mkdir -p "src/tests/data/scrapers/goodreads/domagalski-relikt"
mkdir -p "src/tests/data/scrapers/audible/sanderson-mistborn"
mkdir -p "src/tests/data/scrapers/lubimyczytac/sapkowski-wiedzmin"
```
3. Verify `<dc:source>` contains URL: `grep dc:source metadata.opf`
4. Commit to repository

**TDD Workflow for Scrapers:**

Developing or fixing a scraper:

1. **Create test case:**
```bash
mkdir -p src/tests/data/scrapers/tdd/my-test
# Create metadata.opf with expected values + source URL
```

2. **Run test:**
```bash
python -m pytest src/tests/test_scrapers.py::test_manual_tdd_sample -v -s
```

3. **Fix scraper** based on diff report
4. **Iterate** until test passes

**Interpreting Diff Reports:**

Example report:
```
SCRAPER REGRESSION TEST: lubimyczytac
URL: https://lubimyczytac.pl/ksiazka/5068091/...
Status: PASS (Major Changes Detected)
Overall Similarity: 94.2%

CRITICAL FIELDS: ✓ PASS
  ✓ title: "Wszystkie wskaźniki czerwone. Sztuczny stan"
  ✓ author: "Martha Wells"

MAJOR FIELDS: ⚠ CHANGES (1)
  ⚠ summary: CHANGED (length: 1234 → 1289 chars) (similarity: 92.3%)
    [Use -s for full diff]

INTERPRETATION:
✓ Scraper is working correctly
⚠ Summary content updated on service (possibly legitimate)
→ Review changes to verify they are expected
```

**What to do:**
- ✓ **Green status**: Scraper working, no action needed
- ⚠ **Yellow warnings**: Review changes, update reference OPF if legitimate
- ✗ **Red failures**: Fix scraper selectors, check `debug_pages/` for HTML

**Updating Reference Data:**

When service legitimately updates metadata:
1. Verify changes on live website
2. If legitimate, update reference OPF file:
```bash
# Re-process book to get fresh metadata
python BadaBoomBooks.py --from-opf --opf -R "T:\path\to\book"
# Copy new OPF to test directory
cp "T:\path\to\book\metadata.opf" "src/tests/data/scrapers/SERVICE/sample-name/"
```

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

### Important: Trailing Backslash Issue with Spaces in Paths

**Known Issue:** When using PowerShell or CMD, paths with spaces AND trailing backslashes can cause problems:

```powershell
# ❌ FAILS in PowerShell/CMD (trailing \ escapes the closing quote)
python .\BadaBoomBooks.py -R 'C:\path with space\'

# ✅ WORKS - Remove trailing backslash
python .\BadaBoomBooks.py -R 'C:\path with space'

# ✅ WORKS - Use double backslash
python .\BadaBoomBooks.py -R 'C:\path with space\\'

# ✅ WORKS - Use double quotes
python .\BadaBoomBooks.py -R "C:\path with space\"
```

**Why this happens:**
- In PowerShell/CMD, a trailing backslash before a closing quote escapes the quote
- The Python application itself handles these paths correctly
- This is a shell-level issue, not an application bug

**Solution:** Always remove trailing backslashes from paths with spaces, or use double quotes.
