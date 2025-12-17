"""
Tests for genre normalization and mapping functionality.
"""

import pytest
import json
from pathlib import Path
from src.utils.genre_normalizer import GenreNormalizer, normalize_genres


@pytest.fixture
def temp_mapping_file(tmp_path):
    """Create a temporary genre mapping file for testing."""
    mapping_file = tmp_path / "test_genre_mapping.json"
    test_mapping = {
        "romance": ["romans", "romantasy", "love"],
        "science fiction": ["sci-fy", "sci-fi", "sf", "space"],
        "fantasy": ["fantastyka"],
        "poland": ["polska", "polish"],
        "horror": []
    }
    with open(mapping_file, 'w', encoding='utf-8') as f:
        json.dump(test_mapping, f, ensure_ascii=False)
    return mapping_file


@pytest.fixture
def normalizer(temp_mapping_file):
    """Create a GenreNormalizer instance with test mapping."""
    return GenreNormalizer(mapping_file=temp_mapping_file)


class TestGenreNormalizer:
    """Test the GenreNormalizer class."""

    def test_initialization_with_custom_file(self, temp_mapping_file):
        """Test that normalizer loads custom mapping file correctly."""
        normalizer = GenreNormalizer(mapping_file=temp_mapping_file)
        assert normalizer.mapping_file == temp_mapping_file
        assert "romance" in normalizer.mapping
        assert "science fiction" in normalizer.mapping

    def test_initialization_creates_default_if_missing(self, tmp_path):
        """Test that normalizer creates default mapping if file doesn't exist."""
        missing_file = tmp_path / "nonexistent.json"
        normalizer = GenreNormalizer(mapping_file=missing_file)
        assert missing_file.exists()
        # Should have created file with default mapping
        with open(missing_file, 'r', encoding='utf-8') as f:
            mapping = json.load(f)
        assert isinstance(mapping, dict)

    def test_lowercase_normalization(self, normalizer):
        """Test that all genres are lowercased."""
        result = normalizer.normalize_genres(["Horror", "ROMANCE", "ScIeNcE FiCtIoN"])
        assert result == ["horror", "romance", "science fiction"]

    def test_alternative_mapping(self, normalizer):
        """Test that alternatives are mapped to canonical forms."""
        # "romans" should map to "romance"
        result = normalizer.normalize_genres(["romans"])
        assert result == ["romance"]

        # "sci-fi" should map to "science fiction"
        result = normalizer.normalize_genres(["sci-fi", "Sci-Fy", "SF"])
        assert result == ["science fiction"]

        # "polska" should map to "poland"
        result = normalizer.normalize_genres(["Polska", "POLISH"])
        assert result == ["poland"]

    def test_deduplication(self, normalizer):
        """Test that duplicate genres are removed."""
        # Direct duplicates
        result = normalizer.normalize_genres(["Horror", "horror", "HORROR"])
        assert result == ["horror"]

        # Duplicates via mapping
        result = normalizer.normalize_genres(["Romance", "romans", "love", "ROMANTASY"])
        assert result == ["romance"]

    def test_order_preservation(self, normalizer):
        """Test that first occurrence order is preserved."""
        result = normalizer.normalize_genres(["fantasy", "horror", "romance", "horror"])
        assert result == ["fantasy", "horror", "romance"]

    def test_mixed_canonical_and_alternatives(self, normalizer):
        """Test handling of mixed canonical and alternative genres."""
        result = normalizer.normalize_genres(["romance", "sci-fi", "Horror", "polska"])
        assert result == ["romance", "science fiction", "horror", "poland"]

    def test_unknown_genres_pass_through(self, normalizer):
        """Test that unknown genres are added as new canonical forms."""
        result = normalizer.normalize_genres(["unknown genre", "brand new", "never seen before"])
        assert result == ["unknown genre", "brand new", "never seen before"]

    def test_empty_list(self, normalizer):
        """Test handling of empty genre list."""
        result = normalizer.normalize_genres([])
        assert result == []

    def test_none_and_empty_strings(self, normalizer):
        """Test handling of None and empty string entries."""
        result = normalizer.normalize_genres(["horror", "", "  ", "romance", None])
        # Should filter out empty/None values
        assert result == ["horror", "romance"]

    def test_whitespace_handling(self, normalizer):
        """Test that leading/trailing whitespace is stripped."""
        result = normalizer.normalize_genres(["  horror  ", " romance ", "fantasy"])
        assert result == ["horror", "romance", "fantasy"]

    def test_case_insensitive_mapping(self, normalizer):
        """Test that mapping works regardless of input case."""
        # All should map to "science fiction"
        inputs = ["Sci-Fi", "SCI-FY", "sf", "SF", "ScI-fI"]
        for genre_input in inputs:
            result = normalizer.normalize_genres([genre_input])
            assert result == ["science fiction"]

    def test_complex_scenario(self, normalizer):
        """Test a complex real-world scenario with multiple mappings and duplicates."""
        input_genres = [
            "Fantasy",           # canonical
            "Horror",            # canonical
            "sci-fi",            # maps to "science fiction"
            "Polska",            # maps to "poland"
            "romance",           # canonical
            "romans",            # maps to "romance" (duplicate)
            "HORROR",            # duplicate of horror
            "Space",             # maps to "science fiction" (duplicate)
            "unknown",           # new genre
            "",                  # should be filtered
            "  ",                # should be filtered
        ]
        result = normalizer.normalize_genres(input_genres)
        expected = ["fantasy", "horror", "science fiction", "poland", "romance", "unknown"]
        assert result == expected

    def test_canonical_genre_with_empty_alternatives(self, normalizer):
        """Test that canonical genres with no alternatives (like 'horror': []) work correctly."""
        result = normalizer.normalize_genres(["horror", "Horror", "HORROR"])
        assert result == ["horror"]


