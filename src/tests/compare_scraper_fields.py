"""
Quick script to compare metadata fields across scraper test samples.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.processors.metadata_operations import MetadataProcessor

# Read all OPF files
processor = MetadataProcessor(dry_run=False)

services = {
    'lubimyczytac': list(Path('src/tests/data/scrapers/lubimyczytac').glob('*/metadata.opf')),
    'audible': list(Path('src/tests/data/scrapers/audible').glob('*/metadata.opf')),
    'goodreads': list(Path('src/tests/data/scrapers/goodreads').glob('*/metadata.opf'))
}

# Field definitions
fields = [
    'title', 'subtitle', 'author', 'narrator', 'publisher',
    'publishyear', 'language', 'summary', 'genres', 'series',
    'volumenumber', 'isbn', 'asin', 'url', 'cover_url'
]

# Collect data per service
service_data = {}
for service, opf_files in services.items():
    field_stats = {field: {'present': 0, 'missing': 0, 'samples': []} for field in fields}

    for opf_path in opf_files:
        metadata = processor.read_opf_metadata(opf_path)
        sample_name = opf_path.parent.name

        for field in fields:
            value = getattr(metadata, field, '')
            has_value = bool(value and str(value).strip())

            if has_value:
                field_stats[field]['present'] += 1
            else:
                field_stats[field]['missing'] += 1
                field_stats[field]['samples'].append(sample_name)

    service_data[service] = {
        'total_samples': len(opf_files),
        'field_stats': field_stats
    }

# Print comparison table
print('=' * 120)
print('METADATA FIELD COMPARISON ACROSS SERVICES')
print('=' * 120)
print()
lc_count = service_data["lubimyczytac"]["total_samples"]
au_count = service_data["audible"]["total_samples"]
gr_count = service_data["goodreads"]["total_samples"]
print(f'Sample counts: LubimyCzytac={lc_count}, Audible={au_count}, Goodreads={gr_count}')
print()

# Header
header = f"{'Field':<15} | {'LubimyCzytac':<20} | {'Audible':<20} | {'Goodreads':<20} | Notes"
print(header)
print('-' * 120)

for field in fields:
    lc_present = service_data['lubimyczytac']['field_stats'][field]['present']
    lc_total = service_data['lubimyczytac']['total_samples']
    lc_pct = f'{lc_present}/{lc_total} ({100*lc_present//lc_total if lc_total else 0}%)'

    au_present = service_data['audible']['field_stats'][field]['present']
    au_total = service_data['audible']['total_samples']
    au_pct = f'{au_present}/{au_total} ({100*au_present//au_total if au_total else 0}%)'

    gr_present = service_data['goodreads']['field_stats'][field]['present']
    gr_total = service_data['goodreads']['total_samples']
    gr_pct = f'{gr_present}/{gr_total} ({100*gr_present//gr_total if gr_total else 0}%)'

    # Determine notes
    notes = []
    if lc_present == lc_total and au_present == au_total and gr_present == gr_total:
        notes.append('✓ All services')
    elif lc_present == 0 and au_present == 0 and gr_present == 0:
        notes.append('✗ None')
    else:
        if lc_present == lc_total:
            notes.append('✓ LC')
        if au_present == au_total:
            notes.append('✓ AU')
        if gr_present == gr_total:
            notes.append('✓ GR')

    row = f'{field:<15} | {lc_pct:<20} | {au_pct:<20} | {gr_pct:<20} | {" ".join(notes)}'
    print(row)

print()
print('=' * 120)
print('MISSING FIELDS BY SERVICE')
print('=' * 120)

for service in ['lubimyczytac', 'audible', 'goodreads']:
    print(f'\n{service.upper()}:')
    missing_any = False
    for field in fields:
        missing = service_data[service]['field_stats'][field]['missing']
        total = service_data[service]['total_samples']
        if missing > 0:
            missing_any = True
            samples = service_data[service]['field_stats'][field]['samples']
            print(f'  ✗ {field}: {missing}/{total} missing in {samples}')
    if not missing_any:
        print('  ✓ All fields present in all samples')

print()
print('=' * 120)
print('FIELD COMPLETENESS RANKING (by % of fields populated across all samples)')
print('=' * 120)

service_completeness = {}
for service, data in service_data.items():
    total_fields = len(fields) * data['total_samples']
    populated_fields = sum(
        data['field_stats'][field]['present']
        for field in fields
    )
    completeness_pct = (populated_fields / total_fields * 100) if total_fields else 0
    service_completeness[service] = completeness_pct

for service, pct in sorted(service_completeness.items(), key=lambda x: x[1], reverse=True):
    bar_length = int(pct / 2)
    bar = '█' * bar_length
    print(f'{service.upper():<15} {pct:>5.1f}% {bar}')
