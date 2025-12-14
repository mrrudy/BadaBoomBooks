# Scraper Weights and LLM Scoring

## Overview

BadaBoomBooks uses a weighted scoring system to intelligently select the best metadata source when using LLM-assisted search (`--llm-select`). This system combines LLM quality scoring with scraper preference weights to ensure the most reliable and complete metadata is selected.

## How It Works

### 1. LLM Scoring (Primary)

The LLM (Language Model) scores each candidate based on:
- Title and author match quality
- Relevance to the search context
- Series and narrator information (if available)

Scores range from 0.0 to 1.0:
- **1.0** = Perfect match (exact title and author)
- **0.7-0.9** = Very good match (clear match with minor differences)
- **0.4-0.6** = Possible match (similar but uncertain)
- **0.0-0.3** = Poor match or wrong book

### 2. Scraper Weights (Tiebreaker)

When multiple candidates have **similar LLM scores** (within 0.1 quality bracket), scraper weights are applied as a tiebreaker.

Current weights (configured in [src/config.py](src/config.py)):
```
lubimyczytac.pl:  3.0  (HIGHEST - most favored)
audible.com:      2.0  (medium)
goodreads.com:    1.5  (lowest)
```

### 3. Weight Application Formula

Weights are only applied when candidates are in the same quality bracket:

```python
# Quality bracket: within 0.1 of the best score
if best_llm_score - llm_score <= 0.1:
    final_score = llm_score * (1.0 + (weight - 1.0) * 0.1)
else:
    final_score = llm_score  # No weight applied
```

### 4. Example Scenario

Given these LLM scores:
- Goodreads: 0.850
- Audible: 0.870
- LubimyCzytac: 0.860

All are within 0.1 of the best (0.870), so weights apply:

**After weighting:**
- LubimyCzytac: 1.032 (0.860 × 1.2) ← **WINNER**
- Audible: 0.957 (0.870 × 1.1)
- Goodreads: 0.892 (0.850 × 1.05)

Even though Audible had the highest LLM score, LubimyCzytac wins due to its higher weight.

## User Experience

When using `--llm-select`, the system will display:

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

This transparency allows users to:
- See all LLM scores
- Understand which weights were applied
- Know exactly why a particular source was selected
- Override the AI decision if needed

## Why LubimyCzytac is Favored

LubimyCzytac is configured with the highest weight (3.0) because it typically provides:
- Complete Polish metadata (for Polish audiobooks)
- Better series information
- More detailed narrator credits
- Volume/part ranges for multi-part audiobooks
- Higher quality cover images

## Customizing Weights

To change scraper preferences, edit `SCRAPER_REGISTRY` in [src/config.py](src/config.py):

```python
SCRAPER_REGISTRY = {
    "lubimyczytac": {
        # ... other config ...
        "weight": 3.0  # Change this value (1.0 - 5.0 recommended)
    }
}
```

Higher weights favor that scraper when LLM scores are close.

## Testing

Run the demonstration script to see how weights work:

```bash
python test_scoring_demo.py
```

This shows a realistic scenario with three candidates and demonstrates the weight application logic.

## Technical Details

### Implementation Files

- **[src/config.py](src/config.py)**: Scraper weight definitions
- **[src/search/candidate_selection.py](src/search/candidate_selection.py)**: Weight application logic
- **[src/search/llm_scoring.py](src/search/llm_scoring.py)**: LLM scoring implementation
- **[src/search/auto_search.py](src/search/auto_search.py)**: User interface and score display

### Quality Bracket Threshold

The similarity threshold (0.1) is defined in `CandidateSelector._apply_scraper_weights()`:

```python
SIMILARITY_THRESHOLD = 0.1  # Scores within this range are "similar"
```

Candidates outside this bracket won't have weights applied, ensuring that significantly better LLM scores always win.

### Acceptance Threshold

LLM selections require a minimum score of 0.5 (50% confidence):

```python
ACCEPTANCE_THRESHOLD = 0.5
```

If no candidate scores above this threshold, the user is prompted to manually select.

## Command Line Usage

Enable LLM-assisted selection with weights:

```bash
python BadaBoomBooks.py --auto-search --llm-select -R "path/to/audiobooks"
```

The system will:
1. Search for candidates
2. Score them with LLM
3. Apply weights to similar scores
4. Show you the results with transparency
5. Ask for confirmation before proceeding

## Benefits

1. **Intelligence**: LLM understands context and matches semantically
2. **Preference**: Weights ensure preferred sources win ties
3. **Transparency**: All scores shown to user for informed decisions
4. **Flexibility**: Easy to reconfigure weights per user preference
5. **Reliability**: Falls back gracefully if LLM unavailable
