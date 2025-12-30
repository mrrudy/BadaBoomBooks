# Search Term Cleaning Improvements

## Problem

When processing audiobooks without an OPF file, the application was generating search terms from both ID3 tags and folder names. This caused issues:

1. **Garbage ID3 data**: Track numbers like "1. I" or "2. A" were being used as titles, resulting in useless searches
2. **Redundant searches**: When ID3 data contained information already in the folder name (e.g., author name), duplicate searches were performed

### Example Before Fix

```
Searching audible.com for: 1. I by Karin Slaughter
  No matching results found for audible

Searching audible.com for: Slaughter Karin Moje sliczne czyta Filip Kosior 224kbps
  No matching results found for audible

Searching goodreads.com for: 1. I by Karin Slaughter
  No matching results found for goodreads

Searching goodreads.com for: Slaughter Karin Moje sliczne czyta Filip Kosior 224kbps
  [1] Moje śliczne by Karin Slaughter | Goodreads
      ...

Searching lubimyczytac.pl for: 1. I by Karin Slaughter
  [1] Moje śliczne - Karin Slaughter | Książka w Lubimyczytac.pl
      ...

Searching lubimyczytac.pl for: Slaughter Karin Moje sliczne czyta Filip Kosior 224kbps
  [1] Moje śliczne - Karin Slaughter | Książka w Lubimyczytac.pl
      ...
```

**Total: 6 searches** (2 per site, one with garbage, one with folder name)

## Solution

Added two improvements to [src/utils/metadata_cleaning.py](src/utils/metadata_cleaning.py):

### 1. Better Garbage Detection for ID3 Fields

Enhanced `clean_id3_field()` to reject fields where the actual text content is too short after removing numbers and special characters:

```python
# Additional validation: check if meaningful content remains
# after removing numbers and special characters
# This catches cases like "1. I" or "2. A" where the actual text is too short
alphanumeric_only = re.sub(r'[^a-zA-Z]', '', result)
if len(alphanumeric_only) < 3:
    return ""
```

**Examples:**
- `"1. I"` → rejected (only 1 letter)
- `"2. A"` → rejected (only 1 letter)
- `"3. The"` → accepted (3 letters, edge case)
- `"1. Title"` → accepted (5 letters)
- `"Karin Slaughter"` → accepted

### 2. Search Term Deduplication

Added `_is_redundant_search()` function to detect when one search term is mostly contained in another:

```python
def _is_redundant_search(term1: str, term2: str, threshold: float = 0.8) -> bool:
    """
    Check if two search terms are redundant (one contains most of the other's content).
    """
    # Normalize both terms (remove case, filler words, special chars)
    # Compare word sets
    # If 80%+ of smaller set's words are in larger set → redundant
```

**Features:**
- Unicode normalization (ś → s) for accurate comparison
- Removes filler words: "by", "czyta", "reads", "narrated", "audiobook", "kbps", "mp3"
- Word-based comparison (not substring) to handle word order differences
- 80% similarity threshold for redundancy detection

**Examples:**
- `"Karin Slaughter"` vs `"Slaughter Karin - Moje sliczne czyta Filip Kosior 224kbps"` → redundant
- `"Moje śliczne by Karin Slaughter"` vs `"Slaughter Karin - Moje sliczne czyta Filip Kosior"` → redundant
- `"Book Title"` vs `"Different Author"` → not redundant

### 3. Updated Search Alternative Generation

Modified `generate_search_alternatives()` to use deduplication:

```python
# Check if folder search would be redundant
is_redundant = False
if alternatives:
    for existing in alternatives:
        if _is_redundant_search(folder_alternative['term'], existing['term']):
            is_redundant = True
            break

if not is_redundant:
    alternatives.append(folder_alternative)
```

## Results

### Example After Fix

```
Searching audible.com for: Slaughter Karin Moje sliczne czyta Filip Kosior 224kbps
  No matching results found for audible

Searching goodreads.com for: Slaughter Karin Moje sliczne czyta Filip Kosior 224kbps
  [1] Moje śliczne by Karin Slaughter | Goodreads
      ...

Searching lubimyczytac.pl for: Slaughter Karin Moje sliczne czyta Filip Kosior 224kbps
  [1] Moje śliczne - Karin Slaughter | Książka w Lubimyczytac.pl
      ...
```

**Total: 3 searches** (1 per site, garbage eliminated, no redundant searches)

### Performance Improvement

- **50% reduction** in search queries when ID3 data is garbage
- **Up to 50% reduction** when ID3 and folder contain overlapping information
- Faster processing, less network traffic, better user experience

## Testing

Test suite added: [test_search_cleaning.py](test_search_cleaning.py)

```bash
python test_search_cleaning.py
```

**Test coverage:**
- ✓ Garbage detection for short titles (1. I, 2. A)
- ✓ Valid title acceptance (legitimate short titles like "The")
- ✓ Redundancy detection with Unicode support
- ✓ Metadata extraction from multiple sources
- ✓ Search alternative generation with deduplication

All tests pass ✓

## Files Modified

1. [src/utils/metadata_cleaning.py](src/utils/metadata_cleaning.py)
   - Enhanced `clean_id3_field()` with minimum length validation
   - Added `_normalize_for_comparison()` for Unicode-aware text normalization
   - Added `_is_redundant_search()` for deduplication logic
   - Updated `generate_search_alternatives()` to use deduplication

## Backward Compatibility

- ✓ No breaking changes
- ✓ Existing functionality preserved
- ✓ Only affects search term generation when no OPF exists
- ✓ OPF-based workflows unchanged

## Future Improvements

Potential enhancements:
- Add more filler words to removal list based on usage patterns
- Adjust similarity threshold based on user feedback
- Add logging to show when searches are deduplicated (with `--debug` flag)
