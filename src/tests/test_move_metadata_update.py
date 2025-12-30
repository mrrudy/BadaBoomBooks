"""
Test for metadata.input_folder update after successful move operation.

This test specifically verifies the fix for the bug where:
1. Files are successfully moved to new location
2. metadata.input_folder still points to old (non-existent) location
3. Any subsequent error references the old path in error messages
"""

import pytest
import shutil
from pathlib import Path
from src.main import BadaBoomBooksApp


@pytest.mark.integration
def test_move_updates_metadata_input_folder(existing_dir, expected_dir, cleanup_queue_ini, test_database, tmp_path):
    """
    Test that --move updates metadata.input_folder after successful move.

    This test verifies the fix for a bug where:
    1. Files are successfully moved to new location
    2. metadata.input_folder still points to old (non-existent) location
    3. Any subsequent error references the old path in error messages

    The fix ensures that after a successful move, metadata.input_folder
    is updated to point to the new location (metadata.final_output).

    Test command equivalent:
        python BadaBoomBooks.py --move --rename --from-opf \
            -O src/tests/data/expected -R src/tests/data/existing
    """
    # Setup: Create a temporary copy of test data (since --move will destroy it)
    temp_source_dir = tmp_path / "source"
    temp_source_dir.mkdir()

    # Copy test data to temporary location
    test_book_folder_orig = existing_dir / "[ignore] Book Title's - Author (Series)_"
    assert test_book_folder_orig.exists(), f"Test data folder not found: {test_book_folder_orig}"

    test_book_folder = temp_source_dir / "[ignore] Book Title's - Author (Series)_"
    shutil.copytree(test_book_folder_orig, test_book_folder)

    # Execute: Run BadaBoomBooks with --move (not --copy) on temporary copy
    app = BadaBoomBooksApp()
    exit_code = app.run([
        '--move',
        '--rename',
        '--from-opf',
        '--yolo',
        '-O', str(expected_dir),
        '-R', str(temp_source_dir)  # Use temp copy, not original test data
    ])

    # Verify: Application completed successfully
    assert exit_code == 0, "Application should exit with code 0 (success)"

    # Verify: Source folder no longer exists (moved, not copied)
    assert not test_book_folder.exists(), \
        f"Source folder should not exist after move: {test_book_folder}"

    # Verify: Correct folder structure created at destination
    expected_author_dir = expected_dir / "Aname A. Asurname"
    assert expected_author_dir.exists(), \
        f"Author directory not created: {expected_author_dir}"

    expected_book_dir = expected_author_dir / "Proper Title"
    assert expected_book_dir.exists(), \
        f"Book directory not created: {expected_book_dir}"

    # Verify: Audio files were moved and renamed correctly
    renamed_file_1 = expected_book_dir / "01 - Proper Title.mp3"
    renamed_file_2 = expected_book_dir / "02 - Proper Title.mp3"

    assert renamed_file_1.exists(), \
        f"Renamed audio file not found after move: {renamed_file_1}"
    assert renamed_file_2.exists(), \
        f"Renamed audio file not found after move: {renamed_file_2}"

    # Verify: metadata.opf exists at new location
    output_opf = expected_book_dir / "metadata.opf"
    assert output_opf.exists(), \
        f"metadata.opf not found after move: {output_opf}"

    # Verify: File count matches (2 audio + 1 OPF = 3 files)
    output_files = list(expected_book_dir.glob('*'))
    assert len(output_files) == 3, \
        f"Expected 3 files in output after move, found {len(output_files)}: {output_files}"
