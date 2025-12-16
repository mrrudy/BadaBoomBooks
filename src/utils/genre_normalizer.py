"""
Genre normalization and mapping utilities.

This module provides functionality to normalize genre names and map alternatives
to canonical designators based on a mapping file.
"""

import json
from pathlib import Path
from typing import List, Dict, Set
import logging

logger = logging.getLogger(__name__)


class GenreNormalizer:
    """Handles genre normalization and mapping to canonical forms."""

    def __init__(self, mapping_file: Path = None):
        """
        Initialize the genre normalizer.

        Args:
            mapping_file: Path to the genre mapping JSON file.
                         Defaults to 'genre_mapping.json' in project root.
        """
        if mapping_file is None:
            # Default to project root
            project_root = Path(__file__).parent.parent.parent
            mapping_file = project_root / "genre_mapping.json"

        self.mapping_file = Path(mapping_file)
        self.mapping = self._load_mapping()

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

    def _find_canonical_genre(self, genre: str) -> str:
        """
        Find the canonical form of a genre.

        Args:
            genre: Genre name to normalize (will be lowercased).

        Returns:
            Canonical genre name (lowercase). If genre is an alternative,
            returns the designator. If not found in mapping, returns the
            original genre (lowercased).
        """
        genre_lower = genre.lower().strip()

        # Check if it's already a canonical designator
        if genre_lower in self.mapping:
            return genre_lower

        # Check if it's an alternative for any canonical genre
        for canonical, alternatives in self.mapping.items():
            if genre_lower in alternatives:
                return canonical

        # Not found in mapping - treat as new canonical genre
        return genre_lower

    def normalize_genres(self, genres: List[str]) -> List[str]:
        """
        Normalize and deduplicate a list of genres.

        Process:
        1. Lowercase all genres
        2. Map alternatives to canonical forms
        3. Remove duplicates while preserving order
        4. Unknown genres become new canonical forms

        Args:
            genres: List of genre strings to normalize.

        Returns:
            Normalized list of unique canonical genre names (lowercase).

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

        for genre in genres:
            if not genre or not genre.strip():
                continue

            canonical = self._find_canonical_genre(genre)

            # Add only if not already seen (deduplication)
            if canonical not in seen:
                canonical_genres.append(canonical)
                seen.add(canonical)

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


def get_normalizer() -> GenreNormalizer:
    """Get the global GenreNormalizer instance (singleton pattern)."""
    global _normalizer
    if _normalizer is None:
        _normalizer = GenreNormalizer()
    return _normalizer


def normalize_genres(genres: List[str]) -> List[str]:
    """
    Convenience function to normalize genres using the global normalizer.

    Args:
        genres: List of genre strings to normalize.

    Returns:
        Normalized list of unique canonical genre names (lowercase).
    """
    return get_normalizer().normalize_genres(genres)
