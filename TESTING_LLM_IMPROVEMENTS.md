# Testing LLM Author Name Matching Improvements

## Quick Test Commands

### Test Case: Stempniewicz Czesław - Tron dla faworyta

This book has author name in **"Surname Firstname"** order in ID3 tags but **"Firstname Surname"** on lubimyczytac.pl.

**Before fix**: LLM scored lubimyczytac candidate as 0.0 (false negative)
**After fix**: LLM should score lubimyczytac candidate as ≥0.9 (correct match)

### Command 1: Interactive Test (See LLM Scores)

```bash
python BadaBoomBooks.py \
  "T:\Sorted\Books\newAudio\Incoming\Stempniewicz Czesław - Tron dla faworyta (czyta Adam Bauman) 320kbps" \
  -O "T:\Sorted\Books\newAudio\Sorted" \
  --move --series --opf --force-refresh --rename --infotxt --cover \
  --auto-search --llm-select --workers 1 --interactive --dry-run
```

**What to look for:**
```
Candidate pages:

[1] [goodreads] 0.00
    Null by Szczepan Twardoch | Goodreads
    ...

[2] [lubimyczytac] 0.95   ← Should be high score now (was 0.00 before)
    Tron dla faworyta - Czesław Stempniewicz | Książka w Lubimyczytac.pl ...
    ...
```

### Command 2: Fully Automated Test (YOLO Mode)

```bash
python BadaBoomBooks.py \
  "T:\Sorted\Books\newAudio\Incoming\Stempniewicz Czesław - Tron dla faworyta (czyta Adam Bauman) 320kbps" \
  -O "T:\Sorted\Books\newAudio\Sorted" \
  --move --series --opf --force-refresh --rename --infotxt --cover \
  --auto-search --llm-select --yolo --dry-run --debug
```

**What to check in debug output:**
```
LLM batch scored 'Tron dla faworyta - Czesław Stempniewicz | Książka w Lubimyczytac.pl ...' (lubimyczytac) as 0.95
```

### Command 3: Debug Mode with Log File

```bash
python BadaBoomBooks.py \
  "T:\Sorted\Books\newAudio\Incoming\Stempniewicz Czesław - Tron dla faworyta (czyta Adam Bauman) 320kbps" \
  -O "T:\Sorted\Books\newAudio\Sorted" \
  --auto-search --llm-select --yolo --dry-run --debug 2>&1 | tee llm_test.log
```

Then search the log:
```bash
grep "LLM batch scored" llm_test.log
grep "lubimyczytac" llm_test.log
```

## Other Test Cases with Name Order Variations

### Polish Authors (Surname Firstname)

```bash
# Sapkowski Andrzej (should match "Andrzej Sapkowski")
# Lem Stanisław (should match "Stanisław Lem")
# Sienkiewicz Henryk (should match "Henryk Sienkiewicz")
```

### Czech Authors

```bash
# Capek Karel (should match "Karel Čapek" or "Karel Capek")
# Kundera Milan (should match "Milan Kundera")
```

### Western Authors (Usually Firstname Lastname, but may vary)

```bash
# "Rowling J.K." should match "J.K. Rowling"
# "King Stephen" should match "Stephen King"
```

## Expected Results

### Success Indicators

✅ **lubimyczytac candidate scores ≥0.9** for exact title+author match (different name order)
✅ **LLM log shows**: `LLM batch scored '...lubimyczytac...' as 0.9X`
✅ **No "No high-confidence matches" warning** when perfect match exists

### Failure Indicators (Prompt needs more work)

❌ **lubimyczytac candidate still scores 0.0** despite matching title+author
❌ **LLM rejects all candidates** when perfect match is available
❌ **Manual selection required** for obvious matches

## Troubleshooting

### If LLM still returns low scores:

1. **Check LLM model**: Some models are better at following complex instructions
   ```bash
   python BadaBoomBooks.py --llm-conn-test
   ```

2. **Try different model**: Edit `.env` file
   ```
   LLM_MODEL=gpt-4  # Better instruction following
   # or
   LLM_MODEL=claude-3-opus-20240229  # Excellent with nuanced instructions
   ```

3. **Increase temperature** (experimental): Edit `src/search/llm_scoring.py` line 90
   ```python
   temperature=0.5,  # Higher = more creative/flexible (was 0.3)
   ```

4. **Inspect actual prompt**: Add temporary print statement in `llm_scoring.py`
   ```python
   # Line 84, after building prompt:
   print("="*80)
   print("PROMPT SENT TO LLM:")
   print(prompt)
   print("="*80)
   ```

## Verification Checklist

After making prompt changes, verify:

- [ ] Exact title match with reversed author name order scores ≥0.9
- [ ] Exact title+author with diacritics scores ≥0.9
- [ ] Different book by same author scores <0.5
- [ ] Completely unrelated book scores 0.0
- [ ] Narrator/bitrate differences don't affect score (if title+author match)

## Contributing Test Cases

If you find other false negatives, please document:

1. **Folder name**: `[Author format] - [Title] (czyta [Narrator]) [bitrate]`
2. **Expected match**: Candidate that should score high but doesn't
3. **Actual LLM score**: What score it received
4. **LLM model used**: Which model returned the score
5. **Book metadata**: Title, author, series info from ID3/folder

Create an issue with this information to help improve the prompt further.
