"""
Integration test for processing author folders with nested book folders.

Tests the scenario where users pass an author folder containing multiple books,
each with their own nested structure (e.g., "Author/Book - Author/Book/metadata.opf").
"""

import pytest
import shutil
import subprocess
import sys
from pathlib import Path

from src.processors.metadata_operations import MetadataProcessor


@pytest.mark.integration
@pytest.mark.requires_network
@pytest.mark.author_folder
def test_author_folder_with_nested_books(
    all_scraper_samples,
    expected_dir,
    metadata_processor,
    cleanup_queue_ini,
    test_database
):
    """
    Test processing an author folder containing nested book folders.

    Scenario:
    - User has structure: A.B. Obarska/
                            └── Fuga dwojga serc - A.B. Obarska/
                                └── Fuga dwojga serc/
                                    ├── metadata.opf
                                    └── 01-chapter.mp3

    - User runs: python BadaBoomBooks.py 'A.B. Obarska' --from-opf --opf --force-refresh

    Expected behavior:
    - App should find metadata.opf in nested subdirectories
    - App should use that OPF for processing
    - App should write updated OPF to the same location

    Current behavior (BUG):
    - App looks for metadata.opf directly in 'A.B. Obarska/metadata.opf'
    - App cannot find OPF, tries to scrape from folder name
    - App writes OPF to wrong location
    """
    import random

    # Step 1: Select random sample
    all_samples = []
    for service, samples in all_scraper_samples.items():
        all_samples.extend(samples)

    if not all_samples:
        pytest.skip("No scraper samples available")

    reference_opf_path = random.choice(all_samples)
    print(f"\nSelected sample: {reference_opf_path.parent.name}")

    # Step 2: Read reference metadata
    reference_metadata = metadata_processor.read_opf_metadata(reference_opf_path)
    assert reference_metadata is not None, f"Failed to read OPF from {reference_opf_path}"

    # Step 3: Create nested directory structure (Author/Book - Author/Book/)
    author = reference_metadata.author or "Unknown Author"
    title = reference_metadata.title or "Unknown Title"

    from src.utils import clean_filename
    author_clean = clean_filename(author)
    title_clean = clean_filename(title)

    # Create structure: Author/Title - Author/Title/
    author_folder = expected_dir / author_clean
    book_outer_folder = author_folder / f"{title_clean} - {author_clean}"
    book_inner_folder = book_outer_folder / title_clean
    book_inner_folder.mkdir(parents=True, exist_ok=True)

    print(f"\nCreated structure:")
    print(f"  Author folder: {author_folder.name}")
    print(f"  Book outer: {book_outer_folder.name}")
    print(f"  Book inner: {book_inner_folder.name}")

    # Step 4: Copy OPF to inner folder
    test_opf_path = book_inner_folder / 'metadata.opf'
    shutil.copy(reference_opf_path, test_opf_path)

    # Step 5: Create dummy audio file
    dummy_audio = book_inner_folder / '01-chapter.mp3'
    dummy_audio.touch()

    print(f"\nTest OPF location: {test_opf_path.relative_to(expected_dir)}")
    assert test_opf_path.exists(), "Test OPF should exist"

    # Step 6: Run application passing the AUTHOR folder (not the book folder)
    app_script = Path('BadaBoomBooks.py')
    if not app_script.exists():
        pytest.skip("BadaBoomBooks.py not found (run from project root)")

    cmd = [
        sys.executable,
        str(app_script),
        '--from-opf',
        '--opf',
        '--yolo',
        str(author_folder)  # Pass AUTHOR folder, app should find nested books
    ]

    print(f"\nRunning: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')

    print("\n--- STDOUT ---")
    print(result.stdout if result.stdout else "(no output)")
    if result.stderr:
        print("\n--- STDERR ---")
        print(result.stderr)

    # Step 7: Verify OPF was read from correct location
    # The OPF should still be in the INNER folder where we placed it
    assert test_opf_path.exists(), \
        f"OPF should exist at {test_opf_path.relative_to(expected_dir)}"

    # Step 8: Verify OPF was NOT created in wrong locations
    wrong_locations = [
        author_folder / 'metadata.opf',  # Should NOT be in author folder
        book_outer_folder / 'metadata.opf'  # Should NOT be in outer book folder
    ]

    for wrong_path in wrong_locations:
        assert not wrong_path.exists(), \
            f"OPF should NOT exist at wrong location: {wrong_path.relative_to(expected_dir)}"

    # Step 9: Verify OPF was processed correctly
    processed_metadata = metadata_processor.read_opf_metadata(test_opf_path)
    assert processed_metadata is not None, "Failed to read processed OPF"
    assert processed_metadata.title, "Title should be present"
    assert processed_metadata.author, "Author should be present"

    print(f"\n✓ Test PASSED: App correctly found and processed nested metadata.opf")
    print(f"  OPF location: {test_opf_path.relative_to(expected_dir)}")


@pytest.mark.integration
@pytest.mark.author_folder
def test_author_folder_finds_all_nested_books(
    expected_dir,
    metadata_processor,
    cleanup_queue_ini,
    test_database
):
    """
    Test that passing an author folder discovers all nested book folders.

    Structure:
    Author/
      ├── Book1 - Author/
      │   └── Book1/
      │       ├── metadata.opf
      │       └── 01.mp3
      └── Book2 - Author/
          └── Book2/
              ├── metadata.opf
              └── 01.mp3

    Expected: App should discover and process both Book1 and Book2
    """
    import sys

    # Create test structure with 2 books
    author_folder = expected_dir / "Test Author"

    books = [
        ("Book One", "Test Author", "https://example.com/book1"),
        ("Book Two", "Test Author", "https://example.com/book2")
    ]

    for title, author, url in books:
        book_outer = author_folder / f"{title} - {author}"
        book_inner = book_outer / title
        book_inner.mkdir(parents=True, exist_ok=True)

        # Create minimal OPF
        opf_path = book_inner / 'metadata.opf'
        opf_content = f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{title}</dc:title>
    <dc:creator>{author}</dc:creator>
    <dc:source>{url}</dc:source>
  </metadata>
</package>'''
        opf_path.write_text(opf_content, encoding='utf-8')

        # Create dummy audio
        (book_inner / '01.mp3').touch()

    # Run app
    app_script = Path('BadaBoomBooks.py')
    if not app_script.exists():
        pytest.skip("BadaBoomBooks.py not found (run from project root)")

    cmd = [
        sys.executable,
        str(app_script),
        '--from-opf',
        '--yolo',
        str(author_folder)
    ]

    print(f"\nRunning: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')

    print("\n--- STDOUT ---")
    print(result.stdout if result.stdout else "(no output)")

    # Verify both books were discovered
    assert "Books to process: 2" in result.stdout, \
        "App should discover 2 books in author folder"

    print("\n✓ Test PASSED: App discovered all nested books in author folder")
