# Legacy Code Archive

This folder contains the original monolithic code that has been replaced by the new modular architecture.

## Files Archived

- **`BadaBoomBooks.py`** - Original monolithic script (1000+ lines)
- **`scrapers.py`** - Original scraper functions  
- **`optional.py`** - Original file processing functions
- **`language_map.py`** - Language mapping (now in `src/language_map.py`)
- **`debug_selectors.py`** - Debug utilities
- **`*.html`** - Test pages for scraper development
- **`__pycache__/`** - Python cache files
- **`test_imports.py`** - Import testing script

## Why Archived

These files have been replaced by the new modular architecture in the `src/` directory which provides:

- Better organization and maintainability
- Clear separation of concerns
- Easier testing and debugging
- Enhanced error handling
- Type safety with hints
- AI-friendly code structure

## Using Legacy Code

If you need to reference the original implementation:

1. **For functionality**: Check the migration guide (`MIGRATION_GUIDE.md`) to see where functions moved
2. **For compatibility**: The new `BadaBoomBooks.py` maintains the same CLI interface
3. **For comparison**: Use this as reference when enhancing the modular version

## Migration Status

✅ **Fully Migrated**: All functionality has been successfully moved to the modular architecture  
✅ **Backward Compatible**: Same command-line interface and configuration files  
✅ **Enhanced Features**: Better error handling, progress reporting, and debugging  

The modular version is now the primary codebase.
