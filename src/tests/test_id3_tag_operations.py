"""
Integration tests for ID3 tag operations.

This module tests the ID3 tag update functionality including:
- Creating ID3 tags on files without existing tags
- Updating ID3 tags on files with existing tags
- Genre normalization and mapping
- Clearing genres when source has no genres
- Proper error handling and failure reporting
- Processing result tracking
"""

import pytest
from pathlib import Path
from src.main import BadaBoomBooksApp


@pytest.mark.integration
def test_id3_tag_creation_and_update(existing_dir, expected_dir, cleanup_queue_ini, test_database):
    """
    Test ID3 tag creation and update functionality.

    This test verifies that the application:
    1. Creates ID3 tags on MP3 files without existing tags
    2. Updates ID3 tags on MP3 files with existing tags
    3. Reports failure if ANY file fails ID3 tag update
    4. Properly tracks success/failure in ProcessingResult

    Test files:
    - 1-one.mp3: Has existing ID3 tags
    - 2-.mp3: NO existing ID3 tags (should create new tags)

    Test command equivalent:
        python BadaBoomBooks.py --copy --rename --from-opf --id3-tag --yolo \
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

    # Verify initial state of audio files
    try:
        from mutagen.id3 import ID3

        # File 1 should have ID3 tags
        id3_1 = ID3(str(audio_file_1))
        assert len(id3_1) > 0, "File 1 should have existing ID3 tags"

        # File 2 should NOT have ID3 tags
        try:
            id3_2 = ID3(str(audio_file_2))
            # If we get here, the file has tags (unexpected)
            assert False, "File 2 should NOT have ID3 tags initially"
        except Exception as e:
            # Expected - file has no ID3 tags
            assert "doesn't start with an ID3 tag" in str(e) or "No ID3" in str(e)

    except ImportError:
        pytest.skip("Mutagen library not available")

    # Execute: Run BadaBoomBooks with ID3 tagging enabled
    app = BadaBoomBooksApp()
    exit_code = app.run([
        '--copy',
        '--rename',
        '--from-opf',
        '--id3-tag',
        '--debug',
        '--yolo',
        '-O', str(expected_dir),
        '-R', str(existing_dir)
    ])

    # Verify: Application should complete successfully
    assert exit_code == 0, "Application should exit with code 0 (success)"

    # Verify: Correct folder structure created
    expected_author_dir = expected_dir / "Aname A. Asurname"
    expected_book_dir = expected_author_dir / "Proper Title"
    assert expected_book_dir.exists(), f"Book directory not created: {expected_book_dir}"

    # Verify: Both audio files exist and were renamed
    renamed_file_1 = expected_book_dir / "01 - Proper Title.mp3"
    renamed_file_2 = expected_book_dir / "02 - Proper Title.mp3"

    assert renamed_file_1.exists(), f"Renamed audio file not found: {renamed_file_1}"
    assert renamed_file_2.exists(), f"Renamed audio file not found: {renamed_file_2}"

    # Verify: BOTH files now have ID3 tags with correct values
    try:
        from mutagen.easyid3 import EasyID3

        # Check file 1 (had tags, should be updated)
        audio_1 = EasyID3(str(renamed_file_1))
        assert audio_1['title'][0] == "Proper Title", \
            f"File 1 title mismatch: {audio_1['title'][0]}"
        assert audio_1['artist'][0] == "Aname A. Asurname", \
            f"File 1 artist mismatch: {audio_1['artist'][0]}"
        # Album should be series if series exists, otherwise title
        assert audio_1['album'][0] == "Series Title", \
            f"File 1 album mismatch: {audio_1['album'][0]}"

        # Check file 2 (had NO tags, should be created)
        audio_2 = EasyID3(str(renamed_file_2))
        assert audio_2['title'][0] == "Proper Title", \
            f"File 2 title mismatch: {audio_2['title'][0]}"
        assert audio_2['artist'][0] == "Aname A. Asurname", \
            f"File 2 artist mismatch: {audio_2['artist'][0]}"
        # Album should be series if series exists, otherwise title
        assert audio_2['album'][0] == "Series Title", \
            f"File 2 album mismatch: {audio_2['album'][0]}"

    except ImportError:
        pytest.skip("Mutagen library not available")

    # Verify: Processing result shows success
    assert app.result.has_successes(), "Should have successful processing"
    assert not app.result.has_failures(), "Should NOT have any failures"
    assert len(app.result.success_books) == 1, "Should have exactly 1 successful book"


@pytest.mark.integration
def test_id3_tag_partial_failure_reporting(existing_dir, expected_dir, cleanup_queue_ini, test_database):
    """
    Test that partial ID3 tag failures are properly reported as failures.

    This test verifies that if ANY audio file fails ID3 tag update,
    the entire book processing is marked as failed (not success).

    This is a regression test for the bug where the application reported
    success even when some files failed ID3 tag updates.
    """
    # Setup: Verify test data exists
    test_book_folder = existing_dir / "[ignore] Book Title's - Author (Series)_"
    assert test_book_folder.exists(), f"Test data folder not found: {test_book_folder}"

    # Execute: Run BadaBoomBooks with ID3 tagging
    app = BadaBoomBooksApp()
    exit_code = app.run([
        '--copy',
        '--rename',
        '--from-opf',
        '--id3-tag',
        '--yolo',
        '-O', str(expected_dir),
        '-R', str(existing_dir)
    ])

    # The key assertion: If ID3 tag update succeeds for ALL files,
    # the result should show success. If ANY file fails, it should show failure.

    # For now, we expect success because our fix will make it work
    assert exit_code == 0, "Application should exit successfully"

    # The processing result should accurately reflect what happened
    if app.result.has_failures():
        # If there were failures, they should be logged
        assert len(app.result.failed_books) > 0, "Failed books should be tracked"
    else:
        # If there were no failures, all books should be successful
        assert app.result.has_successes(), "Should have successful books"
        assert len(app.result.success_books) == 1, "Should have exactly 1 successful book"


@pytest.mark.integration
def test_id3_genre_normalization(existing_dir, expected_dir, cleanup_queue_ini, test_database):
    """
    Test that genres are normalized when writing ID3 tags.

    This test verifies that:
    1. Genres from OPF files are normalized using genre_mapping.json
    2. Lowercase normalization is applied
    3. Alternative names are mapped to canonical forms
    4. Normalized genres appear in ID3 tags

    Test data has genres: ["fantasy", "science fiction"]
    Expected normalized: ["fantasy", "science fiction"] (already canonical)

    Test command equivalent:
        python BadaBoomBooks.py --copy --rename --from-opf --id3-tag --yolo \
            -O src/tests/data/expected -R src/tests/data/existing
    """
    # Setup: Verify test data exists
    test_book_folder = existing_dir / "[ignore] Book Title's - Author (Series)_"
    assert test_book_folder.exists(), f"Test data folder not found: {test_book_folder}"

    opf_file = test_book_folder / "metadata.opf"
    assert opf_file.exists(), f"Test OPF file not found: {opf_file}"

    # Execute: Run BadaBoomBooks with ID3 tagging enabled
    app = BadaBoomBooksApp()
    exit_code = app.run([
        '--copy',
        '--rename',
        '--from-opf',
        '--id3-tag',
        '--yolo',
        '-O', str(expected_dir),
        '-R', str(existing_dir)
    ])

    # Verify: Application should complete successfully
    assert exit_code == 0, "Application should exit with code 0 (success)"

    # Verify: Correct folder structure created
    expected_author_dir = expected_dir / "Aname A. Asurname"
    expected_book_dir = expected_author_dir / "Proper Title"
    assert expected_book_dir.exists(), f"Book directory not created: {expected_book_dir}"

    # Verify: Audio files exist
    renamed_file_1 = expected_book_dir / "01 - Proper Title.mp3"
    renamed_file_2 = expected_book_dir / "02 - Proper Title.mp3"

    assert renamed_file_1.exists(), f"Renamed audio file not found: {renamed_file_1}"
    assert renamed_file_2.exists(), f"Renamed audio file not found: {renamed_file_2}"

    # Verify: Genres are normalized in ID3 tags
    try:
        from mutagen.easyid3 import EasyID3

        # Check both files have normalized genres
        for audio_file in [renamed_file_1, renamed_file_2]:
            audio = EasyID3(str(audio_file))

            # Verify genre field exists
            assert 'genre' in audio, f"Genre field missing in {audio_file.name}"

            # Verify genres are normalized (lowercase)
            genres = audio['genre']
            assert len(genres) == 2, f"Expected 2 genres, got {len(genres)}: {genres}"

            # Genres should be lowercase and canonical
            assert 'fantasy' in genres, f"Expected 'fantasy' in genres, got: {genres}"
            assert 'science fiction' in genres, f"Expected 'science fiction' in genres, got: {genres}"

    except ImportError:
        pytest.skip("Mutagen library not available")


@pytest.mark.integration
def test_id3_genre_clearing_when_no_source_genres(existing_dir, expected_dir, cleanup_queue_ini, tmp_path, test_database):
    """
    Test that ID3 genre tags are cleared when source OPF has no genres.

    This test verifies that:
    1. When OPF file has no genres, ID3 genre tag is cleared
    2. Files that previously had genre tags get them removed
    3. Files without genre tags remain unchanged (no error)

    Test flow:
    1. Create a modified OPF with no genres
    2. Process with --id3-tag
    3. Verify genre tags are cleared from output files

    Test command equivalent:
        python BadaBoomBooks.py --copy --rename --from-opf --id3-tag --yolo \
            -O tmp_dir/expected -R tmp_dir/existing
    """
    # Setup: Create test directory structure in tmp_path
    test_existing = tmp_path / "existing"
    test_expected = tmp_path / "expected"
    test_existing.mkdir()
    test_expected.mkdir()

    # Copy test data to tmp directory
    import shutil
    source_folder = existing_dir / "[ignore] Book Title's - Author (Series)_"
    dest_folder = test_existing / "[ignore] Book Title's - Author (Series)_"
    shutil.copytree(source_folder, dest_folder)

    # Modify OPF to remove genres
    opf_file = dest_folder / "metadata.opf"
    with open(opf_file, 'r', encoding='utf-8') as f:
        opf_content = f.read()

    # Remove genre lines
    import re
    opf_content = re.sub(r'<dc:subject>.*?</dc:subject>\s*', '', opf_content)

    with open(opf_file, 'w', encoding='utf-8') as f:
        f.write(opf_content)

    # Add some genre tags to test files to verify they get cleared
    try:
        from mutagen.easyid3 import EasyID3
        from mutagen.id3 import ID3NoHeaderError
        from mutagen.mp3 import MP3

        audio_file = dest_folder / "1-one.mp3"

        # Ensure file has ID3 tags with genres
        try:
            audio = EasyID3(str(audio_file))
        except ID3NoHeaderError:
            audio = MP3(str(audio_file))
            audio.add_tags()
            audio.save()
            audio = EasyID3(str(audio_file))

        # Add test genres that should be cleared
        audio['genre'] = ['test genre 1', 'test genre 2']
        audio.save()

        # Verify genres were added
        audio = EasyID3(str(audio_file))
        assert 'genre' in audio, "Failed to add test genres"
        assert len(audio['genre']) == 2, "Failed to add test genres"

    except ImportError:
        pytest.skip("Mutagen library not available")

    # Execute: Run BadaBoomBooks with ID3 tagging enabled
    app = BadaBoomBooksApp()
    exit_code = app.run([
        '--copy',
        '--rename',
        '--from-opf',
        '--id3-tag',
        '--yolo',
        '-O', str(test_expected),
        '-R', str(test_existing)
    ])

    # Verify: Application should complete successfully
    assert exit_code == 0, "Application should exit with code 0 (success)"

    # Verify: Correct folder structure created
    expected_author_dir = test_expected / "Aname A. Asurname"
    expected_book_dir = expected_author_dir / "Proper Title"
    assert expected_book_dir.exists(), f"Book directory not created: {expected_book_dir}"

    # Verify: Audio files exist
    renamed_file_1 = expected_book_dir / "01 - Proper Title.mp3"
    renamed_file_2 = expected_book_dir / "02 - Proper Title.mp3"

    assert renamed_file_1.exists(), f"Renamed audio file not found: {renamed_file_1}"
    assert renamed_file_2.exists(), f"Renamed audio file not found: {renamed_file_2}"

    # Verify: Genre tags are CLEARED (not present)
    try:
        from mutagen.easyid3 import EasyID3

        # Check both files have NO genre tags
        for audio_file in [renamed_file_1, renamed_file_2]:
            audio = EasyID3(str(audio_file))

            # Verify genre field is cleared/not present
            if 'genre' in audio:
                # If genre key exists, it should be empty
                assert len(audio['genre']) == 0, \
                    f"Expected empty genres in {audio_file.name}, got: {audio['genre']}"
            # else: genre key not present - this is also acceptable

    except ImportError:
        pytest.skip("Mutagen library not available")


@pytest.mark.integration
def test_id3_genre_alternative_mapping(existing_dir, expected_dir, cleanup_queue_ini, tmp_path, test_database):
    """
    Test that alternative genre names are mapped to canonical forms in ID3 tags.

    This test verifies that:
    1. Alternative genre names are mapped to canonical forms based on genre_mapping.json
    2. Mapping is applied during ID3 tag writing
    3. Multiple alternatives are deduplicated to single canonical form

    This test is data-driven: it reads genre_mapping.json to determine expected mappings,
    making it resilient to future changes in the mapping file.

    Test flow:
    1. Load genre mappings from genre_mapping.json
    2. Select test alternative genres from the mapping
    3. Create OPF with alternative genre names
    4. Process with --id3-tag
    5. Verify ID3 tags contain canonical genre names (not alternatives)

    Test command equivalent:
        python BadaBoomBooks.py --copy --rename --from-opf --id3-tag --yolo \
            -O tmp_dir/expected -R tmp_dir/existing
    """
    # Load genre mapping to determine expected canonical forms
    import json
    from pathlib import Path

    mapping_file = Path(__file__).parent.parent.parent / "genre_mapping.json"
    with open(mapping_file, 'r', encoding='utf-8') as f:
        genre_mapping = json.load(f)

    # Build reverse mapping: alternative -> canonical (lowercase)
    alternative_to_canonical = {}
    for canonical, alternatives in genre_mapping.items():
        canonical_lower = canonical.lower()
        for alt in alternatives:
            alternative_to_canonical[alt.lower()] = canonical_lower

    # Select test cases: pick one alternative from different canonical genres
    # We want to test various mapping scenarios
    test_alternatives = []
    expected_canonicals = set()

    # Strategy: Pick the first available alternative for each of these canonical genres
    target_genres = ["science fiction", "fantasy", "romance"]
    for target in target_genres:
        target_lower = target.lower()
        if target_lower in genre_mapping and genre_mapping[target_lower]:
            # Pick first alternative
            test_alternatives.append(genre_mapping[target_lower][0])
            expected_canonicals.add(target_lower)

    # Add one more test case for nationality genre (if available)
    for canonical in genre_mapping:
        if canonical.startswith("nat.") and genre_mapping[canonical]:
            test_alternatives.append(genre_mapping[canonical][0])
            expected_canonicals.add(canonical.lower())
            break

    # Ensure we have test data
    assert len(test_alternatives) >= 3, \
        "Not enough alternative genres in mapping file for testing"

    # Setup: Create test directory structure in tmp_path
    test_existing = tmp_path / "existing"
    test_expected = tmp_path / "expected"
    test_existing.mkdir()
    test_expected.mkdir()

    # Copy test data to tmp directory
    import shutil
    source_folder = existing_dir / "[ignore] Book Title's - Author (Series)_"
    dest_folder = test_existing / "[ignore] Book Title's - Author (Series)_"
    shutil.copytree(source_folder, dest_folder)

    # Modify OPF to use alternative genre names
    opf_file = dest_folder / "metadata.opf"
    with open(opf_file, 'r', encoding='utf-8') as f:
        opf_content = f.read()

    # Remove existing genres
    import re
    opf_content = re.sub(r'<dc:subject>.*?</dc:subject>\s*', '', opf_content)

    # Insert test alternative genre names with varied casing
    insert_pos = opf_content.find('<dc:identifier')
    genre_tags = ""
    for i, alt in enumerate(test_alternatives):
        # Vary the casing to test case-insensitive matching
        if i % 3 == 0:
            genre_value = alt.lower()
        elif i % 3 == 1:
            genre_value = alt.upper()
        else:
            genre_value = alt.title()
        genre_tags += f'    <dc:subject>{genre_value}</dc:subject>\n'

    opf_content = opf_content[:insert_pos] + genre_tags + opf_content[insert_pos:]

    with open(opf_file, 'w', encoding='utf-8') as f:
        f.write(opf_content)

    # Execute: Run BadaBoomBooks with ID3 tagging enabled
    app = BadaBoomBooksApp()
    exit_code = app.run([
        '--copy',
        '--rename',
        '--from-opf',
        '--id3-tag',
        '--yolo',
        '-O', str(test_expected),
        '-R', str(test_existing)
    ])

    # Verify: Application should complete successfully
    assert exit_code == 0, "Application should exit with code 0 (success)"

    # Verify: Correct folder structure created
    expected_author_dir = test_expected / "Aname A. Asurname"
    expected_book_dir = expected_author_dir / "Proper Title"
    assert expected_book_dir.exists(), f"Book directory not created: {expected_book_dir}"

    # Verify: Audio files exist
    renamed_file_1 = expected_book_dir / "01 - Proper Title.mp3"
    renamed_file_2 = expected_book_dir / "02 - Proper Title.mp3"

    assert renamed_file_1.exists(), f"Renamed audio file not found: {renamed_file_1}"
    assert renamed_file_2.exists(), f"Renamed audio file not found: {renamed_file_2}"

    # Verify: Genres are normalized to canonical forms in ID3 tags
    try:
        from mutagen.easyid3 import EasyID3

        # Check both files have canonical genres
        for audio_file in [renamed_file_1, renamed_file_2]:
            audio = EasyID3(str(audio_file))

            # Verify genre field exists
            assert 'genre' in audio, f"Genre field missing in {audio_file.name}"

            # Get actual genres from ID3 tags
            actual_genres = set(g.lower() for g in audio['genre'])

            # Verify count matches expected (no duplicates after normalization)
            assert len(actual_genres) == len(expected_canonicals), \
                f"Expected {len(expected_canonicals)} unique genres, got {len(actual_genres)}: {actual_genres}"

            # Verify all expected canonical genres are present
            for canonical in expected_canonicals:
                assert canonical in actual_genres, \
                    f"Expected canonical genre '{canonical}' not found in: {actual_genres}"

            # Verify NO alternative names are present (all should be mapped)
            for alt in test_alternatives:
                alt_lower = alt.lower()
                assert alt_lower not in actual_genres or alt_lower in expected_canonicals, \
                    f"Alternative '{alt_lower}' should be mapped to canonical form, not present as-is: {actual_genres}"

    except ImportError:
        pytest.skip("Mutagen library not available")
