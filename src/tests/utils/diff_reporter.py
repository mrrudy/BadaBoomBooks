"""
Diff reporter for scraper regression testing.

Generates human-readable diff reports with interpretation guidance to help
distinguish between scraper failures and legitimate service updates.
"""

from typing import Optional
from .metadata_comparison import MetadataComparison, DiffSeverity, DiffType

# Try to import colorama for colored output, fall back to plain text
try:
    from colorama import Fore, Style, init
    init(autoreset=True)
    HAS_COLOR = True
except ImportError:
    HAS_COLOR = False
    # Fallback: no-op color codes
    class Fore:
        GREEN = ""
        RED = ""
        YELLOW = ""
        CYAN = ""
        WHITE = ""
        RESET = ""

    class Style:
        BRIGHT = ""
        RESET_ALL = ""


def format_diff_report(
    comparison: MetadataComparison,
    verbose: bool = False,
    use_color: bool = True
) -> str:
    """
    Format a MetadataComparison into a human-readable report.

    Args:
        comparison: The comparison result to format
        verbose: If True, show full diff details
        use_color: If True, use ANSI color codes (if colorama available)

    Returns:
        Formatted report string
    """
    if not use_color or not HAS_COLOR:
        # Disable colors
        global Fore, Style
        class NoColor:
            GREEN = RED = YELLOW = CYAN = WHITE = RESET = ""
            BRIGHT = RESET_ALL = ""
        Fore = Style = NoColor()

    lines = []

    # Extract service name from URL
    url = comparison.reference_metadata.url
    service = "unknown"
    if "lubimyczytac" in url:
        service = "lubimyczytac"
    elif "audible" in url:
        service = "audible"
    elif "goodreads" in url:
        service = "goodreads"

    # Header
    lines.append("=" * 80)
    lines.append(f"{Style.BRIGHT}SCRAPER REGRESSION TEST: {service}{Style.RESET_ALL}")
    lines.append(f"URL: {url}")
    lines.append(f"Status: {_format_status(comparison)}")
    lines.append(f"Overall Similarity: {comparison.overall_similarity:.1%}")
    lines.append("=" * 80)
    lines.append("")

    # Critical fields
    lines.append(f"{Style.BRIGHT}CRITICAL FIELDS:{Style.RESET_ALL} {_format_section_status(comparison, 'critical')}")
    critical_diffs = [d for d in comparison.field_diffs if d.field_name in ['title', 'author', 'url']]

    # Always show critical fields, even if they match
    for field_name in ['title', 'author', 'url']:
        diff = next((d for d in critical_diffs if d.field_name == field_name), None)
        if diff and diff.severity == DiffSeverity.CRITICAL:
            lines.append(f"  {Fore.RED}✗ {field_name}: {diff.message}{Style.RESET_ALL}")
            if verbose:
                lines.append(f"    Expected: {diff.expected_value}")
                lines.append(f"    Actual:   {diff.actual_value}")
        else:
            # Show the value
            value = getattr(comparison.reference_metadata, field_name, "")
            if len(str(value)) > 60:
                value = str(value)[:57] + "..."
            lines.append(f"  {Fore.GREEN}✓ {field_name}: \"{value}\"{Style.RESET_ALL}")

    lines.append("")

    # Major fields
    major_diffs = [d for d in comparison.field_diffs
                   if d.field_name in ['series', 'volumenumber', 'summary', 'genres', 'language', 'isbn']]

    if major_diffs:
        change_count = len([d for d in major_diffs if d.diff_type != DiffType.EMPTY])
        lines.append(f"{Style.BRIGHT}MAJOR FIELDS:{Style.RESET_ALL} {_format_section_status(comparison, 'major')} ({change_count} changes)")

        for diff in major_diffs:
            if diff.diff_type == DiffType.EMPTY and diff.severity == DiffSeverity.INFO:
                continue  # Skip perfect matches in summary

            lines.append(f"  {_format_diff_indicator(diff)} {diff.field_name}: {_format_diff_message(diff, verbose)}")

            if verbose and diff.field_name == 'summary':
                lines.append(f"    Expected ({len(str(diff.expected_value))} chars):")
                lines.append(f"      {_truncate(diff.expected_value, 200)}")
                lines.append(f"    Actual ({len(str(diff.actual_value))} chars):")
                lines.append(f"      {_truncate(diff.actual_value, 200)}")

        lines.append("")
    else:
        lines.append(f"{Style.BRIGHT}MAJOR FIELDS:{Style.RESET_ALL} {Fore.GREEN}✓ ALL MATCH{Style.RESET_ALL}")
        lines.append("")

    # Minor fields (only show if there are differences)
    minor_diffs = [d for d in comparison.field_diffs
                   if d.field_name in ['subtitle', 'narrator', 'publisher', 'publishyear', 'datepublished', 'asin']]

    if minor_diffs:
        change_count = len([d for d in minor_diffs if d.diff_type != DiffType.EMPTY])
        lines.append(f"{Style.BRIGHT}MINOR FIELDS:{Style.RESET_ALL} {change_count} changes")

        for diff in minor_diffs:
            if diff.diff_type == DiffType.EMPTY and diff.severity == DiffSeverity.INFO:
                continue
            lines.append(f"  {_format_diff_indicator(diff)} {diff.field_name}: {_format_diff_message(diff, verbose)}")

        lines.append("")

    # Dynamic fields (cover_url, etc.)
    dynamic_diffs = [d for d in comparison.field_diffs if d.field_name in ['cover_url']]
    if dynamic_diffs:
        lines.append(f"{Style.BRIGHT}DYNAMIC FIELDS:{Style.RESET_ALL} (allowed to change)")
        for diff in dynamic_diffs:
            lines.append(f"  ℹ {diff.field_name}: {diff.message}")
        lines.append("")

    # Interpretation guidance
    lines.append(f"{Style.BRIGHT}INTERPRETATION:{Style.RESET_ALL}")
    lines.extend(_generate_interpretation(comparison))
    lines.append("")

    if not verbose and any(d.field_name == 'summary' for d in comparison.field_diffs):
        lines.append(f"{Fore.CYAN}Tip: Use -s flag with pytest to see full diff details{Style.RESET_ALL}")
        lines.append("")

    return "\n".join(lines)


