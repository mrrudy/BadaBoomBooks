"""
Pytest configuration and shared fixtures for BadaBoomBooks tests.

This module contains fixtures that are available to all test files,
including setup/teardown utilities and test data factories.
"""

import pytest
import shutil
from pathlib import Path


@pytest.fixture
def test_data_dir():
    """
    Fixture that returns the path to the test data directory.

    Returns:
        Path: Absolute path to src/tests/data/
    """
    return Path(__file__).parent / 'data'


@pytest.fixture
def expected_dir(test_data_dir):
    """
    Fixture that provides a clean expected output directory.

    Cleans the directory before each test to ensure isolation.

    Returns:
        Path: Absolute path to src/tests/data/expected/
    """
    expected = test_data_dir / 'expected'
    expected.mkdir(exist_ok=True)

    # Clean directory before test
    for item in expected.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    yield expected

    # Optional: Clean after test as well
    # Commented out to allow inspection of test results
    # for item in expected.iterdir():
    #     if item.is_dir():
    #         shutil.rmtree(item)
    #     else:
    #         item.unlink()


@pytest.fixture
def existing_dir(test_data_dir):
    """
    Fixture that returns the path to the existing test data directory.

    Contains static test data (audiobook folders with metadata.opf files).

    Returns:
        Path: Absolute path to src/tests/data/existing/
    """
    return test_data_dir / 'existing'


@pytest.fixture
def existing_dir_with_space(test_data_dir):
    """
    Fixture that returns the path to test data directory WITH SPACE in name.

    This tests the bug where paths with spaces + trailing backslashes fail.
    Contains static test data (audiobook folders with metadata.opf files).

    Returns:
        Path: Absolute path to src/tests/data/existing dir/
    """
    return test_data_dir / 'existing dir'


@pytest.fixture
def cleanup_queue_ini():
    """
    Fixture that ensures queue.ini is cleaned up after tests.

    Yields control to the test, then removes queue.ini if it exists.
    """
    queue_file = Path('queue.ini')

    # Clean before test
    if queue_file.exists():
        queue_file.unlink()

    yield

    # Clean after test
    if queue_file.exists():
        queue_file.unlink()


@pytest.fixture
def sample_opf_content():
    """
    Fixture that returns the sample OPF XML content for testing.

    Returns:
        str: Complete OPF XML content with UTF-8 test characters
    """
    return """<?xml version='1.0' encoding='utf-8'?>
<ns0:package xmlns:dc='http://purl.org/dc/elements/1.1/' xmlns:ns0='http://www.idpf.org/2007/opf' unique-identifier='BookId' version='2.0'>
  <ns0:metadata xmlns:dc="http://purl.org/dc/elements/1.1/"
          xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>Proper Title</dc:title>
    <dc:subtitle></dc:subtitle>
    <dc:description>Lorem ipsum dolor sit ąmęt, cónsęctętür ądîpîsĉîng ęlît. Śęd dö ęïüsmöd tęmpör încîdîdünt üt łäbörę ęt döłörę mägnä äłîqüä. Üt ęnîm äd mînîm vęnîäm, qüîs nöstrüd ęxęrcîtätîön üłłämcö łäbörîs nîsî üt äłîqüîp ęx ęä cömmödö cönsęqüät. Żółć gęślą jąźń.</dc:description>
    <dc:creator opf:role="aut">Aname A. Asurname</dc:creator>
    <dc:creator opf:role="nrt"></dc:creator>
    <dc:publisher></dc:publisher>
    <dc:date></dc:date>
    <dc:language>pol</dc:language>
    <dc:subject>fantasy</dc:subject>
    <dc:subject>science fiction</dc:subject>
    <dc:identifier opf:scheme="ISBN">9799379643216</dc:identifier>
    <dc:identifier opf:scheme="ASIN"></dc:identifier>
    <dc:source></dc:source>
    <ns0:meta name="calibre:series" content="Series Title" />
    <ns0:meta name="calibre:series_index" content="22" />
    <dc:tag></dc:tag>
  </ns0:metadata>
</ns0:package>
"""


