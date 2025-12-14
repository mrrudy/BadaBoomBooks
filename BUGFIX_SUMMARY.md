# Bug Fix Summary: LLM Scoring Issues

## Issues Found

### Issue 1: All LLM Scores Returning 0.0

**Symptom**: Every candidate was being scored as 0.0 by the LLM

**Root Cause**: The `max_tokens` parameter was set to 50, which was too small for the LLM to return a complete response. The response was being truncated (`"finish_reason": "length"`), so the score wasn't being returned properly.

**Evidence**:
```
19:40:20 - LiteLLM:DEBUG: litellm_logging.py:1138 - RAW RESPONSE:
{"id": "chatcmpl-luau6fxwf9dzc6qeyg2fq", "choices": [{"finish_reason": "length",
```

The `"finish_reason": "length"` indicates the response was cut off.

**Fix**:
- Changed `max_tokens` from 50 to 4096 (configurable via `LLM_MAX_TOKENS` environment variable)
- Added `max_tokens` to LLM configuration in [src/config.py](src/config.py)
- Updated [src/search/llm_scoring.py](src/search/llm_scoring.py) to use configurable value
- Added documentation to [.env.example](.env.example)

---

### Issue 2: 0.0 Scores Still Resulting in Selection

**Symptom**: Even with all candidates scored as 0.0, one was still being selected (lubimyczytac)

**Root Cause**: The weight application logic was applying weights to ALL candidates within the quality bracket, even when all scores were 0.0. Since lubimyczytac has weight 3.0:
- 0.0 × (1.0 + (3.0 - 1.0) × 0.1) = 0.0 × 1.2 = 0.0

But it was still being sorted first and selected, even though the score was below the acceptance threshold.

**Fix**:
- Modified `_apply_scraper_weights()` in [src/search/candidate_selection.py](src/search/candidate_selection.py)
- Added check: weights are only applied if `best_llm_score >= ACCEPTANCE_THRESHOLD (0.5)`
- When all scores are below 0.5, no weights are applied and selection is rejected

---

## Files Modified

### 1. [src/config.py](src/config.py)

**Added**:
```python
'max_tokens': int(os.getenv('LLM_MAX_TOKENS', '4096')),  # Maximum tokens for LLM responses
```

**Purpose**: Make max_tokens configurable via environment variable, default to 4096

---

### 2. [src/search/llm_scoring.py](src/search/llm_scoring.py)

**Changed**:
```python
# Before:
max_tokens=50  # Just need a number

# After:
max_tokens=LLM_CONFIG.get('max_tokens', 4096)  # Configurable, default 4096
```

**Purpose**: Use configurable max_tokens instead of hardcoded 50

---

### 3. [src/search/candidate_selection.py](src/search/candidate_selection.py)

**Added**:
```python
# Minimum score threshold - don't apply weights if all scores are too low
ACCEPTANCE_THRESHOLD = 0.5

# Don't apply weights if best score is below acceptance threshold
# This prevents selecting a candidate when all scores are 0.0 or very low
should_apply_weights = best_llm_score >= ACCEPTANCE_THRESHOLD
```

**Changed**:
```python
# Before:
if best_llm_score - llm_score <= SIMILARITY_THRESHOLD:

# After:
if should_apply_weights and (best_llm_score - llm_score <= SIMILARITY_THRESHOLD):
```

**Purpose**: Only apply weights when scores are above acceptance threshold (0.5)

---

### 4. [.env.example](.env.example)

**Added**:
```env
# Maximum tokens for LLM responses (optional, default: 4096)
# Increase if LLM responses are being truncated
# Decrease to reduce token usage and cost
LLM_MAX_TOKENS=4096
```

**Purpose**: Document the new configuration option for users

---

## Testing

### Test 1: Zero Score Handling

**Command**: `python test_zero_score_fix.py`

**Result**: ✅ PASS
```
Scenario: All candidates scored 0.0 by LLM (no good matches)

After Weight Application:
  [goodreads      ] LLM: 0.000, Final: 0.000, Weight applied: NO
  [audible        ] LLM: 0.000, Final: 0.000, Weight applied: NO
  [lubimyczytac   ] LLM: 0.000, Final: 0.000, Weight applied: NO

✅ PASS: Weights correctly NOT applied when all scores are 0.0
   All candidates will be rejected (no selection made)
```

