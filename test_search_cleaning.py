#!/usr/bin/env python3
"""
Test script for search term cleaning improvements.

Tests the new logic for:
1. Detecting garbage ID3 data like "1. I" or "2. A"
2. Deduplicating search terms when one is redundant
"""

from pathlib import Path
from src.utils.metadata_cleaning import (
    clean_id3_field,
    extract_metadata_from_sources,
    generate_search_alternatives,
    _is_redundant_search,
    _normalize_for_comparison
)


def test_clean_id3_field():
    """Test that garbage ID3 fields are properly rejected."""
    print("\n=== Testing clean_id3_field() ===")

    test_cases = [
        ("1. I", "", "Should reject: too short after removing numbers"),
        ("2. A", "", "Should reject: too short after removing numbers"),
        ("3. The", "3. The", "Should accept: 'The' has 3 letters (edge case, acceptable)"),
        ("1. Title", "1. Title", "Should accept: enough letters"),
        ("Karin Slaughter", "Karin Slaughter", "Should accept: valid author"),
        ("exsite.pl", "", "Should reject: domain name"),
        ("audiobook.com", "", "Should reject: audiobook marker"),
        ("", "", "Should reject: empty"),
        ("I", "", "Should reject: too short"),
        ("12", "", "Should reject: only numbers"),
    ]

    all_passed = True
    for input_val, expected, description in test_cases:
        result = clean_id3_field(input_val)
        passed = result == expected
        all_passed = all_passed and passed

        status = "✓" if passed else "✗"
        print(f"{status} {description}")
        print(f"  Input: '{input_val}' → Output: '{result}' (expected: '{expected}')")

    return all_passed


def test_is_redundant_search():
    """Test deduplication of search terms."""
    print("\n=== Testing _is_redundant_search() ===")

    test_cases = [
        ("Karin Slaughter", "Slaughter Karin - Moje sliczne czyta Filip Kosior 224kbps", True,
         "Author name is subset of folder name - redundant"),
        ("Title by Author", "Author - Title", True,
         "Same info in different format - redundant"),
        ("Book Title", "Different Author", False,
         "Completely different - not redundant"),
        ("Moje śliczne by Karin Slaughter", "Slaughter Karin - Moje sliczne czyta Filip Kosior", True,
         "ID3 term is subset of folder - redundant"),
    ]

    all_passed = True
    for term1, term2, expected, description in test_cases:
        result = _is_redundant_search(term1, term2)
        passed = result == expected
        all_passed = all_passed and passed

        status = "✓" if passed else "✗"
        print(f"{status} {description}")
        print(f"  Term1: '{term1}'")
        print(f"  Term2: '{term2}'")
        print(f"  Result: {result} (expected: {expected})")
        print(f"  Normalized: '{_normalize_for_comparison(term1)}' vs '{_normalize_for_comparison(term2)}'")

    return all_passed


def test_extract_metadata_from_sources():
    """Test metadata extraction with garbage detection."""
    print("\n=== Testing extract_metadata_from_sources() ===")

    # Case 1: Garbage ID3 data
    print("\nCase 1: Garbage ID3 title '1. I' with valid author")
    folder_path = Path("Slaughter Karin - Moje sliczne czyta Filip Kosior 224kbps")
    result = extract_metadata_from_sources(
        folder_path,
        id3_title="1. I",
        id3_author="Karin Slaughter",
        id3_album="Moje śliczne"
    )

    print(f"  Folder data valid: {result['folder']['valid']}")
    print(f"  Folder cleaned: '{result['folder']['cleaned']}'")
    print(f"  ID3 valid: {result['id3']['valid']}")
    print(f"  ID3 title cleaned: '{result['id3']['title']}'")
    print(f"  ID3 author cleaned: '{result['id3']['author']}'")
    print(f"  Garbage detected: {result['id3']['garbage_detected']}")

    # The ID3 title should be empty (rejected), making ID3 invalid
    if result['id3']['title'] == "" and not result['id3']['valid']:
        print("  ✓ Garbage ID3 title correctly rejected")
    else:
        print("  ✗ Garbage ID3 title should have been rejected")
        return False

    # Case 2: Valid ID3 data
    print("\nCase 2: Valid ID3 data")
    result2 = extract_metadata_from_sources(
        folder_path,
        id3_title="Moje śliczne",
        id3_author="Karin Slaughter"
    )

    print(f"  ID3 valid: {result2['id3']['valid']}")
    print(f"  ID3 title: '{result2['id3']['title']}'")
    print(f"  ID3 author: '{result2['id3']['author']}'")

    if result2['id3']['valid'] and result2['id3']['title'] == "Moje śliczne":
        print("  ✓ Valid ID3 data correctly accepted")
    else:
        print("  ✗ Valid ID3 data should have been accepted")
        return False

    return True


