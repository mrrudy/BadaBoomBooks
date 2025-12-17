"""
Genre normalization and mapping utilities.

This module provides functionality to normalize genre names and map alternatives
to canonical designators based on a mapping file. Includes optional LLM-based
categorization for unmapped genres.
"""

import json
from pathlib import Path
from typing import List, Dict, Set, Optional
import logging

logger = logging.getLogger(__name__)


class GenreNormalizer:
    """Handles genre normalization and mapping to canonical forms."""

    # Minimum confidence threshold for LLM genre categorization (0.0-1.0)
    LLM_CONFIDENCE_THRESHOLD = 0.85

    # Maximum tokens for LLM response (allows for reasoning in response)
    LLM_MAX_TOKENS = 6000

    def __init__(self, mapping_file: Path = None, use_llm: bool = False):
        """
        Initialize the genre normalizer.

        Args:
            mapping_file: Path to the genre mapping JSON file.
                         Defaults to 'genre_mapping.json' in project root.
            use_llm: Whether to use LLM for categorizing unmapped genres.
        """
        if mapping_file is None:
            # Default to project root
            project_root = Path(__file__).parent.parent.parent
            mapping_file = project_root / "genre_mapping.json"

        self.mapping_file = Path(mapping_file)
        self.mapping = self._load_mapping()
        self.use_llm = use_llm
        self.llm_available = False

        if self.use_llm:
            self._test_llm_connection()

    def _load_mapping(self) -> Dict[str, List[str]]:
        """
        Load genre mapping from JSON file.

        Returns:
            Dictionary mapping canonical genre names (lowercase) to list of alternatives (lowercase).

        Format:
            {
                "romance": ["romans", "romantasy", "love"],
                "science fiction": ["sci-fy", "science fiction & fantasy", "space"]
            }
        """
        if not self.mapping_file.exists():
            logger.warning(f"Genre mapping file not found: {self.mapping_file}")
            logger.warning("Creating empty genre mapping. Genres will pass through unchanged.")
            self._create_default_mapping()
            return {}

        try:
            with open(self.mapping_file, 'r', encoding='utf-8') as f:
                mapping = json.load(f)
                # Ensure all keys and values are lowercase
                return {k.lower(): [alt.lower() for alt in v] for k, v in mapping.items()}
        except Exception as e:
            logger.error(f"Error loading genre mapping: {e}")
            return {}

    def _create_default_mapping(self):
        """Create a default genre mapping file with examples."""
        default_mapping = {
            "romance": ["romans", "romantasy", "love"],
            "science fiction": ["sci-fy", "sci-fi", "science fiction & fantasy", "science fiction fantasy", "space", "sf"],
            "fantasy": ["fantastyka"],
            "poland": ["polska", "polish", "polish literature"],
            "mystery": ["thriller", "crime"],
            "horror": []
        }

        try:
            with open(self.mapping_file, 'w', encoding='utf-8') as f:
                json.dump(default_mapping, f, indent=2, ensure_ascii=False)
            logger.info(f"Created default genre mapping file: {self.mapping_file}")
        except Exception as e:
            logger.error(f"Error creating default genre mapping: {e}")

    def _test_llm_connection(self) -> bool:
        """
        Test LLM connection during initialization.

        Returns:
            True if LLM is available and working, False otherwise.
        """
        try:
            from ..config import LLM_CONFIG

            if not LLM_CONFIG['enabled']:
                logger.warning("LLM genre categorization requested but no LLM_API_KEY configured")
                self.llm_available = False
                return False

            import litellm

            # Configure litellm
            if LLM_CONFIG['base_url']:
                litellm.api_base = LLM_CONFIG['base_url']

            # Test with a simple prompt
            logger.info(f"Testing LLM connection for genre categorization (model: {LLM_CONFIG['model']})...")
            response = litellm.completion(
                model=LLM_CONFIG['model'],
                api_key=LLM_CONFIG['api_key'],
                messages=[{"role": "user", "content": "Reply with only the word 'OK'"}],
                temperature=0.1,
                max_tokens=10
            )

            if response and response.choices:
                logger.info("LLM connection successful - genre categorization enabled")
                self.llm_available = True
                return True
            else:
                logger.error("LLM connection failed - genre categorization disabled")
                self.llm_available = False
                return False

        except ImportError:
            logger.error("litellm library not available - genre categorization disabled. Install with: pip install litellm")
            self.llm_available = False
            return False
        except Exception as e:
            logger.error(f"Failed to connect to LLM for genre categorization: {e}")
            self.llm_available = False
            return False

    def _categorize_genre_with_llm(self, new_genre: str) -> Optional[str]:
        """
        Use LLM to categorize a new genre into an existing category.

        Args:
            new_genre: The unmapped genre to categorize.

        Returns:
            The canonical genre name if a match is found with sufficient confidence,
            None if no match found (LLM returned NO_FIT),
            or raises Exception if LLM response is invalid/incomplete.
        """
        if not self.llm_available:
            raise Exception("LLM not available")

        try:
            import litellm
            from ..config import LLM_CONFIG

            # Build prompt with current mapping
            prompt = self._build_categorization_prompt(new_genre)

            logger.debug(f"Asking LLM to categorize genre: '{new_genre}'")

            response = litellm.completion(
                model=LLM_CONFIG['model'],
                api_key=LLM_CONFIG['api_key'],
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,  # Low temperature for consistent categorization
                max_tokens=self.LLM_MAX_TOKENS
            )

            # Validate finish_reason to ensure complete response
            finish_reason = response.choices[0].finish_reason
            if finish_reason != "stop":
                raise Exception(f"LLM response incomplete (finish_reason: {finish_reason})")

            response_text = response.choices[0].message.content.strip()
            result = self._parse_llm_categorization(response_text, new_genre)

            return result

        except Exception as e:
            logger.error(f"LLM genre categorization failed for '{new_genre}': {e}")
            raise

    def _build_categorization_prompt(self, new_genre: str) -> str:
        """
        Build the LLM prompt for genre categorization.

        Args:
            new_genre: The genre to categorize.

        Returns:
            The prompt string.
        """
        # Get list of canonical genres
        canonical_genres = sorted(self.mapping.keys())

        prompt = f"""You are a book genre classification assistant. I need you to determine if a new genre fits into any of my existing genre categories.

Existing genre categories and their alternatives:
{json.dumps(self.mapping, indent=2, ensure_ascii=False)}

New genre to categorize: "{new_genre}"

Your task:
1. Determine if "{new_genre}" can be reasonably categorized as one of the existing genres listed above
2. Only suggest a match if you are at least {int(self.LLM_CONFIDENCE_THRESHOLD * 100)}% confident it fits
3. Consider synonyms, related concepts, subcategories, and translations
4. IMPORTANT: Genres in different languages should match if they mean the same thing
   - Example: "historia" (Spanish/Polish) = "history"
   - Example: "fantastyka" (Polish) = "fantasy"
   - The language difference should NOT reduce your confidence if the meaning matches

Response format:
- If you find a match with {int(self.LLM_CONFIDENCE_THRESHOLD * 100)}%+ confidence: respond with ONLY the canonical genre name (e.g., "science fiction")
- If no match or confidence is below {int(self.LLM_CONFIDENCE_THRESHOLD * 100)}%: respond with ONLY "NO_FIT"

Examples:
- For "cyberpunk" → "science fiction"
- For "historical romance" → "romance"
- For "historia" → "history" (Spanish/Polish word for history)
- For "french literature" → "NO_FIT" (no good match)
- For "cozy mystery" → "mystery"

Respond with ONLY the canonical genre name or "NO_FIT". No explanations, no reasoning, just the answer."""

        return prompt

    def _parse_llm_categorization(self, response_text: str, genre: str) -> Optional[str]:
        """
        Parse LLM categorization response.

        Args:
            response_text: Raw LLM response.
            genre: Original genre being categorized (for logging).

        Returns:
            Canonical genre name if valid match found,
            None if NO_FIT response,
            raises Exception if response is invalid.
        """
        response_text = response_text.strip().lower()

        # Check for "no match" response
        if response_text == "no_fit":
            logger.info(f"LLM: No confident match found for genre '{genre}' (NO_FIT)")
            return None

        # Check if response is a valid canonical genre
        if response_text in self.mapping:
            logger.info(f"LLM: Categorized '{genre}' as '{response_text}'")
            return response_text

        # Invalid response - raise exception to skip this genre
        raise Exception(f"LLM returned invalid response: '{response_text}'")

    def _find_canonical_genre(self, genre: str) -> str:
        """
        Find the canonical form of a genre.

        Args:
            genre: Genre name to normalize (will be lowercased).

        Returns:
            Canonical genre name (lowercase). If genre is an alternative,
            returns the designator. If not found in mapping, returns the
            original genre (lowercased). If LLM is enabled and finds a match,
            adds the mapping and returns the canonical genre.
        """
        genre_lower = genre.lower().strip()

        # Check if it's already a canonical designator
        if genre_lower in self.mapping:
            return genre_lower

        # Check if it's an alternative for any canonical genre
        for canonical, alternatives in self.mapping.items():
            if genre_lower in alternatives:
                return canonical

        # Not found in mapping - try LLM categorization if enabled
        if self.use_llm and self.llm_available:
            logger.info(f"Genre '{genre_lower}' not in mapping - consulting LLM...")
            try:
                llm_category = self._categorize_genre_with_llm(genre_lower)

                if llm_category:
                    # LLM found a match - add to mapping as alternative
                    logger.info(f"LLM mapped '{genre_lower}' → '{llm_category}' - adding to genre_mapping.json")
                    self.add_alternative_to_existing(llm_category, genre_lower)
                    self.save_mapping()
                    return llm_category
                else:
                    # LLM returned NO_FIT - treat as new canonical genre
                    logger.info(f"LLM found no match for '{genre_lower}' - adding as new main genre")
                    self.add_mapping(genre_lower, [])
                    self.save_mapping()
                    return genre_lower

            except Exception as e:
                # LLM error - raise to skip this genre completely
                logger.error(f"LLM categorization error for '{genre_lower}': {e}")
                raise Exception(f"LLM failed to categorize genre '{genre_lower}': {e}")

        # Not found and LLM not available - treat as new canonical genre
        return genre_lower

    def normalize_genres(self, genres: List[str]) -> List[str]:
        """
        Normalize and deduplicate a list of genres.

        Process:
        1. Lowercase all genres
        2. Map alternatives to canonical forms
        3. Remove duplicates while preserving order
        4. Unknown genres: With LLM, try to categorize; without LLM, add as new canonical
        5. If LLM errors on a genre, skip that genre and raise exception

        Args:
            genres: List of genre strings to normalize.

        Returns:
            Normalized list of unique canonical genre names (lowercase).

        Raises:
            Exception: If LLM fails to categorize a genre (book should be skipped).

        Examples:
            >>> normalizer = GenreNormalizer()
            >>> normalizer.normalize_genres(["Horror", "ROMANCE", "romans", "Horror"])
            ["horror", "romance"]

            >>> normalizer.normalize_genres(["Sci-Fy", "Fantasy", "Science Fiction"])
            ["science fiction", "fantasy"]
        """
        if not genres:
            return []

        canonical_genres = []
        seen: Set[str] = set()
        llm_failed_genres = []

        for genre in genres:
            if not genre or not genre.strip():
                continue

            try:
                canonical = self._find_canonical_genre(genre)

                # Add only if not already seen (deduplication)
                if canonical not in seen:
                    canonical_genres.append(canonical)
                    seen.add(canonical)

            except Exception as e:
                # LLM error for this genre - track it
                llm_failed_genres.append(genre)
                logger.error(f"Skipping genre '{genre}' due to LLM error: {e}")

        # If any genres failed LLM categorization, raise exception to skip this book
        if llm_failed_genres:
            failed_str = ", ".join(llm_failed_genres)
            raise Exception(f"LLM failed to categorize genres: {failed_str}")

        return canonical_genres

    def add_mapping(self, canonical: str, alternatives: List[str] = None):
        """
        Add or update a genre mapping.

        Args:
            canonical: The canonical genre name (will be lowercased).
            alternatives: List of alternative names that map to this canonical form.
        """
        canonical_lower = canonical.lower().strip()
        alternatives_lower = [alt.lower().strip() for alt in (alternatives or [])]

        if canonical_lower in self.mapping:
            # Merge with existing alternatives
            existing = set(self.mapping[canonical_lower])
            self.mapping[canonical_lower] = list(existing | set(alternatives_lower))
        else:
            self.mapping[canonical_lower] = alternatives_lower

    def add_alternative_to_existing(self, canonical: str, alternative: str):
        """
        Add an alternative to an existing canonical genre.

        Args:
            canonical: The canonical genre name (must exist in mapping).
            alternative: The alternative name to add.
        """
        canonical_lower = canonical.lower().strip()
        alternative_lower = alternative.lower().strip()

        if canonical_lower not in self.mapping:
            logger.error(f"Cannot add alternative '{alternative}' - canonical genre '{canonical}' not found")
            return

        if alternative_lower not in self.mapping[canonical_lower]:
            self.mapping[canonical_lower].append(alternative_lower)
            logger.debug(f"Added '{alternative_lower}' as alternative to '{canonical_lower}'")

    def save_mapping(self):
        """Save the current mapping to the JSON file."""
        try:
            with open(self.mapping_file, 'w', encoding='utf-8') as f:
                json.dump(self.mapping, f, indent=2, ensure_ascii=False, sort_keys=True)
            logger.info(f"Genre mapping saved to: {self.mapping_file}")
        except Exception as e:
            logger.error(f"Error saving genre mapping: {e}")


# Global instance for easy access
_normalizer = None


def get_normalizer(use_llm: bool = False) -> GenreNormalizer:
    """
    Get the global GenreNormalizer instance (singleton pattern).

    Args:
        use_llm: Whether to enable LLM categorization. If True and instance
                 already exists without LLM, a new instance will be created.

    Returns:
        GenreNormalizer instance with requested configuration.
    """
    global _normalizer

    # If requesting LLM but current instance doesn't have it, create new one
    if use_llm and (_normalizer is None or not _normalizer.use_llm):
        _normalizer = GenreNormalizer(use_llm=True)
    elif _normalizer is None:
        _normalizer = GenreNormalizer(use_llm=False)

    return _normalizer


def normalize_genres(genres: List[str], use_llm: bool = False) -> List[str]:
    """
    Convenience function to normalize genres using the global normalizer.

    Args:
        genres: List of genre strings to normalize.
        use_llm: Whether to use LLM for categorizing unmapped genres.

    Returns:
        Normalized list of unique canonical genre names (lowercase).
    """
    return get_normalizer(use_llm=use_llm).normalize_genres(genres)
