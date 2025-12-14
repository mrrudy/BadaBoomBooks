"""Test that 0.0 scores don't result in selection."""

from src.models import SearchCandidate
from src.search.candidate_selection import CandidateSelector

print("="*80)
print("TEST: Zero Score Handling")
print("="*80)

# Create mock candidates
candidates = [
    SearchCandidate(
        url="https://www.goodreads.com/book/show/123",
        title="Wrong Book 1",
        snippet="Not related",
        site_key="goodreads"
    ),
    SearchCandidate(
        url="https://www.audible.com/pd/Wrong-Book-2",
        title="Wrong Book 2",
        snippet="Also not related",
        site_key="audible"
    ),
    SearchCandidate(
        url="https://lubimyczytac.pl/ksiazka/456/wrong-book-3",
        title="Wrong Book 3",
        snippet="Still not related",
        site_key="lubimyczytac"
    )
]

# Simulate LLM scoring with all 0.0 (all candidates failed)
scored_candidates = [
    (candidates[0], 0.0),
    (candidates[1], 0.0),
    (candidates[2], 0.0),
]

print("\nScenario: All candidates scored 0.0 by LLM (no good matches)")
print("\nLLM Scores:")
for candidate, score in scored_candidates:
    print(f"  [{candidate.site_key:15}] {score:.3f} - {candidate.title}")

# Create selector and apply weights
selector = CandidateSelector(enable_ai_selection=False)
weighted_results = selector._apply_scraper_weights(scored_candidates)

print("\nAfter Weight Application:")
print("  (Weights should NOT be applied when all scores are below 0.5)")
for candidate, llm_score, final_score in weighted_results:
    weight_applied = "YES" if abs(llm_score - final_score) > 0.001 else "NO"
    print(f"  [{candidate.site_key:15}] LLM: {llm_score:.3f}, Final: {final_score:.3f}, Weight applied: {weight_applied}")

# Check if any weights were applied
weights_were_applied = any(abs(llm - final) > 0.001 for _, llm, final in weighted_results)

print("\n" + "="*80)
if weights_were_applied:
    print("❌ FAIL: Weights were applied when all scores were 0.0!")
    print("   This is incorrect - weights should only apply when scores >= 0.5")
else:
    print("✅ PASS: Weights correctly NOT applied when all scores are 0.0")
    print("   All candidates will be rejected (no selection made)")

print("="*80)

# Now test with scores above threshold
print("\n" + "="*80)
print("TEST: Scores Above Threshold")
print("="*80)

scored_candidates_good = [
    (candidates[0], 0.85),
    (candidates[1], 0.87),
    (candidates[2], 0.86),
]

print("\nScenario: All candidates scored well (0.85-0.87)")
print("\nLLM Scores:")
for candidate, score in scored_candidates_good:
    print(f"  [{candidate.site_key:15}] {score:.3f}")

weighted_results_good = selector._apply_scraper_weights(scored_candidates_good)

print("\nAfter Weight Application:")
print("  (Weights SHOULD be applied when scores are good and similar)")
for candidate, llm_score, final_score in weighted_results_good:
    weight_applied = "YES" if abs(llm_score - final_score) > 0.001 else "NO"
    boost = final_score - llm_score
    print(f"  [{candidate.site_key:15}] LLM: {llm_score:.3f}, Final: {final_score:.3f}, "
          f"Boost: +{boost:.4f}, Weight applied: {weight_applied}")

weights_were_applied_good = any(abs(llm - final) > 0.001 for _, llm, final in weighted_results_good)

print("\n" + "="*80)
if not weights_were_applied_good:
    print("❌ FAIL: Weights were NOT applied when scores were good!")
    print("   This is incorrect - weights should apply when scores >= 0.5 and similar")
else:
    print("✅ PASS: Weights correctly applied when scores are above threshold")
    winner = sorted(weighted_results_good, key=lambda x: x[2], reverse=True)[0]
    print(f"   Winner: {winner[0].site_key} (should be lubimyczytac with highest weight)")

print("="*80)