# ============================================================================
# Scraper Testing Fixtures
# ============================================================================

@pytest.fixture
def scraper_test_data_dir(test_data_dir):
    """
    Fixture that returns the path to the scraper test data directory.

    Returns:
        Path: Absolute path to src/tests/data/scrapers/
    """
    return test_data_dir / 'scrapers'


@pytest.fixture
def lubimyczytac_samples(scraper_test_data_dir):
    """
    Fixture that returns all LubimyCzytac test sample OPF files.

    Returns:
        List[Path]: List of paths to metadata.opf files in lubimyczytac/ subdirectories
    """
    lubimyczytac_dir = scraper_test_data_dir / 'lubimyczytac'
    if not lubimyczytac_dir.exists():
        return []
    return sorted(lubimyczytac_dir.glob('*/metadata.opf'))


@pytest.fixture
def audible_samples(scraper_test_data_dir):
    """
    Fixture that returns all Audible test sample OPF files.

    Returns:
        List[Path]: List of paths to metadata.opf files in audible/ subdirectories
    """
    audible_dir = scraper_test_data_dir / 'audible'
    if not audible_dir.exists():
        return []
    return sorted(audible_dir.glob('*/metadata.opf'))


@pytest.fixture
def goodreads_samples(scraper_test_data_dir):
    """
    Fixture that returns all Goodreads test sample OPF files.

    Returns:
        List[Path]: List of paths to metadata.opf files in goodreads/ subdirectories
    """
    goodreads_dir = scraper_test_data_dir / 'goodreads'
    if not goodreads_dir.exists():
        return []
    return sorted(goodreads_dir.glob('*/metadata.opf'))


@pytest.fixture
def all_scraper_samples(lubimyczytac_samples, audible_samples, goodreads_samples):
    """
    Fixture that returns all scraper test samples organized by service.

    Returns:
        Dict[str, List[Path]]: Dictionary mapping service name to list of OPF file paths
    """
    return {
        'lubimyczytac': lubimyczytac_samples,
        'audible': audible_samples,
        'goodreads': goodreads_samples,
    }


@pytest.fixture
def random_sample_per_service(all_scraper_samples):
    """
    Fixture that returns one random OPF per service for quick smoke tests.

    Returns:
        Dict[str, Optional[Path]]: Dictionary mapping service name to a random OPF file path
                                   (or None if no samples available for that service)
    """
    import random

    result = {}
    for service, samples in all_scraper_samples.items():
        if samples:
            result[service] = random.choice(samples)
        else:
            result[service] = None

    return result


@pytest.fixture
def metadata_processor():
    """
    Fixture that provides a MetadataProcessor instance for reading OPF files.

    Returns:
        MetadataProcessor: Instance for OPF operations
    """
    from src.processors.metadata_operations import MetadataProcessor
    return MetadataProcessor(dry_run=False)


# ============================================================================
# Database Isolation for Tests
# ============================================================================

@pytest.fixture
def test_database(tmp_path):
    """
    Fixture that provides an isolated test database.

    Creates a temporary database file for each test to prevent interference
    with production operations. The database is automatically cleaned up
    after the test completes.

    Args:
        tmp_path: Pytest's built-in temporary directory fixture

    Returns:
        Path: Path to the temporary database file

    Yields:
        Path: Path to the test database (during test execution)
    """
    import os
    from pathlib import Path

    # Create test database in pytest's temporary directory
    test_db_path = tmp_path / "test_badaboombooksqueue.db"

    # Set environment variable to override database path
    # This is read by QueueManager to use test database
    old_db_path = os.environ.get('BADABOOMBOOKS_DB_PATH')
    os.environ['BADABOOMBOOKS_DB_PATH'] = str(test_db_path)

    yield test_db_path

    # Cleanup: Restore original database path
    if old_db_path is not None:
        os.environ['BADABOOMBOOKS_DB_PATH'] = old_db_path
    else:
        os.environ.pop('BADABOOMBOOKS_DB_PATH', None)

    # Database file is automatically cleaned up by tmp_path fixture
