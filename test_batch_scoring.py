"""Test the new batch scoring approach."""

from src.models import SearchCandidate
from src.search.llm_scoring import LLMScorer

print("="*80)
print("BATCH SCORING TEST")
print("="*80)

# Create mock candidates - simulating Murderbot Diaries scenario
candidates = [
    SearchCandidate(
        site_key='audible',
        url='https://www.audible.com/pd/All-Systems-Red',
        title='All Systems Red (The Murderbot Diaries, Book 1)',
        snippet='In a corporate-dominated spacefaring future, planetary missions must be approved and supplied by the Company.'
    ),
    SearchCandidate(
        site_key='audible',
        url='https://www.audible.com/pd/Artificial-Condition',
        title='Artificial Condition (The Murderbot Diaries, Book 2)',
        snippet='The second book in the Murderbot Diaries series. Murderbot travels to learn about its past.'
    ),
    SearchCandidate(
        site_key='goodreads',
        url='https://www.goodreads.com/book/show/32758901',
        title='All Systems Red (The Murderbot Diaries, #1)',
        snippet='A murderous android discovers itself in All Systems Red, a thrilling science fiction adventure by Martha Wells.'
    ),
    SearchCandidate(
        site_key='goodreads',
        url='https://www.goodreads.com/book/show/35519101',
        title='Artificial Condition (The Murderbot Diaries, #2)',
        snippet='The second Murderbot novel. Wrong book - this is volume 2, not volume 1.'
    ),
    SearchCandidate(
        site_key='lubimyczytac',
        url='https://lubimyczytac.pl/ksiazka/4896752/wszystkie-systemy-w-normie',
        title='Wszystkie systemy w normie (Pamiętniki Mordbota, #1)',
        snippet='Pierwsza powieść z serii Pamiętniki Mordbota. Polish edition of All Systems Red.'
    ),
    SearchCandidate(
        site_key='lubimyczytac',
        url='https://lubimyczytac.pl/ksiazka/4896753/sztuczny-stan',
        title='Sztuczny stan (Pamiętniki Mordbota, #2)',
        snippet='Druga powieść z serii. Polish edition of Artificial Condition - WRONG BOOK (volume 2).'
    ),
]

# Book info we're looking for
book_info = {
    'title': 'Wszystkie systemy w normie. Sztuczny stan',
    'author': 'Martha Wells',
    'series': 'Pamiętniki Mordbota',
    'volume': '1,2',  # Combined volumes 1 and 2
    'language': 'Polish'
}

search_term = "Wszystkie wskaźniki czerwone. Sztuczny stan (Pamiętniki Mordbota) by Martha Wells"

print(f"\nSearching for: {search_term}")
print(f"\nBook info:")
for key, value in book_info.items():
    print(f"  {key}: {value}")

print(f"\nCandidates to evaluate:")
for i, c in enumerate(candidates, 1):
    print(f"  {i}. [{c.site_key:15}] {c.title}")

# Initialize scorer
scorer = LLMScorer()

if not scorer.llm_available:
    print("\n❌ LLM not available - skipping test")
    print("   Configure .env file with LLM_API_KEY to test")
else:
    print(f"\n✓ LLM available (model: {scorer._initialize_llm.__self__.__dict__})")
    print("\nTesting batch scoring...")
    print("(This will make a single API call for all candidates)\n")

    # Test the prompt building
    prompt = scorer._build_batch_scoring_prompt(candidates, search_term, book_info)
    print("="*80)
    print("GENERATED PROMPT (first 500 chars):")
    print("="*80)
    print(prompt[:500] + "...")
    print("="*80)

    print("\nNote: This is a demo of the prompt. To test actual scoring,")
    print("run the full application with --llm-select flag.")

print("\n" + "="*80)
print("Key improvements in batch scoring:")
print("="*80)
print("✓ All candidates compared in single prompt")
print("✓ LLM can see full context and make relative comparisons")
print("✓ Temperature 0.3 allows reasoning while staying focused")
print("✓ Clear instruction that rejecting all is acceptable")
print("✓ Emphasis on exact match (same language, same volume)")
print("✓ Warning that 'same series' is NOT enough")
print("="*80)
