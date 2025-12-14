"""Test script for scraper weights and LLM scoring display."""

from src.config import SCRAPER_REGISTRY

print("Scraper Registry Weights:")
print("=" * 60)
for site_key, config in SCRAPER_REGISTRY.items():
    weight = config.get('weight', 'NOT SET')
    domain = config['domain']
    print(f"{site_key:15} | {domain:20} | Weight: {weight}")

print("\n" + "=" * 60)
print("\nWeight configuration:")
print("- lubimyczytac.pl: 3.0 (HIGHEST - most favored)")
print("- audible.com:     2.0 (medium)")
print("- goodreads.com:   1.5 (lowest)")
print("\nWeights are used as tiebreakers when LLM scores are within")
print("0.1 quality bracket (e.g., 0.85 vs 0.87)")
