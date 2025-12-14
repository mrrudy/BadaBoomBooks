# Quick Reference: LLM Selection with Weights

## Basic Usage

```bash
# Process with LLM selection (recommended)
python BadaBoomBooks.py --auto-search --llm-select -R "path/to/audiobooks"

# Test LLM connection first
python BadaBoomBooks.py --llm-conn-test

# Dry run to see what would happen
python BadaBoomBooks.py --auto-search --llm-select --dry-run -R "path"
```

---

## Understanding the Output

When LLM selects a candidate, you'll see:

```
🤖 LLM Auto-selected: Wszystkie systemy w normie
   URL: https://lubimyczytac.pl/ksiazka/4896752/wszystkie-systemy-w-normie
   Site: lubimyczytac

   LLM Scores for all candidates:
   - [lubimyczytac] 0.860 (weighted: 1.032) ← SELECTED
     Wszystkie systemy w normie (Murderbot Diaries #1)
   - [audible] 0.870 (weighted: 0.957)
   - [goodreads] 0.850 (weighted: 0.892)

Accept this selection? [Y/n]:
```

### What This Means:

- **LLM Score** (e.g., 0.860): AI's confidence that this is the right book (0-1 scale)
- **Weighted Score** (e.g., 1.032): Final score after applying source preference
- **← SELECTED**: The winner after weighting

---

## Source Preferences (Weights)

| Source | Weight | When to Prefer |
|--------|--------|----------------|
| **LubimyCzytac** | 3.0 | Polish audiobooks, series info, complete metadata |
| **Audible** | 2.0 | English audiobooks, narrator details |
| **Goodreads** | 1.5 | General book info, reviews |

**Note**: Weights only matter when LLM scores are close (within 0.1). Clear winners always win.

---

## Reading the Scores

### Example 1: Clear Winner (No Weights Applied)

```
- [audible] 0.950 (weighted: 0.950) ← SELECTED
- [goodreads] 0.650
- [lubimyczytac] 0.620
```

**What happened**: Audible score (0.950) is much better than others. No weights applied because the difference is > 0.1. Audible wins clearly.

### Example 2: Close Race (Weights Applied)

```
- [lubimyczytac] 0.860 (weighted: 1.032) ← SELECTED
- [audible] 0.870 (weighted: 0.957)
- [goodreads] 0.850 (weighted: 0.892)
```

**What happened**: All scores within 0.1 of best (0.870). Weights applied. LubimyCzytac gets +20% boost and wins despite lower raw score.

### Example 3: Mixed (Partial Weighting)

```
- [audible] 0.920 (weighted: 0.920) ← SELECTED
- [lubimyczytac] 0.830 (weighted: 0.830)
- [goodreads] 0.810 (weighted: 0.810)
```

**What happened**: Audible score (0.920) is > 0.1 better than others. No weights applied to anyone. Audible wins clearly.

---

## Configuration (.env file)

Create a `.env` file in the project root:

```env
# Required
LLM_API_KEY=your-api-key-here

# Optional (defaults shown)
LLM_MODEL=gpt-3.5-turbo
OPENAI_BASE_URL=http://localhost:1234/v1  # For local models (LM Studio, Ollama)
```

### For Local Models (LM Studio, Ollama):

```env
LLM_API_KEY=not-needed
LLM_MODEL=openai/gpt-oss-20b  # Note: Must include provider prefix
OPENAI_BASE_URL=http://localhost:1234/v1
```

---

## Decision Tree

```
Is LLM configured? (.env file exists)
├─ NO  → Falls back to manual selection
└─ YES → LLM scores candidates
          │
          Is best score > 0.5? (50% confidence)
          ├─ NO  → Manual selection (LLM not confident)
          └─ YES → Are scores similar? (within 0.1)
                   ├─ NO  → Pick highest LLM score
                   └─ YES → Apply weights, pick highest weighted score
                            │
                            Show scores to user
                            │
                            User accepts? [Y/n]
                            ├─ YES → Use selected source
                            └─ NO  → Show all candidates
```

---

## Troubleshooting

### "LLM not configured"
→ Create `.env` file with `LLM_API_KEY`

### "LLM Provider NOT provided"
→ For local models, use provider prefix: `openai/model-name` or `ollama/model-name`

### "Connection failed"
→ Run `python BadaBoomBooks.py --llm-conn-test` for diagnostics

### "Best LLM score below threshold"
→ LLM couldn't find a good match. You'll be shown all candidates to choose manually.

### Weights not applying
→ Check that scores are within 0.1 of each other. Large differences ignore weights.

---

## Adjusting Preferences

Want to favor Audible over LubimyCzytac? Edit `src/config.py`:

```python
SCRAPER_REGISTRY = {
    "audible": {
        # ...
        "weight": 3.0  # Changed from 2.0 to 3.0
    },
    "lubimyczytac": {
        # ...
        "weight": 2.0  # Changed from 3.0 to 2.0
    }
}
```

---

## Common Workflows

### 1. Process New Audiobooks
```bash
python BadaBoomBooks.py --auto-search --llm-select --series --opf --id3-tag --move -O "T:\Sorted" -R "T:\Incoming"
```

### 2. Check What Would Happen (Dry Run)
```bash
python BadaBoomBooks.py --auto-search --llm-select --dry-run -R "T:\Test"
```

### 3. Just Metadata (No Moving Files)
```bash
python BadaBoomBooks.py --auto-search --llm-select --opf --id3-tag -R "T:\Books"
```

### 4. Test LLM Connection
```bash
python BadaBoomBooks.py --llm-conn-test
```

---

## Score Interpretation Guide

| LLM Score | Meaning | Action |
|-----------|---------|--------|
| 0.9 - 1.0 | Perfect match | Auto-accept confidently |
| 0.7 - 0.9 | Very good match | Review title, usually correct |
| 0.5 - 0.7 | Possible match | Check carefully before accepting |
| 0.0 - 0.5 | Poor match | System rejects, shows all options |

---

## Tips

💡 **Always review the title** shown in the selection, even with high scores

💡 **Weights favor preferred sources** when multiple good matches exist

💡 **Test with --dry-run** before processing entire libraries

💡 **Use --llm-conn-test** to verify setup before batch processing

💡 **LubimyCzytac wins ties** because it has best metadata for Polish audiobooks

💡 **You can always reject** the AI selection and choose manually

---

## Need More Help?

- Full documentation: [SCRAPER_WEIGHTS.md](SCRAPER_WEIGHTS.md)
- Implementation details: [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
- Visual guide: [CHANGES_VISUAL.md](CHANGES_VISUAL.md)
- Main documentation: [CLAUDE.md](CLAUDE.md)
