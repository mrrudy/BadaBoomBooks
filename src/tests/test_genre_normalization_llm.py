"""
Tests for LLM-based genre categorization.

This module tests the LLM integration for automatic genre categorization,
including connection testing, categorization logic, and error handling.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from src.utils.genre_normalizer import GenreNormalizer


@pytest.fixture
def temp_mapping_file(tmp_path):
    """Create a temporary genre mapping file."""
    mapping_file = tmp_path / "genre_mapping.json"
    mapping = {
        "science fiction": ["sci-fi", "sf"],
        "fantasy": ["fantastyka"],
        "romance": ["romans"],
        "mystery": ["thriller", "crime"]
    }
    with open(mapping_file, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False)
    return mapping_file


@pytest.fixture
def mock_llm_config():
    """Mock LLM configuration."""
    # LLM_CONFIG is imported inside methods, so we need to patch it in config module
    with patch('src.config.LLM_CONFIG', {
        'enabled': True,
        'api_key': 'test-key',
        'model': 'gpt-3.5-turbo',
        'base_url': None,
        'max_tokens': 100
    }):
        yield


class TestLLMConnection:
    """Tests for LLM connection and initialization."""

    def test_llm_disabled_when_no_api_key(self, temp_mapping_file):
        """Test that LLM is disabled when no API key is configured."""
        with patch('src.config.LLM_CONFIG', {'enabled': False, 'api_key': None}):
            normalizer = GenreNormalizer(mapping_file=temp_mapping_file, use_llm=True)
            assert normalizer.use_llm is True
            assert normalizer.llm_available is False

    def test_llm_disabled_when_litellm_not_available(self, temp_mapping_file, mock_llm_config):
        """Test that LLM is disabled when litellm library is not installed."""
        with patch.dict('sys.modules', {'litellm': None}):
            normalizer = GenreNormalizer(mapping_file=temp_mapping_file, use_llm=True)
            assert normalizer.llm_available is False

    @patch('litellm.completion')
    def test_llm_connection_success(self, mock_completion, temp_mapping_file, mock_llm_config):
        """Test successful LLM connection during initialization."""
        mock_completion.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="OK"), finish_reason="stop")]
        )

        normalizer = GenreNormalizer(mapping_file=temp_mapping_file, use_llm=True)
        assert normalizer.llm_available is True
        mock_completion.assert_called_once()

    @patch('litellm.completion')
    def test_llm_connection_failure(self, mock_completion, temp_mapping_file, mock_llm_config):
        """Test LLM connection failure during initialization."""
        mock_completion.side_effect = Exception("Connection failed")

        normalizer = GenreNormalizer(mapping_file=temp_mapping_file, use_llm=True)
        assert normalizer.llm_available is False


class TestLLMCategorization:
    """Tests for LLM genre categorization logic."""

    @patch('litellm.completion')
    def test_llm_categorizes_subgenre_to_main_genre(self, mock_completion, temp_mapping_file, mock_llm_config):
        """Test that LLM correctly categorizes a subgenre to a main genre."""
        # Setup: LLM connection succeeds, then categorizes "cyberpunk" as "science fiction"
        mock_completion.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content="OK"), finish_reason="stop")]),  # Connection test
            MagicMock(choices=[MagicMock(message=MagicMock(content="science fiction"), finish_reason="stop")])  # Categorization
        ]

        normalizer = GenreNormalizer(mapping_file=temp_mapping_file, use_llm=True)
        genres = ["cyberpunk"]
        result = normalizer.normalize_genres(genres)

        assert result == ["science fiction"]
        # Check that mapping was updated
        assert "cyberpunk" in normalizer.mapping["science fiction"]

    @patch('litellm.completion')
    def test_llm_returns_no_match(self, mock_completion, temp_mapping_file, mock_llm_config):
        """Test that LLM correctly returns no match for unrelated genre."""
        # Setup: LLM connection succeeds, then returns "NO_FIT" for no match
        mock_completion.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content="OK"), finish_reason="stop")]),  # Connection test
            MagicMock(choices=[MagicMock(message=MagicMock(content="NO_FIT"), finish_reason="stop")])  # No match
        ]

        normalizer = GenreNormalizer(mapping_file=temp_mapping_file, use_llm=True)
        genres = ["portuguese literature"]
        result = normalizer.normalize_genres(genres)

        assert result == ["portuguese literature"]
        # Check that new canonical genre was created
        assert "portuguese literature" in normalizer.mapping
        assert normalizer.mapping["portuguese literature"] == []

    @patch('litellm.completion')
    def test_llm_invalid_response_raises_exception(self, mock_completion, temp_mapping_file, mock_llm_config):
        """Test that invalid LLM response raises exception."""
        # Setup: LLM connection succeeds, then returns invalid response
        mock_completion.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content="OK"), finish_reason="stop")]),  # Connection test
            MagicMock(choices=[MagicMock(message=MagicMock(content="invalid category"), finish_reason="stop")])  # Invalid
        ]

        normalizer = GenreNormalizer(mapping_file=temp_mapping_file, use_llm=True)
        genres = ["space opera"]

        # Should raise exception since LLM response was invalid
        with pytest.raises(Exception, match="LLM failed to categorize genres"):
            normalizer.normalize_genres(genres)

    @patch('litellm.completion')
    def test_llm_error_during_categorization(self, mock_completion, temp_mapping_file, mock_llm_config):
        """Test that errors during categorization raise exception."""
        # Setup: LLM connection succeeds, then fails during categorization
        mock_completion.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content="OK"), finish_reason="stop")]),  # Connection test
            Exception("API error")  # Categorization fails
        ]

        normalizer = GenreNormalizer(mapping_file=temp_mapping_file, use_llm=True)
        genres = ["space opera"]

        # Should raise exception since LLM failed
        with pytest.raises(Exception, match="LLM failed to categorize genres"):
            normalizer.normalize_genres(genres)

    @patch('litellm.completion')
    def test_llm_incomplete_response_raises_exception(self, mock_completion, temp_mapping_file, mock_llm_config):
        """Test that incomplete LLM response (finish_reason != 'stop') raises exception."""
        # Setup: LLM connection succeeds, then returns incomplete response
        mock_completion.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content="OK"), finish_reason="stop")]),  # Connection test
            MagicMock(choices=[MagicMock(message=MagicMock(content="partial"), finish_reason="length")])  # Incomplete
        ]

        normalizer = GenreNormalizer(mapping_file=temp_mapping_file, use_llm=True)
        genres = ["space opera"]

        # Should raise exception due to incomplete response
        with pytest.raises(Exception, match="LLM failed to categorize genres"):
            normalizer.normalize_genres(genres)

    @patch('litellm.completion')
    def test_llm_categorization_saves_mapping(self, mock_completion, temp_mapping_file, mock_llm_config):
        """Test that LLM categorization results are saved to mapping file."""
        # Setup: LLM connection succeeds, then categorizes
        mock_completion.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content="OK"), finish_reason="stop")]),  # Connection test
            MagicMock(choices=[MagicMock(message=MagicMock(content="mystery"), finish_reason="stop")])  # Categorization
        ]

        normalizer = GenreNormalizer(mapping_file=temp_mapping_file, use_llm=True)
        genres = ["cozy mystery"]
        normalizer.normalize_genres(genres)

        # Check that mapping file was updated on disk
        with open(temp_mapping_file, 'r', encoding='utf-8') as f:
            saved_mapping = json.load(f)
        assert "cozy mystery" in saved_mapping["mystery"]


class TestLLMPromptGeneration:
    """Tests for LLM prompt generation."""

    @patch('litellm.completion')
    def test_prompt_includes_all_existing_genres(self, mock_completion, temp_mapping_file, mock_llm_config):
        """Test that the LLM prompt includes all existing genre mappings."""
        mock_completion.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content="OK"), finish_reason="stop")]),  # Connection test
            MagicMock(choices=[MagicMock(message=MagicMock(content="NO_FIT"), finish_reason="stop")])  # No match
        ]

        normalizer = GenreNormalizer(mapping_file=temp_mapping_file, use_llm=True)
        normalizer.normalize_genres(["new genre"])

        # Get the categorization call (second call)
        categorization_call = mock_completion.call_args_list[1]
        prompt = categorization_call[1]['messages'][0]['content']

        # Verify prompt contains existing mappings
        assert "science fiction" in prompt
        assert "fantasy" in prompt
        assert "romance" in prompt
        assert "mystery" in prompt
        assert "new genre" in prompt

    @patch('litellm.completion')
    def test_prompt_includes_confidence_threshold(self, mock_completion, temp_mapping_file, mock_llm_config):
        """Test that the LLM prompt mentions the confidence threshold."""
        mock_completion.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content="OK"), finish_reason="stop")]),  # Connection test
            MagicMock(choices=[MagicMock(message=MagicMock(content="NO_FIT"), finish_reason="stop")])  # No match
        ]

        normalizer = GenreNormalizer(mapping_file=temp_mapping_file, use_llm=True)
        normalizer.normalize_genres(["new genre"])

        # Get the categorization call
        categorization_call = mock_completion.call_args_list[1]
        prompt = categorization_call[1]['messages'][0]['content']

        # Verify prompt mentions 85% confidence
        assert "85" in prompt


class TestLLMIntegration:
    """Integration tests for LLM with genre normalization."""

    @patch('litellm.completion')
    def test_mixed_mapped_and_unmapped_genres(self, mock_completion, temp_mapping_file, mock_llm_config):
        """Test normalization with mix of mapped and unmapped genres."""
        # Setup: LLM connection succeeds, then categorizes unmapped genre
        mock_completion.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content="OK"), finish_reason="stop")]),  # Connection test
            MagicMock(choices=[MagicMock(message=MagicMock(content="science fiction"), finish_reason="stop")])  # Categorization
        ]

        normalizer = GenreNormalizer(mapping_file=temp_mapping_file, use_llm=True)
        genres = ["sci-fi", "fantasy", "cyberpunk"]  # sci-fi and fantasy are mapped, cyberpunk is not
        result = normalizer.normalize_genres(genres)

        assert result == ["science fiction", "fantasy"]  # cyberpunk categorized as science fiction
        assert len(result) == 2  # Deduplicated

    @patch('litellm.completion')
    def test_llm_not_called_for_mapped_genres(self, mock_completion, temp_mapping_file, mock_llm_config):
        """Test that LLM is not called when all genres are already mapped."""
        mock_completion.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content="OK"), finish_reason="stop")])  # Only connection test
        ]

        normalizer = GenreNormalizer(mapping_file=temp_mapping_file, use_llm=True)
        genres = ["sci-fi", "fantastyka", "romans"]  # All are mapped
        result = normalizer.normalize_genres(genres)

        assert result == ["science fiction", "fantasy", "romance"]
        # Should only have been called once (for connection test)
        assert mock_completion.call_count == 1

    @patch('litellm.completion')
    def test_llm_categorization_persists_across_instances(self, mock_completion, temp_mapping_file, mock_llm_config):
        """Test that LLM categorization results persist when creating new normalizer instance."""
        # First instance: categorize "cyberpunk"
        mock_completion.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content="OK"), finish_reason="stop")]),  # Connection test
            MagicMock(choices=[MagicMock(message=MagicMock(content="science fiction"), finish_reason="stop")])  # Categorization
        ]

        normalizer1 = GenreNormalizer(mapping_file=temp_mapping_file, use_llm=True)
        normalizer1.normalize_genres(["cyberpunk"])

        # Second instance: "cyberpunk" should now be mapped, no LLM call needed
        mock_completion.reset_mock()
        mock_completion.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content="OK"), finish_reason="stop")])  # Only connection test
        ]

        normalizer2 = GenreNormalizer(mapping_file=temp_mapping_file, use_llm=True)
        result = normalizer2.normalize_genres(["cyberpunk"])

        assert result == ["science fiction"]
        # Should only call for connection test, not categorization
        assert mock_completion.call_count == 1


class TestConfidenceThreshold:
    """Tests for confidence threshold configuration."""

    def test_confidence_threshold_is_configurable(self, temp_mapping_file):
        """Test that confidence threshold can be changed."""
        normalizer = GenreNormalizer(mapping_file=temp_mapping_file, use_llm=False)

        # Check default
        assert GenreNormalizer.LLM_CONFIDENCE_THRESHOLD == 0.85

        # Modify threshold
        GenreNormalizer.LLM_CONFIDENCE_THRESHOLD = 0.90
        assert GenreNormalizer.LLM_CONFIDENCE_THRESHOLD == 0.90

        # Reset to default
        GenreNormalizer.LLM_CONFIDENCE_THRESHOLD = 0.85

    @patch('litellm.completion')
    def test_changed_threshold_affects_prompt(self, mock_completion, temp_mapping_file, mock_llm_config):
        """Test that changing threshold affects the LLM prompt."""
        # Change threshold to 90%
        original_threshold = GenreNormalizer.LLM_CONFIDENCE_THRESHOLD
        GenreNormalizer.LLM_CONFIDENCE_THRESHOLD = 0.90

        mock_completion.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content="OK"), finish_reason="stop")]),  # Connection test
            MagicMock(choices=[MagicMock(message=MagicMock(content="NO_FIT"), finish_reason="stop")])  # No match
        ]

        normalizer = GenreNormalizer(mapping_file=temp_mapping_file, use_llm=True)
        normalizer.normalize_genres(["new genre"])

        # Get the categorization call
        categorization_call = mock_completion.call_args_list[1]
        prompt = categorization_call[1]['messages'][0]['content']

        # Verify prompt mentions 90% confidence
        assert "90" in prompt

        # Reset threshold
        GenreNormalizer.LLM_CONFIDENCE_THRESHOLD = original_threshold


class TestGlobalSingleton:
    """Tests for global singleton pattern with LLM."""

    def test_get_normalizer_without_llm(self, temp_mapping_file):
        """Test that get_normalizer creates instance without LLM by default."""
        from src.utils.genre_normalizer import _normalizer, get_normalizer

        # Reset global instance
        import src.utils.genre_normalizer as gnorm
        original_normalizer = gnorm._normalizer
        gnorm._normalizer = None

        try:
            with patch('src.utils.genre_normalizer.GenreNormalizer.__init__', return_value=None) as mock_init:
                normalizer = get_normalizer(use_llm=False)
                mock_init.assert_called_once_with(use_llm=False)
        finally:
            # Restore original normalizer to prevent test pollution
            gnorm._normalizer = original_normalizer

    def test_get_normalizer_with_llm_creates_new_instance(self, temp_mapping_file):
        """Test that requesting LLM creates new instance even if one exists."""
        from src.utils.genre_normalizer import get_normalizer
        import src.utils.genre_normalizer as gnorm

        # Reset and create non-LLM instance
        original_normalizer = gnorm._normalizer
        gnorm._normalizer = None

        try:
            normalizer1 = get_normalizer(use_llm=False)
            assert normalizer1 is not None

            # Request LLM instance - should create new one
            with patch('src.utils.genre_normalizer.GenreNormalizer') as mock_class:
                mock_instance = Mock()
                mock_instance.use_llm = True
                mock_class.return_value = mock_instance

                normalizer2 = get_normalizer(use_llm=True)
                mock_class.assert_called_with(use_llm=True)
        finally:
            # Restore original normalizer to prevent test pollution
            gnorm._normalizer = original_normalizer