class TestGenreNormalizerAddMapping:
    """Test the add_mapping and save_mapping functionality."""

    def test_add_new_mapping(self, normalizer, temp_mapping_file):
        """Test adding a new genre mapping."""
        normalizer.add_mapping("adventure", ["action", "quest"])
        assert "adventure" in normalizer.mapping
        assert "action" in normalizer.mapping["adventure"]
        assert "quest" in normalizer.mapping["adventure"]

    def test_update_existing_mapping(self, normalizer):
        """Test updating an existing genre mapping."""
        # Romance already has ["romans", "romantasy", "love"]
        normalizer.add_mapping("romance", ["romantic comedy"])
        assert "romantic comedy" in normalizer.mapping["romance"]
        # Old alternatives should still be there
        assert "romans" in normalizer.mapping["romance"]
        assert "love" in normalizer.mapping["romance"]

    def test_add_mapping_normalizes_case(self, normalizer):
        """Test that add_mapping lowercases all inputs."""
        normalizer.add_mapping("ADVENTURE", ["ACTION", "Quest"])
        assert "adventure" in normalizer.mapping
        assert "action" in normalizer.mapping["adventure"]
        assert "quest" in normalizer.mapping["adventure"]

    def test_save_mapping(self, normalizer, temp_mapping_file):
        """Test saving mapping to file."""
        normalizer.add_mapping("adventure", ["action"])
        normalizer.save_mapping()

        # Load the file and verify
        with open(temp_mapping_file, 'r', encoding='utf-8') as f:
            saved_mapping = json.load(f)

        assert "adventure" in saved_mapping
        assert "action" in saved_mapping["adventure"]


class TestGlobalNormalizeFunction:
    """Test the module-level normalize_genres function."""

    def test_global_function_uses_default_mapping(self):
        """Test that the global function works with default mapping file."""
        # This will use genre_mapping.json from project root
        result = normalize_genres(["Horror", "ROMANCE", "sci-fi"])
        # Should lowercase at minimum
        assert all(genre.islower() for genre in result)
        # Should deduplicate
        assert len(result) == len(set(result))


