# Visual Guide: Scraper Weights Implementation

## Before vs After

### BEFORE: Simple LLM Scoring

```
┌─────────────────────────────────────────────────┐
│ LLM Scores 3 Candidates                         │
├─────────────────────────────────────────────────┤
│ [goodreads]     0.850                           │
│ [audible]       0.870  ← WINNER (highest score) │
│ [lubimyczytac]  0.860                           │
└─────────────────────────────────────────────────┘

User sees:
  🤖 LLM Auto-selected: All Systems Red
     Site: audible

  Accept this selection? [Y/n]:
```

**Problem**: No visibility into scores, no preference for better sources

---

### AFTER: Weighted LLM Scoring with Transparency

```
┌─────────────────────────────────────────────────────────────┐
│ LLM Scores 3 Candidates + Apply Weights                      │
├─────────────────────────────────────────────────────────────┤
│ [goodreads]     0.850 → 0.892 (weight: 1.5x)                │
│ [audible]       0.870 → 0.957 (weight: 2.0x)                │
│ [lubimyczytac]  0.860 → 1.032 (weight: 3.0x) ← WINNER! ✨   │
└─────────────────────────────────────────────────────────────┘

User sees:
  🤖 LLM Auto-selected: Wszystkie systemy w normie
     URL: https://lubimyczytac.pl/ksiazka/4896752/...
     Site: lubimyczytac

     LLM Scores for all candidates:
     - [lubimyczytac] 0.860 (weighted: 1.032) ← SELECTED
       Wszystkie systemy w normie (Murderbot Diaries #1)
     - [audible] 0.870 (weighted: 0.957)
     - [goodreads] 0.850 (weighted: 0.892)

  Accept this selection? [Y/n]:
```

**Benefits**:
✅ Full transparency - all scores visible
✅ Smart tiebreaking - preferred source wins
✅ User informed - can make better decisions

---

## Visual Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    LLM SCORING PIPELINE                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                   ┌──────────────────┐
                   │  Search Results  │
                   │  (3 candidates)  │
                   └──────────────────┘
                              │
                              ▼
                   ┌──────────────────┐
                   │  LLM Scoring     │◄─── Uses litellm
                   │  (0.0 - 1.0)     │     (OpenAI/Local)
                   └──────────────────┘
                              │
                              ▼
                   ┌──────────────────┐
                   │  Quality Check   │
                   │  Bracket = 0.1   │
                   └──────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
               ▼                   ▼
    ┌──────────────────┐    ┌──────────────────┐
    │ Similar Scores?  │    │ Clear Winner?    │
    │ (within 0.1)     │    │ (>0.1 difference)│
    └──────────────────┘    └──────────────────┘
               │                        │
               ▼                        ▼
    ┌──────────────────┐    ┌──────────────────┐
    │ APPLY WEIGHTS ✓  │    │  NO WEIGHTS      │
    │                  │    │  (keep LLM score)│
    │ lubimyczytac 3.0x│    └──────────────────┘
    │ audible      2.0x│                │
    │ goodreads    1.5x│                │
    └──────────────────┘                │
               │                        │
               └─────────┬──────────────┘
                         ▼
              ┌──────────────────────┐
              │  Sort by Final Score │
              └──────────────────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │  Display to User     │
              │  (with transparency) │
              └──────────────────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │  User Confirms? Y/N  │
              └──────────────────────┘
```

---

## Weight Boost Visualization

### Formula: `final_score = llm_score * (1.0 + (weight - 1.0) * 0.1)`

```
Weight 1.5 (Goodreads):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  LLM: 0.850
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ Final: 0.892
                                              +5% boost

Weight 2.0 (Audible):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  LLM: 0.870
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ Final: 0.957
                                                +10% boost

Weight 3.0 (LubimyCzytac):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  LLM: 0.860
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ Final: 1.032
                                                  +20% boost ✨
```

**Result**: LubimyCzytac wins despite having lower raw LLM score!

---

## Code Changes Map

```
src/
├── config.py
│   └── SCRAPER_REGISTRY
│       ├── "audible"      ← Added: "weight": 2.0
│       ├── "goodreads"    ← Added: "weight": 1.5
│       └── "lubimyczytac" ← Added: "weight": 3.0
│
├── search/
│   ├── candidate_selection.py
│   │   ├── __init__()              ← Added: last_scored_candidates = []
│   │   ├── _ai_select_candidate()  ← Modified: Apply weights + store scores
│   │   └── _apply_scraper_weights() ← NEW METHOD: Weight application logic
│   │
│   └── auto_search.py
│       └── _user_select_candidate() ← Modified: Display LLM scores with weights
│
└── (unchanged files...)
```

---

## Real-World Example

### Scenario: Processing "The Murderbot Diaries"

**Input**:
```bash
python BadaBoomBooks.py --auto-search --llm-select --dry-run \
  -R "T:\Audiobooks\Martha Wells\The Murderbot Diaries"
```

**Search Results**:
- Goodreads: English version, basic metadata
- Audible: English version, great narrator info
- LubimyCzytac: Polish version, complete series metadata

**LLM Analysis**:
```
All three look equally good!
- Goodreads: 0.85 (recognizes title and author)
- Audible:   0.87 (recognizes title, author, and format)
- LubimyCzytac: 0.86 (recognizes Polish title and author)
```

**Weight Application**:
```
All scores within 0.1 of best (0.87), so weights apply:
- Goodreads:     0.85 * 1.05 = 0.892
- Audible:       0.87 * 1.10 = 0.957
- LubimyCzytac:  0.86 * 1.20 = 1.032 ← WINNER
```

**User Sees**:
```
🤖 LLM Auto-selected: Wszystkie systemy w normie (Murderbot Diaries #1)
   URL: https://lubimyczytac.pl/ksiazka/4896752/wszystkie-systemy-w-normie
   Site: lubimyczytac

   LLM Scores for all candidates:
   - [lubimyczytac] 0.860 (weighted: 1.032) ← SELECTED
     Wszystkie systemy w normie (Murderbot Diaries #1)
   - [audible] 0.870 (weighted: 0.957)
   - [goodreads] 0.850 (weighted: 0.892)

Accept this selection? [Y/n]:
```

**User presses Y** → Gets superior Polish metadata with series info!

---

## Configuration Reference

| Setting | Location | Default | Purpose |
|---------|----------|---------|---------|
| **Scraper Weights** | `config.py` | lubimyczytac: 3.0<br>audible: 2.0<br>goodreads: 1.5 | Preference multipliers |
| **Quality Bracket** | `candidate_selection.py` | 0.1 | Similarity threshold |
| **Acceptance Threshold** | `candidate_selection.py` | 0.5 | Minimum LLM score |
| **Weight Impact Factor** | `candidate_selection.py` | 0.1 | Boost multiplier |

---

## Testing Commands

```bash
# Verify configuration
python test_weights.py

# See demonstration
python test_scoring_demo.py

# Test LLM connection
python BadaBoomBooks.py --llm-conn-test

# Process with LLM selection
python BadaBoomBooks.py --auto-search --llm-select -R "path/to/audiobook"
```

---

## Key Takeaways

1. **🎯 Smart Tiebreaking**: Weights only apply when scores are similar (within 0.1)
2. **📊 Full Transparency**: Users see all scores and understand the decision
3. **🏆 LubimyCzytac Favored**: Highest weight (3.0) for best Polish metadata
4. **🛡️ Safe Fallback**: Clear winners still win regardless of weights
5. **⚙️ Configurable**: Easy to adjust weights or thresholds as needed
