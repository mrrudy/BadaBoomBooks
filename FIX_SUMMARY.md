# Fix Summary: Garbage ID3 Tag Detection and Folder Name Fallback

## Problem

When processing raw audiobook folders without OPF files, the application was using corrupted ID3 tags (e.g., "exsite.pl") for search, ignoring valuable folder name information. This led to completely wrong search results.

### Example

**Folder**: `Frankiewicz Janusz - Gorejące ognie` ✓ (correct book info)
**ID3 Tags**: All fields = `exsite.pl` ❌ (garbage data from torrent site)

**Before Fix**:
```
Searching audible.com for: exsite.pl by exsite.pl
Searching goodreads.com for: exsite.pl by exsite.pl
Searching lubimyczytac.pl for: exsite.pl by exsite.pl

Results: Wrong books about nature/Biebrza ❌
```

**After Fix**:
```
Searching audible.com for: Frankiewicz Janusz Gorejące ognie
Searching goodreads.com for: Frankiewicz Janusz Gorejące ognie
Searching lubimyczytac.pl for: Frankiewicz Janusz Gorejące ognie

Results: Correct book found! "Gorejące ognie - Janusz Frankiewicz" ✓
```

## Solution

### 1. Created Metadata Cleaning Module

**File**: `src/utils/metadata_cleaning.py`

