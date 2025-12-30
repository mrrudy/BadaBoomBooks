# Bug Fix: Move Operation Metadata Update

## Issue Description

When using `--move` flag, files were successfully moved to the new location, but the `metadata.input_folder` field was not updated to reflect the new path. This caused misleading error messages if any subsequent operation failed, referencing the non-existent old path instead of the actual current location.

### Example Error (Before Fix)

```
✓ Resumed Slaughter Karin - Will Trent (tom 5) Upadek czyta Filip Kosior 128kbps
Moving... Renaming... Creating 'metadata.opf'... Creating 'info.txt'... Downloading cover...
Downloaded cover image to T:\Sorted\Books\newAudio\Sorted\Karin Slaughter\Will Trent\5 - Upadek\cover.jpg

⚠️ 1 books failed to process:
  - Slaughter Karin - Will Trent (tom 5) Upadek czyta Filip Kosior 128kbps
    (Move error: [WinError 3] The system cannot find the path specified:
    '\\\\nas.lan\\srv_storage\\VMs\\storage\\torrent\\Sorted\\Books\\newAudio\\Incoming\\Slaughter Karin - ...')
```

**Note**: The actual move operation **succeeded** (files exist at destination), but the error message references the old UNC path `\\nas.lan\...` which no longer exists.

## Root Cause

In [`src/processors/file_operations.py`](src/processors/file_operations.py), the `_move_folder()` method successfully moved files but did not update the `metadata.input_folder` attribute:

```python
def _move_folder(self, metadata: BookMetadata) -> bool:
    source = Path(metadata.input_folder)
    target = metadata.final_output

    # Move files (succeeds)
    source.rename(target)
    # or
    shutil.copytree(source, target)
    shutil.rmtree(source)

    # BUG: metadata.input_folder still points to old path!
    return True
```

This caused problems when:
1. Files were moved from `T:\Incoming\...` (mapped drive) to `T:\Sorted\...`
2. Any subsequent operation failed
3. Error handler tried to log `metadata.input_folder` (still pointing to old UNC path `\\nas.lan\...`)

## Solution

Update `metadata.input_folder` to point to the new location immediately after successful move:

```python
def _move_folder(self, metadata: BookMetadata) -> bool:
    source = Path(metadata.input_folder)
    target = metadata.final_output

    try:
        # Try direct rename first
        source.rename(target)
        metadata.input_folder = str(target)  # ✅ Update metadata
        return True
    except OSError:
        # Cross-filesystem move
        shutil.copytree(source, target)
        shutil.rmtree(source)
        metadata.input_folder = str(target)  # ✅ Update metadata
        return True
```

## Files Changed

- [`src/processors/file_operations.py:172,181`](src/processors/file_operations.py#L172) - Added `metadata.input_folder = str(target)` after successful move
- [`src/tests/test_move_metadata_update.py`](src/tests/test_move_metadata_update.py) - New test verifying the fix

## Testing

### New Test

Created comprehensive test `test_move_updates_metadata_input_folder` that verifies:
- ✅ Move operation succeeds
- ✅ Source folder no longer exists
- ✅ Files appear at destination with correct names
- ✅ All processing steps complete successfully
- ✅ No misleading error messages

**Important**: Test uses a temporary copy of test data (via `tmp_path` fixture) to avoid destroying the original test data during move operations.

### Test Results

```bash
# New test
python -m pytest src/tests/test_move_metadata_update.py -v
# PASSED

# All file operations tests
python -m pytest src/tests/test_file_operations.py -v
# 6 passed

# Previously failing tests (caused by missing test data)
python -m pytest src/tests/test_no_resume_flag.py src/tests/test_queue_system.py -v
# 16 passed
```

## Impact

- **User-visible change**: Error messages now correctly reference the current file location
- **Breaking change**: No
- **Backwards compatible**: Yes
- **Performance impact**: None (trivial string assignment)

## Related Issues

This fix specifically addresses the scenario where:
- User has network drive mapped (e.g., `T:` → `\\nas.lan\srv_storage\...`)
- Using `--move` flag with `--series` organization
- Any subsequent operation fails (rare, but possible)

The error message now correctly shows the destination path instead of the non-existent source path.
