# Batch Scoring Implementation

## Overview

The LLM scoring system has been redesigned to use **batch scoring** instead of scoring each candidate individually. This provides better context and more accurate comparisons.

## Key Changes

### Before: Individual Scoring
```
For each candidate:
  - Send separate prompt to LLM
  - Get individual score (0.0-1.0)
  - No comparison context
  - Temperature: 0.1 (very deterministic)
```

**Problems**:
- LLM couldn't compare candidates to each other
- Each prompt lacked full context
- Required multiple API calls
- More expensive and slower

### After: Batch Scoring
```
Send ONE prompt with ALL candidates:
  - LLM sees full context
  - Can compare candidates directly
  - Makes informed relative judgments
  - Temperature: 0.3 (allows reasoning)
  - Single API call per book
```

**Benefits**:
- ✅ Better decision making with full context
- ✅ Faster (single API call vs multiple)
- ✅ Cheaper (fewer tokens overall)
- ✅ More accurate comparisons

---

## Scoring Criteria (Priority Order)

### 1. PERFECT MATCH (1.0)
- **EXACT title** match in same language
- Same author
- Same narrator (if known)
- **CRITICAL**: Must be EXACT book, not just same series

**Example**:
```
Looking for: Wszystkie systemy w normie (Polish, Volume 1)
Found: Wszystkie systemy w normie (Pamiętniki Mordbota #1)
Score: 1.0 ✓
```

### 2. VERY GOOD MATCH (0.7-0.9)
- Very similar title (minor subtitle differences)
- Same author
- **Language matches**

**Example**:
```
Looking for: All Systems Red: The Murderbot Diaries
Found: All Systems Red (Murderbot Diaries Book 1)
Score: 0.85
```

### 3. POSSIBLE MATCH (0.4-0.6)
- Similar title but uncertain
- Same author but different edition/format

**Example**:
```
Looking for: All Systems Red (English)
Found: All Systems Red - Unabridged Audiobook
Score: 0.6 (uncertain about exact match)
```

### 4. POOR MATCH (0.0-0.3)
- **Wrong book from same series** (critical!)
- Wrong language
- Different book by same author
- Completely unrelated

**Example**:
```
Looking for: All Systems Red (Volume 1)
Found: Artificial Condition (Volume 2)
Score: 0.0 ❌ (same series, WRONG volume)
```

---

## Important Rules

### Rule 1: Same Series ≠ Match
Being "part of the same series" is **NOT a match** if it's a different volume.

```
❌ WRONG:
Looking for: Murderbot Diaries #1
Found: Murderbot Diaries #2
Score: 0.8  (INCORRECT - different book!)

✓ CORRECT:
Looking for: Murderbot Diaries #1
Found: Murderbot Diaries #2
Score: 0.0  (Correct - wrong volume)
```

### Rule 2: Language is Critical
Same language is a **strong positive indicator**.

```
Looking for: Polish audiobook
Found (Polish edition): Score boost +0.3
Found (English edition): Score penalty -0.5
```

### Rule 3: Exact Title Wins
Exact title match in correct language is the **best indicator**.

```
Looking for: "Wszystkie systemy w normie"
Found: "Wszystkie systemy w normie" → 1.0
Found: "All Systems Red" → 0.3 (different language)
```

### Rule 4: False Negatives > False Positives
**When in doubt, score LOW**. It's better to reject a good match than accept a wrong one.

```
Uncertain about match?
→ Score 0.4 or lower
→ User can manually select if needed
```

### Rule 5: Rejecting All is OK
It's **completely acceptable** to score all candidates as 0.0 if none match.

```
All candidates are wrong language? → All get 0.0
All candidates are different volumes? → All get 0.0
User will get manual selection prompt
```

---

## Temperature: 0.3

**Why 0.3 instead of 0.1?**

- **0.1** (old): Very deterministic, minimal reasoning
- **0.3** (new): Allows thoughtful comparison while staying focused
- Enables LLM to "think through" the candidates
- Still low enough to avoid randomness

**What this means**:
- LLM can weigh multiple factors
- Better handling of edge cases
- More nuanced scoring (0.75 vs 0.8 vs 0.85)
- Consistent but not robotic

---

## Prompt Structure

### 1. Book Information
```
Search term: Wszystkie wskaźniki czerwone. Sztuczny stan
Book information (what we're looking for):
  Title: Wszystkie systemy w normie. Sztuczny stan
  Author: Martha Wells
  Series: Pamiętniki Mordbota (Volume 1,2)
  Language: Polish
```