class TestIntegrationWithOPF:
    """Integration tests simulating real OPF writing scenarios."""

    def test_goodreads_genres(self, normalizer):
        """Test normalization of typical Goodreads scraped genres."""
        goodreads_genres = ["Fantasy", "Science Fiction", "Horror", "Young Adult"]
        result = normalizer.normalize_genres(goodreads_genres)
        assert "fantasy" in result
        assert "science fiction" in result
        assert "horror" in result

    def test_lubimyczytac_genres(self, normalizer):
        """Test normalization of typical LubimyCzytac scraped genres."""
        lubimyczytac_genres = ["Fantastyka", "Horror", "Polska"]
        result = normalizer.normalize_genres(lubimyczytac_genres)
        assert result == ["fantasy", "horror", "poland"]

    def test_mixed_source_genres(self, normalizer):
        """Test genres from multiple sources that should deduplicate."""
        # Goodreads says "Fantasy", LubimyCzytac says "Fantastyka"
        mixed_genres = ["Fantasy", "Fantastyka", "Horror"]
        result = normalizer.normalize_genres(mixed_genres)
        assert result == ["fantasy", "horror"]  # Should deduplicate fantasy

    def test_audible_genres(self, normalizer):
        """Test normalization of typical Audible genres."""
        audible_genres = ["Sci-Fi & Fantasy", "Horror", "Mystery, Thriller & Suspense"]
        # Note: "Sci-Fi & Fantasy" won't match exact mapping, becomes new canonical
        result = normalizer.normalize_genres(audible_genres)
        assert "horror" in result
        # Check that it's lowercased at least
        assert all(genre.islower() for genre in result)


class TestUTF8Support:
    """Test that UTF-8 characters (like Polish) are handled correctly."""

    def test_polish_characters_in_genres(self, normalizer):
        """Test that Polish characters (ą, ę, ć, etc.) work correctly."""
        polish_genres = ["Fantastyka", "Komedia", "Książka polska"]
        result = normalizer.normalize_genres(polish_genres)
        # Should lowercase and preserve Polish characters
        assert "fantastyka" in result or "fantasy" in result
        assert all(isinstance(genre, str) for genre in result)

    def test_save_and_load_utf8(self, tmp_path):
        """Test that UTF-8 characters are preserved when saving/loading."""
        mapping_file = tmp_path / "utf8_test.json"
        test_mapping = {
            "komedia": ["śmieszne", "zabawne"],
            "polska": ["książka polska"]
        }

        # Save with UTF-8
        with open(mapping_file, 'w', encoding='utf-8') as f:
            json.dump(test_mapping, f, ensure_ascii=False)

        # Load and verify
        normalizer = GenreNormalizer(mapping_file=mapping_file)
        assert "komedia" in normalizer.mapping
        assert "śmieszne" in normalizer.mapping["komedia"]


@pytest.mark.integration
class TestEndToEndScenario:
    """End-to-end integration test simulating full processing."""

    def test_full_audiobook_processing_flow(self, normalizer):
        """
        Simulate the full flow:
        1. Scraper extracts genres
        2. Genres stored in BookMetadata
        3. Genres normalized when writing to OPF
        """
        # Step 1: Scraped genres (mixed case, duplicates, alternatives)
        scraped_genres = ["Fantasy", "Sci-Fi", "HORROR", "romans", "space", "Fantasy"]

        # Step 2: Stored in metadata as comma-separated string
        genres_string = ",".join(scraped_genres)

        # Step 3: Convert to list (like get_genres_list())
        genres_list = [g.strip() for g in genres_string.split(',') if g.strip()]

        # Step 4: Normalize (like _format_genres_for_opf())
        normalized = normalizer.normalize_genres(genres_list)

        # Verify final result
        expected = ["fantasy", "science fiction", "horror", "romance"]
        assert normalized == expected
