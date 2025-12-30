# LLM Prompt Improvements for Author Name Matching

## Problem

The LLM candidate selection was returning false negatives (score 0.0) for perfect matches when author names appeared in different orders:

**Example:**
- **Query**: "Tron dla faworyta by Stempniewicz Czesław"
- **Candidate 2** (lubimyczytac): "Tron dla faworyta - Czesław Stempniewicz"
- **Issue**: Same book, same author, but LLM scored 0.0 due to name order difference

## Root Cause

Polish, Czech, and other Slavic language naming conventions often use **"Surname Firstname"** order (e.g., "Stempniewicz Czesław"), while Western conventions use **"Firstname Surname"** (e.g., "Czesław Stempniewicz").

The original LLM prompt mentioned diacritics and 1-2 character typo tolerance but **did not explicitly state that name order variations are acceptable**.

## Solution

Enhanced the LLM scoring prompt in `src/search/llm_scoring.py` with three key improvements:

### 1. **Explicit Name Order Tolerance in PERFECT MATCH criteria** (lines 311-327)

```
1. PERFECT MATCH (0.9-1.0):
   - **Author name contains same components** (ORDER IRRELEVANT):
     * "Stempniewicz Czesław" = "Czesław Stempniewicz" → PERFECT MATCH
     * Name variations allowed:
       - Name order: "Surname Firstname" = "Firstname Surname" (both valid)
       - Diacritics: "Čapek"="Capek", "José"="Jose"
       - Typos: One letter difference acceptable
     * CRITICAL: If same first+last name words appear → PERFECT MATCH regardless of order
     * Examples that should score 1.0:
       - "Stempniewicz Czesław" vs "Czesław Stempniewicz" → 1.0
       - "Karel Čapek" vs "Čapek Karel" → 1.0
```

### 2. **New "AUTHOR NAME MATCHING RULES" Section** (lines 352-363)

Added a dedicated section before diacritics rules to emphasize author name matching:

```
AUTHOR NAME MATCHING RULES (CRITICAL):
- **NAME ORDER DOES NOT MATTER**: "Stempniewicz Czesław" = "Czesław Stempniewicz"
  * Polish/Czech/Slavic names: "Surname Firstname" (LastName FirstName) format is common
  * Western format: "Firstname Surname" (FirstName LastName)
  * BOTH ARE VALID - if same name components appear, it's a MATCH regardless of order
  * Examples of PERFECT matches:
    - "Stempniewicz Czesław" vs "Czesław Stempniewicz" → SCORE 1.0
    - "Capek Karel" vs "Karel Capek" → SCORE 1.0
    - "Rowling J.K." vs "J.K. Rowling" → SCORE 1.0
- **MATCHING ALGORITHM**: Extract all name components (first name, last name), compare as sets
  * If all components match (ignoring order) → PERFECT MATCH (1.0)
  * If diacritics differ but same components → PERFECT MATCH (1.0)
```

### 3. **Concrete Example with Exact Test Case** (line 313, 323)

Included the actual problematic case in the prompt examples:

```
- "Stempniewicz Czesław" vs "Czesław Stempniewicz" → 1.0
```

This gives the LLM a direct reference when scoring the exact case we're testing.

## Testing

To verify the updated prompt:

```bash
# Run with --debug and --llm-select to see LLM scores
python BadaBoomBooks.py "T:\Sorted\Books\newAudio\Incoming\Stempniewicz Czesław - Tron dla faworyta (czyta Adam Bauman) 320kbps" \
  -O "T:\Sorted\Books\newAudio\Sorted" \
  --move --series --opf --force-refresh --rename --infotxt --cover \
  --auto-search --llm-select --workers 1 --interactive --dry-run
```

**Expected outcome**: Candidate 2 (lubimyczytac) should now score ≥0.9 instead of 0.0.

## Files Modified

- **`src/search/llm_scoring.py`**: Enhanced `_build_batch_scoring_prompt()` method
  - Lines 311-327: Updated PERFECT MATCH criteria
  - Lines 352-363: New AUTHOR NAME MATCHING RULES section
  - Lines 313, 323: Added concrete example with "Stempniewicz Czesław"

## Impact

This fix improves LLM matching accuracy for:
- Polish, Czech, Hungarian, and other Slavic language audiobooks
- Any author names that appear in different conventional orders
- Multi-cultural book collections with mixed naming conventions

The LLM should now correctly identify perfect matches regardless of whether the source uses "Firstname Lastname" or "Lastname Firstname" order.

## Additional Benefits

The enhanced prompt also reinforces:
- Diacritics equivalence (ł/l, ą/a, ć/c, etc.)
- Typo tolerance (1-2 character differences)
- Narrator/bitrate metadata should be ignored for matching

These improvements make the LLM more robust to real-world metadata variations found in audiobook libraries.