**Key Features**:
- **Garbage Detection**: Identifies domains (*.pl, *.com), URLs (http://, www.), torrent markers, duplicate fields
- **Smart Cleaning**: Removes brackets, special characters that hurt search
- **Multi-Source Extraction**: Generates parallel search strategies from folder name + ID3 tags
- **Validation**: Checks for too-short strings, suspicious patterns

**Garbage Patterns Detected**:
```python
- Domain names: exsite.pl, audiobook.com, audioteka.pl
- URLs: https://, www.
- Common markers: audiobook, exsite, audioteka, empik, legimi, storytel
- Torrent markers: rarbg, yify, rip
- Duplicate title/author (e.g., "exsite.pl" == "exsite.pl")
- Empty/very short strings (< 3 chars)
```

### 2. Updated Metadata Extraction Logic

**Fixed in TWO places** (critical!):
- `src/main.py` - `_extract_book_info()` - For main thread
- `src/queue_manager.py` - `_extract_book_info_for_discovery()` - For worker threads ⚠ **This was the missing piece!**

**New Priority**:
```
1. OPF File (if exists) → TRUSTED completely, return immediately ✓
2. NO OPF:
   - Extract from BOTH ID3 tags and folder name
   - Validate both sources (detect garbage)
   - Store as separate sources with labels
   - Use folder name if ID3 is garbage ✓
3. Parent directory (if -R flag)
```

**Key Changes**:
- Added `opf_exists` flag to distinguish OPF vs. raw folder processing
- Added `sources` dict with both `folder` and `id3` metadata
- ID3 garbage detection with `garbage_detected` flag
- Intelligent fallback: prefer ID3 if valid, folder name if ID3 is garbage

### 3. Parallel Search Strategy

**File**: `src/search/auto_search.py`

**Updated**: `search_and_select_with_context()` to accept `search_alternatives` parameter

**Behavior**:
- When multiple alternatives provided, searches with ALL of them
- Tags candidates with their source (`id3` or `folder`)
- Combines results from all sources for LLM scoring

### 4. Enhanced LLM Prompts

**File**: `src/search/llm_scoring.py`

**New LLM Context**:
```
Primary search term: Frankiewicz Janusz Gorejące ognie

Book information (what we're looking for):
  Folder name: Frankiewicz Janusz - Gorejące ognie
    (cleaned: Frankiewicz Janusz Gorejące ognie)

  ⚠ WARNING: ID3 tags appear to contain garbage data (domains/URLs/duplicates):
    ID3 Title: exsite.pl [MAY BE UNRELIABLE]
    ID3 Author: exsite.pl [MAY BE UNRELIABLE]
  → RECOMMENDATION: Trust folder name over ID3 tags if they conflict

  Metadata source: folder name (cleaned)
```

**Updated Scoring Rules**:
```
IMPORTANT RULES:
- When ID3 tags are marked as garbage (⚠ WARNING), IGNORE them and use folder name instead
- Folder name is generally more reliable than corrupted ID3 tags
- If candidates are about completely different topics/genres, score them 0.0
- It is COMPLETELY ACCEPTABLE to score all candidates as 0.0 if none match
- When in doubt, score LOW - false negatives are better than false positives
```

### 5. Source Tracking

**File**: `src/models.py`

**Extended** `SearchCandidate` class:
```python
@dataclass
class SearchCandidate:
    ...
    search_source: str = "single"   # 'id3', 'folder', 'single'
    search_term_used: str = ""      # actual search term used
```

Enables future analytics and learning from which sources produce good results.

## Files Modified

### New Files
- `src/utils/metadata_cleaning.py` - Core cleaning and validation (380 lines)
- `test_metadata_cleaning.py` - Validation tests (all pass ✓)
- `METADATA_IMPROVEMENTS.md` - Detailed technical documentation
- `FIX_SUMMARY.md` - This document

### Modified Files
1. **`src/main.py`**:
   - `_extract_book_info()` (lines 510-622) - Multi-source extraction
   - `_auto_search_for_folder()` (lines 446-497) - Generate search alternatives

2. **`src/queue_manager.py`** ⚠ **Critical fix**:
   - `_extract_book_info_for_discovery()` (lines 989-1120) - Worker metadata extraction
   - `_discover_url_for_folder()` (lines 849-987) - Worker search term generation

3. **`src/search/auto_search.py`**:
   - `search_and_select_with_context()` (lines 62-129) - Handle parallel alternatives

4. **`src/search/llm_scoring.py`**:
   - `_build_batch_scoring_prompt()` (lines 206-353) - Enhanced LLM context
   - `_build_scoring_prompt()` (lines 155-203) - Enhanced single candidate scoring

5. **`src/models.py`**:
   - `SearchCandidate` (lines 178-190) - Added source tracking fields

## Test Results

### Unit Tests
```bash
python test_metadata_cleaning.py
```
**Results**: ✅ **All tests pass**
- Garbage detection: 8/8 ✓
- Duplicate detection: 4/4 ✓
- Folder cleaning: 3/3 ✓
- ID3 cleaning: 4/4 ✓
- Metadata extraction: 2/2 ✓
- Search alternatives: 2/2 ✓

### Integration Test (Real Failing Case)
```bash
python BadaBoomBooks.py \
  "T:/Sorted/Books/newAudio/Incoming/Frankiewicz Janusz - Gorejące ognie" \
  --from-opf --force-refresh --auto-search --llm-select \
  -O "T:/Sorted/Books/newAudio/Sorted" \
  --move --series --opf --rename --infotxt --cover \
  --workers 1 --interactive --dry-run
```

**Before**:
```
Searching for: exsite.pl by exsite.pl
Found: Łosie w kaczeńcach. O czym milczy Biebrza (WRONG!) ❌
```

**After**:
```
Searching for: Frankiewicz Janusz Gorejące ognie
Found: Gorejące ognie - Janusz Frankiewicz (CORRECT!) ✓
```

## Key Insights

### Why It Failed Initially

The application has **two separate code paths** for metadata extraction:
1. **Main thread** (`src/main.py`) - Used during legacy queue building
2. **Worker threads** (`src/queue_manager.py`) - Used during parallel processing ⚠

I initially only fixed the main thread code, but the application was using the worker code path! The worker extraction function `_extract_book_info_for_discovery()` was still using old logic without garbage detection.

### Critical Fix

The breakthrough was discovering and updating **BOTH** extraction functions:
- `src/main.py::_extract_book_info()`
- `src/queue_manager.py::_extract_book_info_for_discovery()` ✅ **This was the key!**

Both now use the same `metadata_cleaning.py` module for consistent behavior.

## Benefits

1. ✅ **Automatic Garbage Detection**: Identifies and ignores corrupted ID3 tags
2. ✅ **Smart Fallback**: Uses folder name when ID3 is unreliable
3. ✅ **Better Search**: Searches with cleaned, reliable data
4. ✅ **Informed LLM**: LLM receives full context with warnings
5. ✅ **Transparency**: User sees which source was used and why
6. ✅ **OPF Priority**: Trusted OPF files never overridden (your requirement)
7. ✅ **Multi-Source**: Can search with both ID3 and folder alternatives in parallel

## Usage

No changes to command-line usage required! The fix is automatic:

```bash
# Works with any existing command
python BadaBoomBooks.py --auto-search --llm-select --opf --id3-tag \
  -O "C:\Output" "C:\Input Folder"
```

**Behavior**:
- If folder has OPF → uses OPF (trusted)
- If no OPF but ID3 valid → uses ID3
- If no OPF and ID3 garbage → uses folder name ✓
- If both ID3 and folder valid → can use both for parallel search

## Future Enhancements

### 1. Garbage Pattern Collection (Not Yet Implemented)

**Concept**: Learn from manual corrections
```
When user manually selects correct candidate:
  - Input: "exsite.pl"
  - Correct: "Gorejące ognie" by "Janusz Frankiewicz"
  - Delta: Domain name → Polish novel
  - Save to: garbage_patterns.txt
  - Use for: Improved automatic detection
```

### 2. Integration Tests

Add tests with real audiobook folders to ensure:
- OPF priority is never violated
- Garbage detection works with various patterns
- Folder name fallback works correctly
- -R flag parent directory extraction still works

### 3. Fine-Tuning

Monitor LLM performance:
- Check if 0.5 threshold is appropriate
- Collect cases of correct/incorrect scoring
- Adjust scraper weights if needed

## Notes

- No changes to existing flags or behavior
- Backward compatible with all existing commands
- OPF files are still trusted completely (as required)
- The fix is transparent to users
- All tests pass
- **Real-world test case now works correctly! ✓**
