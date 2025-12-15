"""
Integration tests for file operations (copy, rename, organize).

This module tests the complete processing pipeline including:
- Reading metadata from OPF files
- Copying audiobook folders
- Renaming audio files
- Path sanitization
- UTF-8 encoding handling
"""

import pytest
from pathlib import Path
import xml.etree.ElementTree as ET
from src.main import BadaBoomBooksApp


@pytest.mark.integration
def test_copy_rename_from_opf(existing_dir, expected_dir, cleanup_queue_ini):
    """
    Test complete processing pipeline: --copy --rename --from-opf.

    This test verifies that the application can:
    1. Read metadata from an existing metadata.opf file
    2. Copy the audiobook folder to the correct output structure
    3. Rename audio files to numbered format (01 - Title.mp3)
    4. Handle problematic folder names with special characters
    5. Preserve UTF-8 encoding in metadata

    Test command equivalent:
        python BadaBoomBooks.py --copy --rename --from-opf \
            -O src/tests/data/expected -R src/tests/data/existing
    """
    # Setup: Verify test data exists
    test_book_folder = existing_dir / "[ignore] Book Title's - Author (Series)_"
    assert test_book_folder.exists(), f"Test data folder not found: {test_book_folder}"

    opf_file = test_book_folder / "metadata.opf"
    assert opf_file.exists(), f"Test OPF file not found: {opf_file}"

    audio_file_1 = test_book_folder / "1-one.mp3"
    audio_file_2 = test_book_folder / "2-.mp3"
    assert audio_file_1.exists(), f"Test audio file not found: {audio_file_1}"
    assert audio_file_2.exists(), f"Test audio file not found: {audio_file_2}"

    # Execute: Run BadaBoomBooks with test arguments
    # Note: --yolo flag auto-accepts all prompts for automated testing
    app = BadaBoomBooksApp()
    exit_code = app.run([
        '--copy',
        '--rename',
        '--from-opf',
        '--yolo',
        '-O', str(expected_dir),
        '-R', str(existing_dir)
    ])

    # Verify: Application completed successfully
    assert exit_code == 0, "Application should exit with code 0 (success)"

    # Verify: Correct folder structure created
    # Expected: expected_dir/Aname A. Asurname/Proper Title/
    expected_author_dir = expected_dir / "Aname A. Asurname"
    assert expected_author_dir.exists(), \
        f"Author directory not created: {expected_author_dir}"

    expected_book_dir = expected_author_dir / "Proper Title"
    assert expected_book_dir.exists(), \
        f"Book directory not created: {expected_book_dir}"

    # Verify: Audio files were copied and renamed correctly
    renamed_file_1 = expected_book_dir / "01 - Proper Title.mp3"
    renamed_file_2 = expected_book_dir / "02 - Proper Title.mp3"

    assert renamed_file_1.exists(), \
        f"Renamed audio file not found: {renamed_file_1}"
    assert renamed_file_2.exists(), \
        f"Renamed audio file not found: {renamed_file_2}"

    # Verify: metadata.opf was copied
    output_opf = expected_book_dir / "metadata.opf"
    assert output_opf.exists(), \
        f"metadata.opf not found in output: {output_opf}"

    # Verify: OPF content preserved correctly (UTF-8 encoding)
    tree = ET.parse(output_opf)
    root = tree.getroot()

    ns = {
        'dc': 'http://purl.org/dc/elements/1.1/',
        'opf': 'http://www.idpf.org/2007/opf'
    }

    # Check title
    title_elem = root.find('.//dc:title', ns)
    assert title_elem is not None, "Title element not found in OPF"
    assert title_elem.text == "Proper Title", \
        f"Title mismatch: {title_elem.text}"

    # Check author
    author_elem = root.find('.//dc:creator[@opf:role="aut"]', ns)
    assert author_elem is not None, "Author element not found in OPF"
    assert author_elem.text == "Aname A. Asurname", \
        f"Author mismatch: {author_elem.text}"

    # Check series (should be preserved even though not used in folder structure)
    series_elem = root.find('.//opf:meta[@name="calibre:series"]', ns)
    assert series_elem is not None, "Series element not found in OPF"
    assert series_elem.get('content') == "Series Title", \
        f"Series mismatch: {series_elem.get('content')}"

    # Check volume number
    volume_elem = root.find('.//opf:meta[@name="calibre:series_index"]', ns)
    assert volume_elem is not None, "Volume element not found in OPF"
    assert volume_elem.get('content') == "22", \
        f"Volume mismatch: {volume_elem.get('content')}"

    # Check UTF-8 characters in description
    desc_elem = root.find('.//dc:description', ns)
    assert desc_elem is not None, "Description element not found in OPF"
    description = desc_elem.text

    # Verify some UTF-8 Polish characters are preserved
    utf8_chars = ['ą', 'ę', 'ć', 'ł', 'ó', 'ń', 'ś', 'ź', 'ż', 'Ś', 'Ż']
    found_utf8_chars = [char for char in utf8_chars if char in description]
    assert len(found_utf8_chars) > 0, \
        f"UTF-8 characters not preserved in description. Found: {found_utf8_chars}"

    # Verify: File count matches (2 audio + 1 OPF = 3 files)
    output_files = list(expected_book_dir.glob('*'))
    assert len(output_files) == 3, \
        f"Expected 3 files in output, found {len(output_files)}: {output_files}"

    # Verify: Original files unchanged
    assert test_book_folder.exists(), "Original folder should still exist (--copy mode)"
    assert opf_file.exists(), "Original OPF should still exist"
    assert audio_file_1.exists(), "Original audio file 1 should still exist"
    assert audio_file_2.exists(), "Original audio file 2 should still exist"


@pytest.mark.integration
def test_copy_rename_from_opf_with_series(existing_dir, expected_dir, cleanup_queue_ini):
    """
    Test processing with --series flag to create series folder structure.

    Expected structure:
        expected_dir/Aname A. Asurname/Series Title/22 - Proper Title/
    """
    # Execute: Run with --series flag
    # Note: --yolo flag auto-accepts all prompts for automated testing
    app = BadaBoomBooksApp()
    exit_code = app.run([
        '--copy',
        '--rename',
        '--from-opf',
        '--series',
        '--yolo',
        '-O', str(expected_dir),
        '-R', str(existing_dir)
    ])

    assert exit_code == 0, "Application should exit with code 0"

    # Verify: Series folder structure created
    expected_author_dir = expected_dir / "Aname A. Asurname"
    expected_series_dir = expected_author_dir / "Series Title"
    expected_book_dir = expected_series_dir / "22 - Proper Title"

    assert expected_author_dir.exists(), \
        f"Author directory not created: {expected_author_dir}"
    assert expected_series_dir.exists(), \
        f"Series directory not created: {expected_series_dir}"
    assert expected_book_dir.exists(), \
        f"Book directory not created: {expected_book_dir}"

    # Verify: Files exist in the series folder
    renamed_file_1 = expected_book_dir / "01 - Proper Title.mp3"
    renamed_file_2 = expected_book_dir / "02 - Proper Title.mp3"
    output_opf = expected_book_dir / "metadata.opf"

    assert renamed_file_1.exists(), f"File not found: {renamed_file_1}"
    assert renamed_file_2.exists(), f"File not found: {renamed_file_2}"
    assert output_opf.exists(), f"OPF not found: {output_opf}"