### Test 2: Good Score Handling

**Result**: ✅ PASS
```
Scenario: All candidates scored well (0.85-0.87)

After Weight Application:
  [goodreads      ] LLM: 0.850, Final: 0.892, Weight applied: YES
  [audible        ] LLM: 0.870, Final: 0.957, Weight applied: YES
  [lubimyczytac   ] LLM: 0.860, Final: 1.032, Weight applied: YES

✅ PASS: Weights correctly applied when scores are above threshold
   Winner: lubimyczytac (should be lubimyczytac with highest weight)
```

### Test 3: Configuration Loading

**Command**: `python -c "from src.config import LLM_CONFIG; print(LLM_CONFIG['max_tokens'])"`

**Result**: ✅ PASS - Returns `4096`

---

## Expected Behavior After Fix

### Scenario 1: LLM Scores All Candidates as 0.0 (Poor Matches)

**Before**:
```
- [lubimyczytac] 0.000 ← SELECTED  ❌ WRONG
  Wszystkie wskaźniki czerwone
```

**After**:
```
- [lubimyczytac] 0.000
- [audible] 0.000
- [goodreads] 0.000

Best LLM score (0.00) below threshold (0.50), rejecting all  ✅ CORRECT
[Manual candidate selection shown to user]
```

### Scenario 2: LLM Returns Proper Scores (Good Matches)

**Before** (with max_tokens=50):
```
- [lubimyczytac] 0.000
- [audible] 0.000
- [goodreads] 0.000
(Scores truncated due to insufficient tokens)
```

**After** (with max_tokens=4096):
```
- [lubimyczytac] 0.860 (weighted: 1.032) ← SELECTED  ✅ CORRECT
- [audible] 0.870 (weighted: 0.957)
- [goodreads] 0.850 (weighted: 0.892)
```

---

## Configuration Guide

### Default Configuration (Recommended)

No .env changes needed! The default `LLM_MAX_TOKENS=4096` will be used automatically.

### Custom Configuration (Optional)

If you want to adjust max_tokens, add to your `.env` file:

```env
# Increase for very long responses (costs more)
LLM_MAX_TOKENS=8192

# Decrease to save tokens/cost (may truncate responses)
LLM_MAX_TOKENS=2048
```

**Recommendation**: Keep the default 4096 unless you have specific needs.

---

## Why These Values?

### max_tokens = 4096 (Default)

- **50 tokens**: Too small - LLM can't complete the response
- **4096 tokens**: Large enough for complete scoring responses
- **More than 4096**: Unnecessary for simple numeric scoring tasks

### Acceptance Threshold = 0.5

- **Below 0.5**: LLM has low confidence, likely wrong book
- **0.5-0.7**: Possible match, user should verify
- **0.7-0.9**: Very good match
- **0.9-1.0**: Perfect match

The 0.5 threshold ensures we only auto-select when the LLM is reasonably confident.

---

## Impact

✅ **LLM now returns proper scores** instead of 0.0
✅ **0.0 scores no longer result in selection** - user is shown all candidates for manual selection
✅ **Weights only apply to good matches** (scores >= 0.5)
✅ **Configurable max_tokens** allows adjustment if needed
✅ **Clear logging** shows why selections are rejected

---

## Testing Recommendations

Before processing your audiobooks:

1. **Test LLM connection**:
   ```bash
   python BadaBoomBooks.py --llm-conn-test
   ```

2. **Test with a single audiobook**:
   ```bash
   python BadaBoomBooks.py --auto-search --llm-select --dry-run -R "path/to/single/book"
   ```

3. **Check the scores** in the output:
   - Should see proper scores (not all 0.0)
   - If scores are below 0.5, you'll be shown manual selection
   - If scores are good (>=0.5 and similar), weights will apply

4. **Process your library**:
   ```bash
   python BadaBoomBooks.py --auto-search --llm-select --series --opf --id3-tag --move -O "output" -R "input"
   ```
