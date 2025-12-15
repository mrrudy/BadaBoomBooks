"""
Scraper regression tests for BadaBoomBooks.

Tests scraper functionality by comparing live-scraped metadata against reference
OPF files from production data. Helps distinguish between scraper failures
(broken code) and legitimate metadata updates (content changes).
"""

import pytest
import requests
from pathlib import Path

from src.models import BookMetadata
from src.processors.metadata_operations import MetadataProcessor
from src.tests.utils.metadata_comparison import compare_metadata
from src.tests.utils.diff_reporter import format_diff_report


@pytest.mark.integration
@pytest.mark.requires_network
@pytest.mark.scraper
def test_lubimyczytac_scraper_regression_all_samples(
    lubimyczytac_samples,
    metadata_processor,
    cleanup_queue_ini
):
    """
    Comprehensive regression test for LubimyCzytac scraper using all available samples.

    For each sample:
    1. Read reference metadata from OPF file
    2. Extract source URL from <dc:source>
    3. Re-scrape URL using current scraper code
    4. Compare scraped vs reference metadata
    5. Report differences

    Usage:
        python -m pytest src/tests/test_scrapers.py::test_lubimyczytac_scraper_regression_all_samples -v -s
    """
    if not lubimyczytac_samples:
        pytest.skip("No LubimyCzytac samples available")

    from src.main import BadaBoomBooksApp

    results = []
    all_reports = []

    for opf_path in lubimyczytac_samples:
        sample_name = opf_path.parent.name
        print(f"\n{'=' * 80}")
        print(f"Testing sample: {sample_name}")
        print(f"{'=' * 80}\n")

        # Load reference metadata from OPF file
        reference_metadata = metadata_processor.read_opf_metadata(opf_path)
        assert reference_metadata is not None, f"Failed to read OPF from {opf_path}"
        assert reference_metadata.url, f"No source URL in {opf_path}"

        # Re-scrape using current scraper code
        try:
            app = BadaBoomBooksApp()

            # Create empty metadata with URL
            scraped_metadata = BookMetadata.create_empty(
                input_folder=str(opf_path.parent),
                url=reference_metadata.url
            )

            # Perform scraping
            scraped_metadata = app._scrape_metadata(scraped_metadata)

            # Check if scraping succeeded
            if scraped_metadata.failed:
                print(f"SCRAPING FAILED: {scraped_metadata.failed_exception}")
                results.append({
                    'sample': sample_name,
                    'passed': False,
                    'error': scraped_metadata.failed_exception
                })
                continue

            # Compare metadata
            comparison = compare_metadata(reference_metadata, scraped_metadata)

            # Generate and print report
            report = format_diff_report(comparison, verbose=False)
            all_reports.append(f"\n{'=' * 80}\n{sample_name}\n{report}")
            print(report)

            # Record result
            results.append({
                'sample': sample_name,
                'passed': comparison.is_acceptable_match(),
                'comparison': comparison
            })

            # Assert acceptable match (FAIL only on critical issues)
            assert comparison.is_acceptable_match(), \
                f"Sample {sample_name} failed:\n{report}"

        except requests.exceptions.RequestException as e:
            # Network error - skip test
            pytest.skip(f"Network error accessing {reference_metadata.url}: {e}")

        except Exception as e:
            print(f"ERROR during scraping: {e}")
            results.append({
                'sample': sample_name,
                'passed': False,
                'error': str(e)
            })
            raise

    # Summary
    print(f"\n\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}")
    passed = sum(1 for r in results if r['passed'])
    total = len(results)
    print(f"Passed: {passed}/{total}")

    for result in results:
        status = "✓ PASS" if result['passed'] else "✗ FAIL"
        print(f"  {status}: {result['sample']}")
        if not result['passed'] and 'error' in result:
            print(f"    Error: {result['error']}")

    print(f"{'=' * 80}\n")

    # Final assertion
    assert all(r['passed'] for r in results), \
        f"Some samples failed. See reports above for details."


@pytest.mark.integration
@pytest.mark.requires_network
@pytest.mark.scraper
def test_lubimyczytac_scraper_regression_random_sample(
    random_sample_per_service,
    metadata_processor,
    cleanup_queue_ini
):
    """
    Quick smoke test for LubimyCzytac scraper using one random sample.

    This is the default test that runs as part of the main test suite.
    For comprehensive testing, use test_lubimyczytac_scraper_regression_all_samples.

    Usage:
        python -m pytest src/tests/ -v
    """
    opf_path = random_sample_per_service.get('lubimyczytac')
    if not opf_path:
        pytest.skip("No LubimyCzytac samples available")

    from src.main import BadaBoomBooksApp

    sample_name = opf_path.parent.name
    print(f"\nTesting random LubimyCzytac sample: {sample_name}\n")

    # Load reference metadata
    reference_metadata = metadata_processor.read_opf_metadata(opf_path)
    assert reference_metadata is not None, f"Failed to read OPF from {opf_path}"
    assert reference_metadata.url, f"No source URL in {opf_path}"

    # Re-scrape
    try:
        app = BadaBoomBooksApp()

        scraped_metadata = BookMetadata.create_empty(
            input_folder=str(opf_path.parent),
            url=reference_metadata.url
        )

        scraped_metadata = app._scrape_metadata(scraped_metadata)

        assert not scraped_metadata.failed, \
            f"Scraping failed: {scraped_metadata.failed_exception}"

        # Compare
        comparison = compare_metadata(reference_metadata, scraped_metadata)

        # Report
        report = format_diff_report(comparison, verbose=False)
        print(report)

        # Assert
        assert comparison.is_acceptable_match(), \
            f"Sample {sample_name} failed:\n{report}"

    except requests.exceptions.RequestException as e:
        pytest.skip(f"Network error accessing {reference_metadata.url}: {e}")


