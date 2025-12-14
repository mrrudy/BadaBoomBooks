# Implementation Summary: Scraper Weights and LLM Score Display

## What Was Implemented

### 1. Scraper Weight System

**File**: [src/config.py](src/config.py#L58-L88)

Added `weight` parameter to each scraper in `SCRAPER_REGISTRY`:

```python
SCRAPER_REGISTRY = {
    "audible": {
        # ... existing config ...
        "weight": 2.0  # Medium priority
    },
    "goodreads": {
        # ... existing config ...
        "weight": 1.5  # Lower priority
    },
    "lubimyczytac": {
        # ... existing config ...
        "weight": 3.0  # HIGHEST priority (most favored)
    }
}
```

**Purpose**: Provides configurable preference for scrapers when LLM scores are similar.

---

### 2. Weight Application Logic

**File**: [src/search/candidate_selection.py](src/search/candidate_selection.py#L100-L141)

Added `_apply_scraper_weights()` method:

```python
def _apply_scraper_weights(self, scored_candidates: List[tuple]) -> List[tuple]:
    """
    Apply scraper weights as tiebreaker for similar LLM scores.

    Quality bracket threshold: 0.1
    Formula: final_score = llm_score * (1.0 + (weight - 1.0) * 0.1)
    """
    # Implementation details in file
```

**Key Features**:
- Only applies to candidates within **0.1 quality bracket** of the best score
- Uses multiplicative boost to preserve LLM score primacy
- LubimyCzytac gets 20% boost, Audible 10%, Goodreads 5%
- Returns `(candidate, llm_score, final_score)` tuples for transparency

---

### 3. Score Storage and Display

**File**: [src/search/candidate_selection.py](src/search/candidate_selection.py#L17-L24)

Added score tracking:

```python
def __init__(self, enable_ai_selection: bool = False):
    self.enable_ai_selection = enable_ai_selection
    self.llm_scorer = None
    self.last_scored_candidates = []  # NEW: Store for display
    # ...
```

**File**: [src/search/candidate_selection.py](src/search/candidate_selection.py#L77-L97)

Updated `_ai_select_candidate()` to store scores:

```python
# Apply weights as tiebreaker for similar scores
scored_with_weights = self._apply_scraper_weights(scored_candidates)

# Sort by weighted score (highest first)
scored_with_weights.sort(key=lambda x: x[2], reverse=True)

# Store scores for later display
self.last_scored_candidates = scored_with_weights
```

---

### 4. User Interface Updates

**File**: [src/search/auto_search.py](src/search/auto_search.py#L269-L281)

Enhanced AI selection display:

```python
# Display LLM scores for all candidates
if hasattr(self.candidate_selector, 'last_scored_candidates') and self.candidate_selector.last_scored_candidates:
    print("\n   LLM Scores for all candidates:")
    for candidate, llm_score, final_score in self.candidate_selector.last_scored_candidates:
        is_selected = (candidate == ai_selected)
        marker = safe_encode_text(" ← SELECTED") if is_selected else ""
        weight_info = ""
        if abs(llm_score - final_score) > 0.001:  # Weight was applied
            weight_info = f" (weighted: {final_score:.3f})"
        print(f"   - [{candidate.site_key}] {llm_score:.3f}{weight_info}{marker}")
        if is_selected:
            print(f"     {candidate.title}")
```

**Output Example**:
```
[AI] LLM Auto-selected: Wszystkie systemy w normie (Murderbot Diaries #1)
   URL: https://lubimyczytac.pl/ksiazka/4896752/wszystkie-systemy-w-normie
   Site: lubimyczytac

   LLM Scores for all candidates:
   - [lubimyczytac] 0.860 (weighted: 1.032) ← SELECTED
     Wszystkie systemy w normie (Murderbot Diaries #1)
   - [audible] 0.870 (weighted: 0.957)
   - [goodreads] 0.850 (weighted: 0.892)

Accept this selection? [Y/n]:
```

---

## Files Modified

| File | Changes |
|------|---------|
| [src/config.py](src/config.py) | Added `weight` field to all scrapers in `SCRAPER_REGISTRY` |
| [src/search/candidate_selection.py](src/search/candidate_selection.py) | Added weight logic, score storage, tiebreaker algorithm |
| [src/search/auto_search.py](src/search/auto_search.py) | Enhanced AI selection display with score breakdown |

## Files Created

| File | Purpose |
|------|---------|
| [test_weights.py](test_weights.py) | Quick test to verify weight configuration |
| [test_scoring_demo.py](test_scoring_demo.py) | Detailed demonstration of weight application |
| [SCRAPER_WEIGHTS.md](SCRAPER_WEIGHTS.md) | Comprehensive documentation of the system |
| [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) | This file |

## Documentation Updated

- [CLAUDE.md](CLAUDE.md#L125-L157): Added LLM selection and weight system details

---

## How It Works (Summary)

1. **LLM Scores Candidates**: Each candidate gets scored 0.0-1.0 based on relevance
2. **Identify Quality Bracket**: Find all candidates within 0.1 of best score
3. **Apply Weights**: Multiply scores by weight-based boost factor
4. **Select Winner**: Highest final score wins
5. **Display to User**: Show all scores (LLM + weighted) with clear markers
6. **User Confirms**: Accept or reject AI selection

---

## Configuration

### Changing Weights

Edit [src/config.py](src/config.py):

```python
"lubimyczytac": {
    # ...
    "weight": 3.0  # Change this value (1.0 - 5.0 recommended)
}
```

### Changing Quality Bracket

Edit [src/search/candidate_selection.py](src/search/candidate_selection.py):

```python
def _apply_scraper_weights(self, scored_candidates: List[tuple]) -> List[tuple]:
    # Quality bracket threshold - scores within this range are considered "similar"
    SIMILARITY_THRESHOLD = 0.1  # Change this value
```

### Changing Weight Impact

Edit the formula in [src/search/candidate_selection.py](src/search/candidate_selection.py):

```python
# Current: final_score = llm_score * (1.0 + (weight - 1.0) * 0.1)
# For stronger impact, increase the 0.1 multiplier:
final_score = llm_score * (1.0 + (weight - 1.0) * 0.2)  # Doubles the impact
```

---

## Testing

### Verify Weight Configuration
```bash
python test_weights.py
```

### See Demonstration
```bash
python test_scoring_demo.py
```

### Test with Real Data
```bash
python BadaBoomBooks.py --auto-search --llm-select --dry-run -R "path/to/test/audiobook"
```

---

## Benefits

✅ **Intelligent Selection**: LLM understands semantic meaning, not just keyword matching
✅ **Preferred Sources**: LubimyCzytac favored for better Polish metadata
✅ **Transparency**: User sees all scores and understands why selection was made
✅ **Configurability**: Easy to adjust weights or quality bracket threshold
✅ **Fallback Safety**: Only applies to similar scores; clear winners still win
✅ **User Control**: Always prompts for confirmation before proceeding

---

## Example Scenario

**Searching for**: "Murderbot Diaries All Systems Red"

**LLM Scores**:
- Goodreads: 0.85 (good match, but basic metadata)
- Audible: 0.87 (very good match, great narrator info)
- LubimyCzytac: 0.86 (very good match, Polish edition with series info)

**Without Weights**: Audible wins (highest score: 0.87)

**With Weights**: LubimyCzytac wins!
- Goodreads: 0.85 → 0.892 (weight 1.5)
- Audible: 0.87 → 0.957 (weight 2.0)
- **LubimyCzytac: 0.86 → 1.032 (weight 3.0)** ✨

**Why This Matters**: LubimyCzytac provides superior metadata for Polish audiobooks, including:
- Proper Polish character encoding
- Better series/volume information
- More complete narrator credits
- Higher quality cover images

The weight system ensures we get the best source even when all options look equally good to the AI.
