"""
Quick test script for metadata cleaning functionality.
Run this to validate the new metadata extraction and cleaning logic.
"""

from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.utils.metadata_cleaning import (
    is_garbage_data,
    is_duplicate_fields,
    clean_folder_name,
    clean_id3_field,
    extract_metadata_from_sources,
    generate_search_alternatives
)


def test_garbage_detection():
    """Test garbage data detection."""
    print("\n=== Testing Garbage Detection ===")

    test_cases = [
        ("exsite.pl", True, "Domain name"),
        ("audiobook.com", True, "Domain name"),
        ("Harry Potter", False, "Valid title"),
        ("Martha Wells", False, "Valid author"),
        ("www.example.com", True, "URL"),
        ("https://test.pl", True, "URL with protocol"),
        ("", True, "Empty string"),
        ("ab", True, "Too short"),
    ]

    for text, should_be_garbage, description in test_cases:
        result = is_garbage_data(text)
        status = "✓" if result == should_be_garbage else "✗"
        print(f"  {status} '{text}' ({description}): {result}")


def test_duplicate_detection():
    """Test duplicate field detection."""
    print("\n=== Testing Duplicate Field Detection ===")

    test_cases = [
        ("exsite.pl", "exsite.pl", True, "Identical garbage"),
        ("Book Title", "Author Name", False, "Different values"),
        ("Title", "TITLE", True, "Case-insensitive match"),
        (None, "Author", False, "None value"),
    ]

    for title, author, should_match, description in test_cases:
        result = is_duplicate_fields(title, author)
        status = "✓" if result == should_match else "✗"
        print(f"  {status} {description}: {result}")


def test_folder_cleaning():
    """Test folder name cleaning."""
    print("\n=== Testing Folder Name Cleaning ===")

    test_cases = [
        ("[AudioBook] Frankiewicz Janusz - Gorejące ognie", "Frankiewicz Janusz Gorejące ognie"),
        ("Author - Title (Series #1) [2023]", "Author Title Series #1"),
        ("Martha Wells - Wszystkie wskaźniki czerwone", "Martha Wells Wszystkie wskaźniki czerwone"),
    ]

    for input_text, expected in test_cases:
        result = clean_folder_name(input_text)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{input_text}'")
        print(f"      → '{result}'")
        if result != expected:
            print(f"      Expected: '{expected}'")


def test_id3_cleaning():
    """Test ID3 field cleaning."""
    print("\n=== Testing ID3 Field Cleaning ===")

    test_cases = [
        ("exsite.pl", "", "Domain name (garbage)"),
        ("Harry Potter", "Harry Potter", "Valid title"),
        ("audiobook.com", "", "Domain (garbage)"),
        ("  Spaced Title  ", "Spaced Title", "Trimmed spaces"),
    ]

    for input_text, expected, description in test_cases:
        result = clean_id3_field(input_text)
        status = "✓" if result == expected else "✗"
        print(f"  {status} {description}:")
        print(f"      '{input_text}' → '{result}'")


def test_metadata_extraction():
    """Test complete metadata extraction."""
    print("\n=== Testing Metadata Extraction ===")

    # Case 1: Garbage ID3 + Good folder name (your failing case)
    print("\n  Case 1: Garbage ID3 + Good Folder Name")
    folder_path = Path("Frankiewicz Janusz - Gorejące ognie")
    result = extract_metadata_from_sources(
        folder_path=folder_path,
        id3_title="exsite.pl",
        id3_author="exsite.pl",
        id3_album="exsite.pl"
    )

    print(f"    Folder data:")
    print(f"      Raw: {result['folder']['raw']}")
    print(f"      Cleaned: {result['folder']['cleaned']}")
    print(f"      Valid: {result['folder']['valid']}")

    print(f"    ID3 data:")
    print(f"      Title: '{result['id3']['title']}'")
    print(f"      Author: '{result['id3']['author']}'")
    print(f"      Valid: {result['id3']['valid']}")
    print(f"      Garbage detected: {result['id3']['garbage_detected']}")

    # Case 2: Good ID3 + Good folder name
    print("\n  Case 2: Good ID3 + Good Folder Name")
    result2 = extract_metadata_from_sources(
        folder_path=Path("Some Folder Name"),
        id3_title="Harry Potter and the Philosopher's Stone",
        id3_author="J.K. Rowling",
        id3_album="Harry Potter"
    )

    print(f"    ID3 data:")
    print(f"      Title: '{result2['id3']['title']}'")
    print(f"      Author: '{result2['id3']['author']}'")
    print(f"      Valid: {result2['id3']['valid']}")
    print(f"      Garbage detected: {result2['id3']['garbage_detected']}")


def test_search_alternatives():
    """Test search alternative generation."""
    print("\n=== Testing Search Alternative Generation ===")

    # Case 1: Garbage ID3 (should only use folder)
    print("\n  Case 1: Garbage ID3 - Should Use Folder Only")
    metadata1 = {
        'folder': {
            'raw': 'Frankiewicz Janusz - Gorejące ognie',
            'cleaned': 'Frankiewicz Janusz Gorejące ognie',
            'valid': True
        },
        'id3': {
            'title': '',
            'author': '',
            'valid': False,
            'garbage_detected': True
        }
    }

    alternatives1 = generate_search_alternatives(metadata1)
    print(f"    Generated {len(alternatives1)} alternative(s):")
    for alt in alternatives1:
        print(f"      [{alt['priority']}] {alt['source']}: {alt['term']}")

    # Case 2: Good ID3 (should use both)
    print("\n  Case 2: Good ID3 - Should Use Both Sources")
    metadata2 = {
        'folder': {
            'raw': 'Some Folder',
            'cleaned': 'Some Folder',
            'valid': True
        },
        'id3': {
            'title': 'Harry Potter',
            'author': 'J.K. Rowling',
            'valid': True,
            'garbage_detected': False
        }
    }

    alternatives2 = generate_search_alternatives(metadata2)
    print(f"    Generated {len(alternatives2)} alternative(s):")
    for alt in alternatives2:
        print(f"      [{alt['priority']}] {alt['source']}: {alt['term']}")


def main():
    """Run all tests."""
    print("=" * 70)
    print("METADATA CLEANING VALIDATION TESTS")
    print("=" * 70)

    test_garbage_detection()
    test_duplicate_detection()
    test_folder_cleaning()
    test_id3_cleaning()
    test_metadata_extraction()
    test_search_alternatives()

    print("\n" + "=" * 70)
    print("TESTS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
