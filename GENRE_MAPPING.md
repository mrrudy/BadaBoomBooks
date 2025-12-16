# Genre Normalization and Mapping

## Overview

BadaBoomBooks automatically normalizes and maps genre names when creating OPF metadata files. This ensures consistent genre classification across different audiobook sources and eliminates duplicates caused by variations in naming conventions.

## How It Works

### Automatic Processing

Genre normalization happens automatically whenever an OPF file is written. The process:

1. **Lowercase Normalization**: All genres are converted to lowercase
   - `Horror` → `horror`
   - `ROMANCE` → `romance`
   - `Science Fiction` → `science fiction`

2. **Alternative Mapping**: Genre alternatives are mapped to canonical forms
   - `romans` → `romance`
   - `sci-fi` → `science fiction`
   - `polska` → `poland`

3. **Deduplication**: Duplicate genres are removed (preserving first occurrence order)
   - `["Fantasy", "fantasy", "FANTASY"]` → `["fantasy"]`
   - `["Romance", "romans", "love"]` → `["romance"]` (all map to same canonical form)

4. **Unknown Genres**: Genres not in the mapping file become new canonical forms
   - If you scrape `"Dystopian"` and it's not mapped, it stays as `"dystopian"`

### Example Transformation

**Input from various scrapers:**
```
Goodreads:      ["Fantasy", "Science Fiction", "Horror"]
LubimyCzytac:   ["Fantastyka", "Horror", "Polska"]
Audible:        ["Sci-Fi", "Horror"]
```

**After normalization:**
```
Final OPF:      ["fantasy", "science fiction", "horror", "poland"]
```

## Mapping File

### Location

The genre mapping is stored in `genre_mapping.json` in the project root directory.

### Format

The mapping file is a JSON object where:
- **Keys** are canonical genre names (lowercase)
- **Values** are arrays of alternative names (lowercase) that map to the canonical form

**Example:**
```json
{
  "romance": ["romans", "romantasy", "love", "romantic"],
  "science fiction": ["sci-fy", "sci-fi", "sf", "space", "science fiction & fantasy"],
  "fantasy": ["fantastyka", "epic fantasy", "urban fantasy"],
  "poland": ["polska", "polish", "polish literature"],
  "horror": [],
  "mystery": ["thriller", "crime", "detective", "suspense"]
}
```

### Default Mappings

If the mapping file doesn't exist, BadaBoomBooks will create one with these defaults:

| Canonical Genre | Alternatives |
|----------------|--------------|
| audiobook | |
| biography | biographical, memoir, autobiography |
| fantasy | fantastyka, epic fantasy, urban fantasy, dark fantasy |
| fiction | literary fiction, contemporary fiction |
| history | historical, historia |
| horror | |
| mystery | thriller, crime, detective, suspense |
| nonfiction | non-fiction, non fiction |
| poland | polska, polish, polish literature |
| romance | romans, romantasy, love, romantic |
| science fiction | sci-fy, sci-fi, sf, space, science fiction & fantasy, science fiction fantasy, sci fi |
| young adult | ya, teen, young adult fiction |

## Customizing the Mapping

### Manual Editing

The `genre_mapping.json` file is designed to be human-readable and easy to edit:

1. Open `genre_mapping.json` in any text editor
2. Add new canonical genres or update existing ones
3. Save the file (ensure valid JSON syntax)
4. Changes take effect immediately on next run

**Example - Adding a new mapping:**
```json
{
  "romance": ["romans", "romantasy", "love"],
  "dystopian": ["dystopia", "post-apocalyptic", "apocalyptic"]
}
```

**Example - Updating existing mapping:**
```json
{
  "science fiction": ["sci-fy", "sci-fi", "sf", "space", "scifi", "hard sf"]
}
```

### Programmatic Access

You can also interact with the mapping programmatically:

```python
from src.utils.genre_normalizer import get_normalizer

# Get the global normalizer instance
normalizer = get_normalizer()

# Add a new mapping
normalizer.add_mapping("adventure", ["action", "quest", "exploration"])

# Save changes to file
normalizer.save_mapping()

# Normalize a list of genres
genres = ["Horror", "ROMANCE", "Sci-Fi", "polska"]
normalized = normalizer.normalize_genres(genres)
# Result: ["horror", "romance", "science fiction", "poland"]
```

## Best Practices

### Building Your Mapping

1. **Start with defaults**: Let the app run and observe what genres appear in your library
2. **Add mappings gradually**: When you notice variations, add them to the mapping file
3. **Be consistent**: Choose canonical names that match your library management style
4. **Use lowercase**: The system handles case automatically, but keep mapping file lowercase for clarity

### Choosing Canonical Names

- **Prefer simple terms**: `"science fiction"` over `"science fiction & fantasy"`
- **Match library conventions**: If you use Audiobookshelf/Plex, align with their genre lists
- **Consider sorting**: Genres appear alphabetically in most apps, so naming matters
- **Avoid redundancy**: Don't create `"sci-fi"` and `"science fiction"` as separate canonical forms