def _format_status(comparison: MetadataComparison) -> str:
    """Format the overall status with color."""
    status = comparison.get_status_summary()
    if "FAIL" in status:
        return f"{Fore.RED}{Style.BRIGHT}{status}{Style.RESET_ALL}"
    elif "Major Changes" in status:
        return f"{Fore.YELLOW}{status}{Style.RESET_ALL}"
    elif "Minor Changes" in status:
        return f"{Fore.CYAN}{status}{Style.RESET_ALL}"
    else:
        return f"{Fore.GREEN}{status}{Style.RESET_ALL}"


def _format_section_status(comparison: MetadataComparison, section: str) -> str:
    """Format section status (PASS/FAIL)."""
    if section == 'critical':
        if comparison.critical_fields_match:
            return f"{Fore.GREEN}✓ PASS{Style.RESET_ALL}"
        else:
            return f"{Fore.RED}✗ FAIL{Style.RESET_ALL}"
    elif section == 'major':
        if comparison.major_fields_match:
            return f"{Fore.GREEN}✓ PASS{Style.RESET_ALL}"
        else:
            return f"{Fore.YELLOW}⚠ CHANGES{Style.RESET_ALL}"
    return ""


def _format_diff_indicator(diff) -> str:
    """Format the indicator symbol for a diff."""
    if diff.severity == DiffSeverity.CRITICAL:
        return f"{Fore.RED}✗{Style.RESET_ALL}"
    elif diff.severity == DiffSeverity.MAJOR:
        return f"{Fore.YELLOW}⚠{Style.RESET_ALL}"
    elif diff.severity == DiffSeverity.MINOR:
        return f"{Fore.CYAN}○{Style.RESET_ALL}"
    else:
        return f"{Fore.WHITE}ℹ{Style.RESET_ALL}"


def _format_diff_message(diff, verbose: bool) -> str:
    """Format the diff message."""
    if diff.diff_type == DiffType.MISSING:
        return f"{Fore.RED}{diff.message}{Style.RESET_ALL}"
    elif diff.diff_type == DiffType.ADDED:
        return f"{Fore.GREEN}{diff.message}{Style.RESET_ALL}"
    elif diff.diff_type == DiffType.CHANGED:
        if diff.field_name == 'summary':
            exp_len = len(str(diff.expected_value))
            act_len = len(str(diff.actual_value))
            sim_info = f" (similarity: {diff.similarity:.1%})" if diff.similarity else ""
            msg = f"CHANGED (length: {exp_len} → {act_len}){sim_info}"
            if not verbose:
                msg += " [Use -s for full diff]"
            return msg
        else:
            return diff.message
    else:
        return diff.message


def _truncate(text: any, max_len: int) -> str:
    """Truncate text to max length."""
    text_str = str(text) if text else ""
    if len(text_str) <= max_len:
        return text_str
    return text_str[:max_len] + "..."


def _generate_interpretation(comparison: MetadataComparison) -> list[str]:
    """Generate interpretation guidance based on diff patterns."""
    lines = []

    if comparison.has_critical_failures():
        lines.append(f"{Fore.RED}✗ SCRAPER BROKEN: Critical fields missing or wrong{Style.RESET_ALL}")
        lines.append(f"  → Check if website structure changed")
        lines.append(f"  → Review scraper selectors and parsing logic")
        lines.append(f"  → Check debug_pages/ for saved HTML")

    elif not comparison.major_fields_match:
        major_diffs = [d for d in comparison.field_diffs
                      if d.severity == DiffSeverity.MAJOR and d.diff_type == DiffType.MISSING]

        if major_diffs:
            lines.append(f"{Fore.YELLOW}⚠ POSSIBLE SCRAPER ISSUE: Major fields missing{Style.RESET_ALL}")
            lines.append(f"  → Fields affected: {', '.join(d.field_name for d in major_diffs)}")
            lines.append(f"  → May indicate scraper breakage")
        else:
            lines.append(f"{Fore.GREEN}✓ Scraper is working correctly{Style.RESET_ALL}")
            lines.append(f"{Fore.YELLOW}⚠ Service updated content (possibly legitimate){Style.RESET_ALL}")
            lines.append(f"  → Review changes to verify they are expected")
            lines.append(f"  → Update reference OPF if changes are legitimate")

    elif len(comparison.field_diffs) > 0:
        lines.append(f"{Fore.GREEN}✓ Scraper is working correctly{Style.RESET_ALL}")
        lines.append(f"{Fore.CYAN}ℹ Minor changes detected (expected variation){Style.RESET_ALL}")

    else:
        lines.append(f"{Fore.GREEN}✓ Perfect match - scraper working perfectly{Style.RESET_ALL}")

    return lines