### 2. All Candidates
```
CANDIDATES TO EVALUATE:

Candidate 1:
  Source: audible
  Title: All Systems Red (The Murderbot Diaries, Book 1)
  Description: In a corporate-dominated spacefaring future...

Candidate 2:
  Source: lubimyczytac
  Title: Wszystkie systemy w normie (Pamiętniki Mordbota, #1)
  Description: Pierwsza powieść z serii...

[... all candidates listed]
```

### 3. Scoring Criteria
Clear rules explaining what makes a perfect match vs poor match.

### 4. Important Rules
Explicit warnings:
- Same series ≠ match if different volume
- Language matters
- Rejecting all is acceptable
- When in doubt, score low

### 5. Response Format
```
RESPONSE FORMAT:
Return ONLY the scores for each candidate, one per line:
Candidate 1: <score>
Candidate 2: <score>
...
```

---

## Response Parsing

The system handles multiple response formats:

### Format 1: Full (Preferred)
```
Candidate 1: 0.85
Candidate 2: 0.90
Candidate 3: 0.30
```

### Format 2: Short
```
1: 0.85
2: 0.90
3: 0.30
```

### Format 3: Just Numbers
```
0.85
0.90
0.30
```

All formats are parsed correctly using progressive regex patterns.

---

## Example Scenarios

### Scenario 1: Combined Volume Audiobook

**Looking for**: Polish combined edition (Volumes 1+2)

**Candidates**:
1. Audible - Volume 1 only (English) → 0.2
2. Audible - Volume 2 only (English) → 0.0
3. Goodreads - Volume 1 only (English) → 0.3
4. LubimyCzytac - Volume 1 only (Polish) → 0.7
5. LubimyCzytac - Combined (Polish) → **1.0** ✓

**Winner**: Candidate 5 (exact match)

### Scenario 2: Wrong Language

**Looking for**: Polish audiobook

**Candidates**:
1. Audible - English → 0.3
2. Audible - English → 0.2
3. Goodreads - English → 0.3
4. LubimyCzytac - Polish → **0.95** ✓

**Winner**: Candidate 4 (language match)

### Scenario 3: All Wrong

**Looking for**: Volume 1

**Candidates**:
1. Volume 2 → 0.0
2. Volume 3 → 0.0
3. Volume 2 (different language) → 0.0
4. Different book by same author → 0.1

**Result**: All scores < 0.5, manual selection shown to user ✓

---

## Configuration

### Temperature (in code)
```python
# src/search/llm_scoring.py line 90
temperature=0.3  # Higher temperature for reasoning and comparison
```

To adjust:
- **Lower (0.1-0.2)**: More deterministic, less reasoning
- **Current (0.3)**: Balanced - recommended
- **Higher (0.4-0.5)**: More creative, potentially less consistent

### Max Tokens
```env
# .env file
LLM_MAX_TOKENS=4096  # Default, sufficient for batch scoring
```

Batch scoring needs more tokens than individual scoring due to longer prompts.

---

## Testing

### Unit Test
```bash
python test_batch_scoring.py
```

Shows the generated prompt and explains the approach.

### Real Test
```bash
python BadaBoomBooks.py --auto-search --llm-select --dry-run \
  -R "path/to/audiobook"
```

Watch for:
- Single API call per book (not per candidate)
- Scores that respect language and volume matching
- Rejection of wrong volumes even from same series

---

## Benefits Summary

| Aspect | Individual Scoring | Batch Scoring |
|--------|-------------------|---------------|
| **Context** | Limited | Full comparison |
| **API Calls** | N calls (N candidates) | 1 call |
| **Cost** | Higher | Lower |
| **Speed** | Slower | Faster |
| **Accuracy** | Good | Better |
| **Language aware** | Somewhat | Highly |
| **Series aware** | Limited | Explicit rules |
| **Temperature** | 0.1 (rigid) | 0.3 (reasoning) |

---

## Migration Notes

The old individual scoring method (`_score_single_candidate`) is kept in the code but no longer used. This allows easy rollback if needed:

```python
# To rollback to individual scoring:
# In score_candidates(), replace:
return self._score_candidates_batch(candidates, search_term, book_info)

# With:
scored = []
for candidate in candidates:
    score = self._score_single_candidate(candidate, search_term, book_info)
    scored.append((candidate, score))
return scored
```

**Recommendation**: Keep batch scoring - it's significantly better.
