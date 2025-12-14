"""
Demo script showing how scraper weights work with LLM scoring.

This demonstrates the tiebreaker logic when LLM scores are similar.
"""

from src.models import SearchCandidate
from src.search.candidate_selection import CandidateSelector

# Create mock candidates with similar LLM scores
candidates = [
    SearchCandidate(
        url="https://www.goodreads.com/book/show/32758901",
        title="All Systems Red (The Murderbot Diaries #1)",
        snippet="The first Murderbot novel...",
        site_key="goodreads"
    ),
    SearchCandidate(
        url="https://www.audible.com/pd/All-Systems-Red-Audiobook/B071VYLZ7K",
        title="All Systems Red",
        snippet="Murderbot Diaries Book 1...",
        site_key="audible"
    ),
    SearchCandidate(
        url="https://lubimyczytac.pl/ksiazka/4896752/wszystkie-systemy-w-normie",
        title="Wszystkie systemy w normie (Murderbot Diaries #1)",
        snippet="Pierwsza powieść z serii...",
        site_key="lubimyczytac"
    )
]

# Simulate LLM scoring (similar scores)
scored_candidates = [
    (candidates[0], 0.85),  # goodreads
    (candidates[1], 0.87),  # audible
    (candidates[2], 0.86),  # lubimyczytac
]

print("=" * 80)
print("DEMONSTRATION: Scraper Weights as Tiebreaker")
print("=" * 80)

print("\nScenario: LLM scored 3 candidates with similar scores (within 0.1 bracket)")
print("\nOriginal LLM Scores:")
for candidate, score in scored_candidates:
    print(f"  [{candidate.site_key:15}] {score:.3f} - {candidate.title}")

# Create selector and apply weights
selector = CandidateSelector(enable_ai_selection=False)
weighted_results = selector._apply_scraper_weights(scored_candidates)

# Sort by final score
weighted_results.sort(key=lambda x: x[2], reverse=True)

print("\nAfter Applying Scraper Weights:")
print("  (Weight formula: final = llm_score * (1.0 + (weight - 1.0) * 0.1))")

for candidate, llm_score, final_score in weighted_results:
    from src.config import SCRAPER_REGISTRY
    weight = SCRAPER_REGISTRY[candidate.site_key]['weight']
    boost = final_score - llm_score
    print(f"  [{candidate.site_key:15}] LLM: {llm_score:.3f} -> Final: {final_score:.3f} "
          f"(weight: {weight}, boost: +{boost:.4f})")

winner = weighted_results[0][0]
print(f"\n{'='*80}")
print(f"WINNER: {winner.site_key} - {winner.title}")
print(f"{'='*80}")

print("\nHow it works:")
print("1. LLM scores all candidates (0.0 - 1.0)")
print("2. If scores are within 0.1 of the best score, apply weight multiplier")
print("3. lubimyczytac (weight 3.0) gets highest boost")
print("4. audible (weight 2.0) gets medium boost")
print("5. goodreads (weight 1.5) gets smallest boost")
print("6. This breaks ties in favor of preferred sources")
print("\nResult: Even with slightly lower LLM score, lubimyczytac wins!")