### Handling Multi-Source Genres

When scraping from multiple sources (Goodreads + LubimyCzytac):
- Map regional variants to English: `"fantastyka"` → `"fantasy"`
- Consolidate sub-genres: `"epic fantasy"`, `"urban fantasy"` → `"fantasy"` (or keep separate if you prefer granularity)
- Handle compound genres: `"science fiction & fantasy"` → `"science fiction"` (decide if you want to split or map)

## UTF-8 Support

The mapping file fully supports UTF-8 characters for non-English genres:

```json
{
  "komedia": ["śmieszne", "zabawne"],
  "polska": ["książka polska", "literatura polska"]
}
```

## Technical Details

### Implementation

- **Module**: [src/utils/genre_normalizer.py](src/utils/genre_normalizer.py)
- **Integration**: [src/processors/metadata_operations.py](src/processors/metadata_operations.py#L205-L224)
- **Tests**: [src/tests/test_genre_normalization.py](src/tests/test_genre_normalization.py)

### Processing Pipeline

```
Scraper extracts genres → BookMetadata.genres (comma-separated string)
                           ↓
                  OPF writing triggered
                           ↓
            metadata.get_genres_list() (split to list)
                           ↓
        normalize_genres() [genre_normalizer.py]
          • Lowercase all genres
          • Map alternatives to canonical
          • Remove duplicates
                           ↓
      _format_genres_for_opf() writes to OPF:
        <dc:subject>fantasy</dc:subject>
        <dc:subject>science fiction</dc:subject>
```

### Singleton Pattern

The normalizer uses a singleton pattern for efficiency:
- Mapping file is loaded once per session
- Multiple calls to `normalize_genres()` reuse the same mapping
- Changes via `add_mapping()` persist only if `save_mapping()` is called

## Testing

Run the comprehensive test suite:

```bash
# Run all genre normalization tests
python -m pytest src/tests/test_genre_normalization.py -v

# Test with different mapping scenarios
python -m pytest src/tests/test_genre_normalization.py::TestGenreNormalizer -v

# Test integration with OPF writing
python -m pytest src/tests/test_genre_normalization.py::TestIntegrationWithOPF -v
```

## Troubleshooting

### Genres not being mapped

1. Check that `genre_mapping.json` exists in project root
2. Verify JSON syntax is valid (use a JSON validator)
3. Ensure alternatives are lowercase in the mapping file
4. Check logs: genre normalization warnings appear in debug output

### Mapping file not created

- The file is created automatically on first run if missing
- Default location: `<project_root>/genre_mapping.json`
- Check file permissions if auto-creation fails

### Genres appearing twice

- This shouldn't happen after normalization
- If it does, check that the genre isn't both a canonical name AND an alternative
- Example of bad mapping (don't do this):
  ```json
  {
    "science fiction": ["sci-fi"],
    "sci-fi": ["sf"]  // ❌ Wrong: sci-fi should only be an alternative
  }
  ```

## Future Enhancements

Potential improvements to consider:

- **Auto-learning**: Automatically suggest mappings based on user selections
- **Genre hierarchies**: Support parent-child relationships (e.g., "urban fantasy" → "fantasy")
- **Import/Export**: Share mapping files between users or libraries
- **Web UI integration**: Edit mappings through the web interface
- **Scraper-specific preferences**: Different canonical names per scraper source

## Examples

### Example 1: Polish Audiobook Library

Your library mostly uses LubimyCzytac (Polish site), but occasionally Goodreads:

```json
{
  "fantasy": ["fantastyka", "fantasyka"],
  "science fiction": ["fantastyka naukowa", "sci-fi"],
  "crime": ["kryminał", "thriller", "sensacja"],
  "romance": ["romans"],
  "poland": ["polska", "literatura polska"]
}
```

### Example 2: English-Only Library

You only use Audible and Goodreads:

```json
{
  "fantasy": [],
  "science fiction": ["sci-fi", "sf", "scifi"],
  "mystery": ["thriller", "crime", "suspense"],
  "romance": [],
  "nonfiction": ["non-fiction"]
}
```

### Example 3: Granular Genre Classification

You want detailed genre categorization:

```json
{
  "epic fantasy": ["high fantasy"],
  "urban fantasy": ["contemporary fantasy"],
  "hard science fiction": ["hard sf"],
  "space opera": ["space adventure"],
  "cyberpunk": ["cyber punk"],
  "cozy mystery": ["cosy mystery"],
  "romantic suspense": ["romance thriller"]
}
```

---

**Note**: Genre normalization is applied **only during OPF file creation**. Existing OPF files are not automatically updated. To apply new mappings to existing books, use:

```bash
python BadaBoomBooks.py --from-opf --opf --force-refresh "C:\Path\To\Book"
```

This will re-scrape metadata and regenerate the OPF with current mapping rules.
