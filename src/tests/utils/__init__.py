"""
Test utilities for BadaBoomBooks scraper testing.

This package provides tools for comparing scraped metadata against reference data
and generating human-readable diff reports.
"""

from .metadata_comparison import (
    FieldDiff,
    DiffSeverity,
    DiffType,
    MetadataComparison,
    compare_metadata,
)
from .diff_reporter import format_diff_report

__all__ = [
    'FieldDiff',
    'DiffSeverity',
    'DiffType',
    'MetadataComparison',
    'compare_metadata',
    'format_diff_report',
]