def test_generate_search_alternatives():
    """Test search alternative generation with deduplication."""
    print("\n=== Testing generate_search_alternatives() ===")

    # Case 1: Garbage ID3 title should result in folder-only search
    print("\nCase 1: Garbage ID3 title (1. I) - should use folder only")
    folder_path = Path("Slaughter Karin - Moje sliczne czyta Filip Kosior 224kbps")
    metadata = extract_metadata_from_sources(
        folder_path,
        id3_title="1. I",
        id3_author="Karin Slaughter",
        id3_album="Moje śliczne"
    )

    alternatives = generate_search_alternatives(metadata)
    print(f"  Number of alternatives: {len(alternatives)}")
    for i, alt in enumerate(alternatives):
        print(f"  [{i+1}] {alt['source']}: '{alt['term']}'")

    if len(alternatives) == 1 and alternatives[0]['source'] == 'folder':
        print("  ✓ Correctly generated only folder-based search")
    else:
        print("  ✗ Should have only 1 folder-based alternative")
        return False

    # Case 2: Valid ID3 but redundant with folder
    print("\nCase 2: Valid ID3 but author is already in folder name - should deduplicate")
    metadata2 = extract_metadata_from_sources(
        folder_path,
        id3_title="Moje śliczne",
        id3_author="Karin Slaughter"
    )

    alternatives2 = generate_search_alternatives(metadata2)
    print(f"  Number of alternatives: {len(alternatives2)}")
    for i, alt in enumerate(alternatives2):
        print(f"  [{i+1}] {alt['source']}: '{alt['term']}'")

    # Both should be present since the folder has extra info (narrator, bitrate)
    # But if they're too similar, deduplication should kick in

    # Case 3: Completely different ID3 and folder
    print("\nCase 3: ID3 and folder with different info - should keep both")
    folder_path3 = Path("Random Folder Name")
    metadata3 = extract_metadata_from_sources(
        folder_path3,
        id3_title="Completely Different Book",
        id3_author="Different Author"
    )

    alternatives3 = generate_search_alternatives(metadata3)
    print(f"  Number of alternatives: {len(alternatives3)}")
    for i, alt in enumerate(alternatives3):
        print(f"  [{i+1}] {alt['source']}: '{alt['term']}'")

    if len(alternatives3) == 2:
        print("  ✓ Correctly kept both alternatives (not redundant)")
    else:
        print("  ✗ Should have 2 alternatives when info is different")
        return False

    return True


def main():
    """Run all tests."""
    print("="*80)
    print("SEARCH TERM CLEANING TEST SUITE")
    print("="*80)

    results = []

    results.append(("clean_id3_field", test_clean_id3_field()))
    results.append(("is_redundant_search", test_is_redundant_search()))
    results.append(("extract_metadata_from_sources", test_extract_metadata_from_sources()))
    results.append(("generate_search_alternatives", test_generate_search_alternatives()))

    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")

    all_passed = all(result[1] for result in results)

    print("\n" + "="*80)
    if all_passed:
        print("✓ ALL TESTS PASSED")
    else:
        print("✗ SOME TESTS FAILED")
    print("="*80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(main())