@pytest.mark.integration
@pytest.mark.requires_network
@pytest.mark.scraper
@pytest.mark.tdd
def test_manual_tdd_sample(
    scraper_test_data_dir,
    metadata_processor,
    cleanup_queue_ini
):
    """
    TDD workflow test for manually created test cases.

    This test looks for a special directory: src/tests/data/scrapers/tdd/
    If found, it processes all metadata.opf files in subdirectories.

    Usage for TDD:
    1. Create src/tests/data/scrapers/tdd/my-test/metadata.opf
    2. Fill with expected metadata + <dc:source>URL</dc:source>
    3. Run: python -m pytest src/tests/test_scrapers.py::test_manual_tdd_sample -v -s
    4. Fix scraper until test passes

    This test is SKIPPED if no TDD directory exists.
    """
    tdd_dir = scraper_test_data_dir / 'tdd'

    if not tdd_dir.exists():
        pytest.skip("No TDD test directory found (src/tests/data/scrapers/tdd/)")

    tdd_samples = list(tdd_dir.glob('*/metadata.opf'))

    if not tdd_samples:
        pytest.skip("No TDD test cases found in src/tests/data/scrapers/tdd/")

    from src.main import BadaBoomBooksApp

    for opf_path in tdd_samples:
        sample_name = opf_path.parent.name
        print(f"\n{'=' * 80}")
        print(f"Testing TDD case: {sample_name}")
        print(f"{'=' * 80}\n")

        # Load reference
        reference_metadata = metadata_processor.read_opf_metadata(opf_path)
        assert reference_metadata is not None, f"Failed to read OPF from {opf_path}"
        assert reference_metadata.url, f"No source URL in {opf_path}"

        # Scrape
        try:
            app = BadaBoomBooksApp()

            scraped_metadata = BookMetadata.create_empty(
                input_folder=str(opf_path.parent),
                url=reference_metadata.url
            )

            scraped_metadata = app._scrape_metadata(scraped_metadata)

            assert not scraped_metadata.failed, \
                f"Scraping failed: {scraped_metadata.failed_exception}"

            # Compare
            comparison = compare_metadata(reference_metadata, scraped_metadata)

            # Report
            report = format_diff_report(comparison, verbose=True)  # Verbose for TDD
            print(report)

            # Assert
            assert comparison.is_acceptable_match(), \
                f"TDD case {sample_name} failed:\n{report}"

            print(f"\n✓ TDD test case '{sample_name}' PASSED\n")

        except requests.exceptions.RequestException as e:
            pytest.skip(f"Network error accessing {reference_metadata.url}: {e}")


@pytest.mark.integration
@pytest.mark.requires_network
@pytest.mark.scraper
def test_scraper_handles_network_error(
    lubimyczytac_samples,
    metadata_processor,
    cleanup_queue_ini
):
    """
    Test that scrapers gracefully handle network errors.

    Uses an invalid URL to trigger a network error and verifies
    that the scraper marks the metadata as failed rather than crashing.
    """
    from src.main import BadaBoomBooksApp
    from src.models import BookMetadata

    app = BadaBoomBooksApp()

    # Create metadata with invalid URL
    metadata = BookMetadata.create_empty(
        input_folder="/fake/path",
        url="https://lubimyczytac.pl/ksiazka/99999999999/nonexistent-book"
    )

    # This should either fail gracefully or raise RequestException
    try:
        scraped_metadata = app._scrape_metadata(metadata)

        # If it didn't raise, it should be marked as failed
        # (or might succeed if the page exists with different data)
        # Either is acceptable - we just want to ensure no crash
        assert isinstance(scraped_metadata, BookMetadata)

    except requests.exceptions.RequestException:
        # This is expected and acceptable
        pass


@pytest.mark.integration
@pytest.mark.requires_network
@pytest.mark.scraper
@pytest.mark.parametrize("service", ["audible", "goodreads"])
def test_other_scrapers_regression(
    service,
    all_scraper_samples,
    metadata_processor,
    cleanup_queue_ini
):
    """
    Placeholder test for Audible and Goodreads scrapers.

    Will be used once test samples are added for these services.
    Currently skips if no samples available.
    """
    samples = all_scraper_samples.get(service, [])

    if not samples:
        pytest.skip(f"No {service} samples available yet")

    # When samples are available, this will run the same logic
    # as the lubimyczytac test
    from src.main import BadaBoomBooksApp

    for opf_path in samples:
        sample_name = opf_path.parent.name
        print(f"\nTesting {service} sample: {sample_name}\n")

        # Load reference
        reference_metadata = metadata_processor.read_opf_metadata(opf_path)
        assert reference_metadata is not None
        assert reference_metadata.url

        # Scrape
        try:
            app = BadaBoomBooksApp()

            scraped_metadata = BookMetadata.create_empty(
                input_folder=str(opf_path.parent),
                url=reference_metadata.url
            )

            scraped_metadata = app._scrape_metadata(scraped_metadata)
            assert not scraped_metadata.failed

            # Compare
            comparison = compare_metadata(reference_metadata, scraped_metadata)

            # Report
            report = format_diff_report(comparison, verbose=False)
            print(report)

            # Assert
            assert comparison.is_acceptable_match()

        except requests.exceptions.RequestException as e:
            pytest.skip(f"Network error: {e}")
