"""
Metadata comparison utilities for scraper regression testing.

Provides field-by-field comparison of BookMetadata objects with intelligent
diff analysis to distinguish between scraper failures and legitimate service updates.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional
from difflib import SequenceMatcher
import re

from src.models import BookMetadata


class DiffSeverity(Enum):
    """Severity levels for metadata field differences."""
    CRITICAL = "CRITICAL"  # Test fails - scraper broken
    MAJOR = "MAJOR"        # Test passes with warning
    MINOR = "MINOR"        # Test passes
    INFO = "INFO"          # Test passes - informational only


class DiffType(Enum):
    """Types of differences between expected and actual values."""
    MISSING = "MISSING"    # Expected value present, actual empty/missing
    ADDED = "ADDED"        # Expected empty, actual has value (service improvement)
    CHANGED = "CHANGED"    # Both have values but different
    EMPTY = "EMPTY"        # Both empty (no diff)


@dataclass
class FieldDiff:
    """Represents a difference in a single metadata field."""
    field_name: str
    expected_value: Any
    actual_value: Any
    severity: DiffSeverity
    diff_type: DiffType
    message: str = ""
    similarity: Optional[float] = None  # For fuzzy matches (0.0-1.0)


@dataclass
class MetadataComparison:
    """Complete comparison result between two BookMetadata objects."""
    reference_metadata: BookMetadata
    scraped_metadata: BookMetadata
    field_diffs: List[FieldDiff] = field(default_factory=list)
    critical_fields_match: bool = True
    major_fields_match: bool = True
    overall_similarity: float = 1.0

    def has_critical_failures(self) -> bool:
        """Check if critical fields (title, author) are broken."""
        return any(
            diff.severity == DiffSeverity.CRITICAL
            for diff in self.field_diffs
        )

    def is_acceptable_match(self) -> bool:
        """
        Overall pass/fail based on thresholds.

        Returns False if:
        - Any CRITICAL severity diffs exist
        - Overall similarity < 70%

        Returns True otherwise.
        """
        if self.has_critical_failures():
            return False
        if self.overall_similarity < 0.7:
            return False
        return True

    def get_status_summary(self) -> str:
        """Get human-readable status summary."""
        if self.has_critical_failures():
            return "FAIL (Critical Fields)"
        elif not self.major_fields_match:
            return "PASS (Major Changes Detected)"
        elif len(self.field_diffs) > 0:
            return "PASS (Minor Changes Detected)"
        else:
            return "PASS (Perfect Match)"


# Field categorization
CRITICAL_FIELDS = ['title', 'author', 'url']
MAJOR_FIELDS = ['series', 'volumenumber', 'summary', 'genres', 'language', 'isbn']
MINOR_FIELDS = ['subtitle', 'narrator', 'publisher', 'publishyear', 'datepublished', 'asin']
DYNAMIC_FIELDS = ['cover_url']  # Can change legitimately
IGNORE_FIELDS = ['input_folder', 'final_output', 'failed', 'skip', 'failed_exception',
                 'authors_multi', 'series_multi', 'narrators_multi']


def normalize_volume(vol: str) -> str:
    """
    Normalize volume number formats.

    Examples:
        "1,2" → "1-2"
        "1-2" → "1-2"
        "1" → "1"
        "01" → "1"
    """
    if not vol:
        return ""
    # Replace commas and spaces with hyphens
    normalized = re.sub(r'[,\s]+', '-', vol.strip())
    # Remove leading zeros from each number
    parts = normalized.split('-')
    parts = [str(int(p)) if p.isdigit() else p for p in parts]
    return '-'.join(parts)


def compare_exact(expected: str, actual: str, case_sensitive: bool = False) -> bool:
    """Compare two strings for exact match."""
    if not case_sensitive:
        expected = (expected or "").lower().strip()
        actual = (actual or "").lower().strip()
    else:
        expected = (expected or "").strip()
        actual = (actual or "").strip()
    return expected == actual


def compare_fuzzy(expected: str, actual: str, threshold: float = 0.85) -> tuple[bool, float]:
    """
    Compare two strings using fuzzy matching.

    Returns:
        (matches, similarity_score)
    """
    if not expected and not actual:
        return True, 1.0
    if not expected or not actual:
        return False, 0.0

    similarity = SequenceMatcher(None, expected.strip(), actual.strip()).ratio()
    return similarity >= threshold, similarity


def compare_set(expected: str, actual: str) -> tuple[bool, set, set, set]:
    """
    Compare comma-separated strings as sets (order-independent).

    Returns:
        (matches, expected_set, actual_set, missing_items, added_items)
    """
    expected_set = set(item.strip().lower() for item in (expected or "").split(',') if item.strip())
    actual_set = set(item.strip().lower() for item in (actual or "").split(',') if item.strip())

    matches = expected_set == actual_set
    missing = expected_set - actual_set
    added = actual_set - expected_set

    return matches, expected_set, actual_set, missing, added


def compare_field(field_name: str, expected: Any, actual: Any) -> FieldDiff:
    """
    Compare a single field using appropriate strategy.

    Returns a FieldDiff object describing the difference.
    """
    # Convert to strings for comparison
    expected_str = str(expected) if expected else ""
    actual_str = str(actual) if actual else ""

    # Handle empty values
    if not expected_str and not actual_str:
        return FieldDiff(
            field_name=field_name,
            expected_value=expected,
            actual_value=actual,
            severity=DiffSeverity.INFO,
            diff_type=DiffType.EMPTY,
            message="Both empty"
        )

    if not expected_str and actual_str:
        return FieldDiff(
            field_name=field_name,
            expected_value=expected,
            actual_value=actual,
            severity=DiffSeverity.INFO,
            diff_type=DiffType.ADDED,
            message="Service added new data"
        )

    if expected_str and not actual_str:
        # Determine severity based on field category
        if field_name in CRITICAL_FIELDS:
            severity = DiffSeverity.CRITICAL
        elif field_name in MAJOR_FIELDS:
            severity = DiffSeverity.MAJOR
        else:
            severity = DiffSeverity.MINOR

        return FieldDiff(
            field_name=field_name,
            expected_value=expected,
            actual_value=actual,
            severity=severity,
            diff_type=DiffType.MISSING,
            message="Scraper failed to extract value"
        )

    # Both have values - compare based on field type
    if field_name in CRITICAL_FIELDS:
        # Critical fields: exact match (case-insensitive)
        if compare_exact(expected_str, actual_str, case_sensitive=False):
            return FieldDiff(
                field_name=field_name,
                expected_value=expected,
                actual_value=actual,
                severity=DiffSeverity.INFO,
                diff_type=DiffType.EMPTY,
                message="Match"
            )
        else:
            return FieldDiff(
                field_name=field_name,
                expected_value=expected,
                actual_value=actual,
                severity=DiffSeverity.CRITICAL,
                diff_type=DiffType.CHANGED,
                message=f"Critical field mismatch: '{expected_str}' != '{actual_str}'"
            )

    elif field_name == 'summary':
        # Summary: fuzzy match
        matches, similarity = compare_fuzzy(expected_str, actual_str, threshold=0.85)
        if matches:
            return FieldDiff(
                field_name=field_name,
                expected_value=expected,
                actual_value=actual,
                severity=DiffSeverity.INFO,
                diff_type=DiffType.EMPTY,
                message=f"Match (similarity: {similarity:.1%})",
                similarity=similarity
            )
        else:
            return FieldDiff(
                field_name=field_name,
                expected_value=expected,
                actual_value=actual,
                severity=DiffSeverity.MAJOR,
                diff_type=DiffType.CHANGED,
                message=f"Summary changed (similarity: {similarity:.1%})",
                similarity=similarity
            )

    elif field_name == 'genres':
        # Genres: set comparison
        matches, exp_set, act_set, missing, added = compare_set(expected_str, actual_str)
        if matches:
            return FieldDiff(
                field_name=field_name,
                expected_value=expected,
                actual_value=actual,
                severity=DiffSeverity.INFO,
                diff_type=DiffType.EMPTY,
                message="Match"
            )
        else:
            msg_parts = []
            if missing:
                msg_parts.append(f"Missing: {', '.join(missing)}")
            if added:
                msg_parts.append(f"Added: {', '.join(added)}")
            message = "; ".join(msg_parts)

            return FieldDiff(
                field_name=field_name,
                expected_value=expected,
                actual_value=actual,
                severity=DiffSeverity.MAJOR,
                diff_type=DiffType.CHANGED,
                message=message
            )

    elif field_name == 'volumenumber':
        # Volume number: normalized comparison
        norm_expected = normalize_volume(expected_str)
        norm_actual = normalize_volume(actual_str)
        if norm_expected == norm_actual:
            return FieldDiff(
                field_name=field_name,
                expected_value=expected,
                actual_value=actual,
                severity=DiffSeverity.INFO,
                diff_type=DiffType.EMPTY,
                message=f"Match (normalized: {norm_actual})"
            )
        else:
            return FieldDiff(
                field_name=field_name,
                expected_value=expected,
                actual_value=actual,
                severity=DiffSeverity.MAJOR,
                diff_type=DiffType.CHANGED,
                message=f"Volume mismatch: '{norm_expected}' != '{norm_actual}'"
            )

    elif field_name in DYNAMIC_FIELDS:
        # Dynamic fields: presence check only
        if actual_str:
            return FieldDiff(
                field_name=field_name,
                expected_value=expected,
                actual_value=actual,
                severity=DiffSeverity.INFO,
                diff_type=DiffType.EMPTY,
                message="Present (URL may change)"
            )
        else:
            return FieldDiff(
                field_name=field_name,
                expected_value=expected,
                actual_value=actual,
                severity=DiffSeverity.MINOR,
                diff_type=DiffType.MISSING,
                message="Not found"
            )

    else:
        # Other fields: exact match
        if compare_exact(expected_str, actual_str, case_sensitive=False):
            return FieldDiff(
                field_name=field_name,
                expected_value=expected,
                actual_value=actual,
                severity=DiffSeverity.INFO,
                diff_type=DiffType.EMPTY,
                message="Match"
            )
        else:
            # Determine severity
            if field_name in MAJOR_FIELDS:
                severity = DiffSeverity.MAJOR
            else:
                severity = DiffSeverity.MINOR

            return FieldDiff(
                field_name=field_name,
                expected_value=expected,
                actual_value=actual,
                severity=severity,
                diff_type=DiffType.CHANGED,
                message=f"Changed: '{expected_str}' → '{actual_str}'"
            )


def compare_metadata(reference: BookMetadata, scraped: BookMetadata) -> MetadataComparison:
    """
    Compare two BookMetadata objects field by field.

    Args:
        reference: Expected metadata from reference OPF file
        scraped: Actual metadata from current scraper

    Returns:
        MetadataComparison object with detailed diff analysis
    """
    comparison = MetadataComparison(
        reference_metadata=reference,
        scraped_metadata=scraped
    )

    # Get all field names from BookMetadata
    all_fields = [f.name for f in reference.__dataclass_fields__.values()]

    # Compare each field
    diffs = []
    for field_name in all_fields:
        if field_name in IGNORE_FIELDS:
            continue

        expected = getattr(reference, field_name, None)
        actual = getattr(scraped, field_name, None)

        diff = compare_field(field_name, expected, actual)

        # Only add to list if there's an actual difference
        if diff.diff_type != DiffType.EMPTY or diff.severity != DiffSeverity.INFO:
            diffs.append(diff)

    comparison.field_diffs = diffs

    # Determine if critical/major fields match
    comparison.critical_fields_match = all(
        diff.severity != DiffSeverity.CRITICAL
        for diff in diffs
    )

    comparison.major_fields_match = all(
        diff.severity not in [DiffSeverity.CRITICAL, DiffSeverity.MAJOR]
        for diff in diffs
    )

    # Calculate overall similarity
    # Count matched fields vs total non-empty reference fields
    total_fields = len([f for f in all_fields if f not in IGNORE_FIELDS])
    matched_fields = total_fields - len([d for d in diffs if d.diff_type != DiffType.EMPTY])

    if total_fields > 0:
        comparison.overall_similarity = matched_fields / total_fields
    else:
        comparison.overall_similarity = 1.0

    return comparison
