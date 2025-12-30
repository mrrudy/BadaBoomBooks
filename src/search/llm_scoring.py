"""
LLM-based candidate scoring.

This module uses litellm to score search candidates against book metadata
using various LLM providers (OpenAI, Anthropic, local models).
"""

import re
import logging as log
from typing import List, Tuple, Optional, Dict

from ..models import SearchCandidate
from ..config import LLM_CONFIG


class LLMScorer:
    """Handles LLM-based scoring of search candidates."""

    def __init__(self):
        self.llm_available = False
        self._initialize_llm()

    def _initialize_llm(self):
        """Initialize litellm if available and configured."""
        if not LLM_CONFIG['enabled']:
            log.debug("LLM scoring disabled - no API key configured")
            return

        try:
            import litellm

            # Configure litellm for local models if base URL provided
            if LLM_CONFIG['base_url']:
                litellm.api_base = LLM_CONFIG['base_url']
                log.debug(f"LLM configured with base URL: {LLM_CONFIG['base_url']}")

            self.llm_available = True
            log.info(f"LLM scoring enabled with model: {LLM_CONFIG['model']}")

        except ImportError:
            log.warning("litellm not available - LLM scoring disabled. Install with: pip install litellm")
            self.llm_available = False
        except Exception as e:
            log.error(f"Failed to initialize LLM: {e}")
            self.llm_available = False

    def score_candidates(self, candidates: List[SearchCandidate],
                        search_term: str,
                        book_info: dict = None) -> List[Tuple[SearchCandidate, float]]:
        """
        Score all candidates using LLM in a single batch prompt.

        Args:
            candidates: List of search candidates
            search_term: Original search term
            book_info: Optional book context (from existing metadata)

        Returns:
            List of (candidate, score) tuples where score is 0-1
        """
        if not self.llm_available:
            return [(c, 0.0) for c in candidates]

        # Use batch scoring (all candidates in one prompt for better comparison)
        return self._score_candidates_batch(candidates, search_term, book_info)

    def _score_candidates_batch(self, candidates: List[SearchCandidate],
                                search_term: str,
                                book_info: dict = None) -> List[Tuple[SearchCandidate, float]]:
        """
        Score all candidates in a single batch prompt for better comparison.

        Args:
            candidates: List of search candidates
            search_term: Original search term
            book_info: Optional book context

        Returns:
            List of (candidate, score) tuples
        """
        try:
            import litellm

            prompt = self._build_batch_scoring_prompt(candidates, search_term, book_info)

            response = litellm.completion(
                model=LLM_CONFIG['model'],
                api_key=LLM_CONFIG['api_key'],
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,  # Higher temperature for reasoning and comparison
                max_tokens=LLM_CONFIG.get('max_tokens', 4096)
            )

            # Extract scores from response
            response_text = response.choices[0].message.content.strip()
            scores = self._parse_batch_scores(response_text, len(candidates))

            # Pair candidates with scores
            scored = []
            for i, candidate in enumerate(candidates):
                score = scores[i] if i < len(scores) else 0.0
                scored.append((candidate, score))
                log.debug(f"LLM batch scored '{candidate.title}' ({candidate.site_key}) as {score:.2f}")

            return scored

        except ImportError:
            log.debug("litellm not available for scoring")
            return [(c, 0.0) for c in candidates]
        except Exception as e:
            log.warning(f"LLM batch scoring failed: {e}")
            return [(c, 0.0) for c in candidates]

    def _score_single_candidate(self, candidate: SearchCandidate,
                                search_term: str,
                                book_info: dict = None) -> float:
        """
        Score a single candidate using LLM.

        Args:
            candidate: Search candidate to score
            search_term: Original search term
            book_info: Optional book context

        Returns:
            Score from 0.0 to 1.0
        """
        try:
            import litellm

            prompt = self._build_scoring_prompt(candidate, search_term, book_info)

            response = litellm.completion(
                model=LLM_CONFIG['model'],
                api_key=LLM_CONFIG['api_key'],
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,  # Low temperature for consistent scoring
                max_tokens=LLM_CONFIG.get('max_tokens', 4096)  # Configurable, default 4096
            )

            # Extract score from response
            score_text = response.choices[0].message.content.strip()
            score = self._parse_score(score_text)

            log.debug(f"LLM scored '{candidate.title}' as {score:.2f}")
            return score

        except ImportError:
            log.debug("litellm not available for scoring")
            return 0.0
        except Exception as e:
            log.warning(f"LLM scoring failed for '{candidate.title}': {e}")
            return 0.0  # Fallback to 0 on error

    def _build_scoring_prompt(self, candidate: SearchCandidate,
                             search_term: str,
                             book_info: dict = None) -> str:
        """
        Build prompt for scoring a candidate.

        Args:
            candidate: Search candidate
            search_term: Original search term
            book_info: Optional book context

        Returns:
            Prompt string for LLM
        """
        context = f"Search term: {search_term}\n\n"

        if book_info:
            context += "Book information:\n"

            # Check for multi-source metadata
            if 'sources' in book_info:
                sources = book_info['sources']
                folder_data = sources.get('folder', {})
                id3_data = sources.get('id3', {})

                if folder_data.get('raw'):
                    context += f"  Folder name: {folder_data['raw']}\n"

                if id3_data.get('garbage_detected'):
                    context += "  ⚠ WARNING: ID3 tags contain garbage data - trust folder name\n"
                elif id3_data.get('valid'):
                    if id3_data.get('title'):
                        context += f"  ID3 Title: {id3_data['title']}\n"
                    if id3_data.get('author'):
                        context += f"  ID3 Author: {id3_data['author']}\n"
            else:
                # Legacy single-source
                if book_info.get('title'):
                    context += f"  Title: {book_info['title']}\n"
                if book_info.get('author'):
                    context += f"  Author: {book_info['author']}\n"
                if book_info.get('series'):
                    context += f"  Series: {book_info['series']}"
                    if book_info.get('volume'):
                        context += f" (Volume {book_info['volume']})"
                    context += "\n"
                if book_info.get('narrator'):
                    context += f"  Narrator: {book_info['narrator']}\n"

        # Truncate snippet to avoid token limits
        snippet = candidate.snippet[:300] if candidate.snippet else "No snippet available"

        prompt = f"""Score the relevance of this search result to the book being searched.

{context}
Search result:
  Site: {candidate.site_key}
  Title: {candidate.title}
  Snippet: {snippet}

Return ONLY a number between 0.0 and 1.0 where:
- 1.0 = Perfect match (exact title and author match)
- 0.7-0.9 = Very good match (clear match with minor differences)
- 0.4-0.6 = Possible match (similar but uncertain)
- 0.0-0.3 = Poor match or wrong book

Score:"""

        return prompt

    def _build_batch_scoring_prompt(self, candidates: List[SearchCandidate],
                                    search_term: str,
                                    book_info: dict = None) -> str:
        """
        Build prompt for scoring all candidates in one batch.

        Args:
            candidates: List of search candidates
            search_term: Original search term
            book_info: Optional book context

        Returns:
            Prompt string for LLM
        """
        context = f"Primary search term: {search_term}\n\n"

        if book_info:
            context += "Book information (what we're looking for):\n"

            # Check if we have multi-source metadata
            if 'sources' in book_info:
                sources = book_info['sources']

                # Show folder name (always reliable)
                folder_data = sources.get('folder', {})
                if folder_data.get('raw'):
                    context += f"  Folder name: {folder_data['raw']}\n"
                    if folder_data.get('cleaned') and folder_data['cleaned'] != folder_data['raw']:
                        context += f"    (cleaned: {folder_data['cleaned']})\n"

                # Show ID3 data with warnings if garbage detected
                id3_data = sources.get('id3', {})
                if id3_data.get('garbage_detected'):
                    context += "\n  ⚠ WARNING: ID3 tags appear to contain garbage data (domains/URLs/duplicates):\n"
                    if id3_data.get('title'):
                        context += f"    ID3 Title: {id3_data['title']} [MAY BE UNRELIABLE]\n"
                    if id3_data.get('author'):
                        context += f"    ID3 Author: {id3_data['author']} [MAY BE UNRELIABLE]\n"
                    context += "  → RECOMMENDATION: Trust folder name over ID3 tags if they conflict\n\n"
                elif id3_data.get('valid'):
                    context += "\n  ID3 Tag Metadata:\n"
                    if id3_data.get('title'):
                        context += f"    Title: {id3_data['title']}\n"
                    if id3_data.get('author'):
                        context += f"    Author: {id3_data['author']}\n"
                    if id3_data.get('album'):
                        context += f"    Album/Series: {id3_data['album']}\n"

                # Show source being used
                context += f"\n  Metadata source: {book_info.get('source', 'unknown')}\n"

            else:
                # Legacy single-source metadata
                if book_info.get('title'):
                    context += f"  Title: {book_info['title']}\n"
                if book_info.get('author'):
                    context += f"  Author: {book_info['author']}\n"
                if book_info.get('series'):
                    context += f"  Series: {book_info['series']}"
                    if book_info.get('volume'):
                        context += f" (Volume {book_info['volume']})"
                    context += "\n"
                if book_info.get('narrator'):
                    context += f"  Narrator: {book_info['narrator']}\n"
                if book_info.get('language'):
                    context += f"  Language: {book_info['language']}\n"
                context += f"  Source: {book_info.get('source', 'folder name')}\n"

        # Build candidate list
        candidates_text = ""
        for i, candidate in enumerate(candidates, 1):
            # Truncate snippet to avoid token limits
            snippet = candidate.snippet[:200] if candidate.snippet else "No description available"
            candidates_text += f"\nCandidate {i}:\n"
            candidates_text += f"  Source: {candidate.site_key}\n"
            candidates_text += f"  Title: {candidate.title}\n"
            candidates_text += f"  Description: {snippet}\n"

        prompt = f"""You are helping to match audiobook metadata. Compare the search results below to find the EXACT book we're looking for.

{context}
CANDIDATES TO EVALUATE:
{candidates_text}

SCORING CRITERIA (in order of importance):

1. PERFECT MATCH (0.9-1.0):
   - Title matches (ignoring narrator names, bitrate info like "192kbps", "czyta X", "narrated by")
   - Author name matches (allow 1-2 character differences due to typos/diacritics)
     * Examples: "Čapek"="Capek", "José"="Jose", "Müller"="Muller", "Dostoyevsky"="Dostoevsky"
     * One letter difference in first/last name is acceptable (typo tolerance)
   - Same language edition
   - Same narrator if specified in folder name (optional)
   - CRITICAL: Must be the EXACT book, not just same series

2. VERY GOOD MATCH (0.7-0.9):
   - Very similar title (minor differences in subtitle or edition)
   - Same author (with or without diacritics)
   - Language matches
   - Narrator may differ or be unspecified

3. POSSIBLE MATCH (0.5-0.6):
   - Similar title but uncertain
   - Same author but different edition or format
   - May be same series but different volume

4. POOR MATCH (0.0-0.4):
   - Wrong book from same series (different volume number)
   - Wrong language edition
   - Different book by same author
   - Completely unrelated

IMPORTANT PARSING RULES FOR FOLDER NAMES:
- Folder names often contain EXTRA INFO not in the book title:
  * Narrator: "czyta X" (Polish), "narrated by X" (English), "read by X"
  * Bitrate: "192kbps", "128kbps", "64kbps"
  * Format info: "mp3", "m4b", "audiobook"
- IGNORE these extra details when matching title
- Example: "Capek Karel - Fabryka absolutu czyta A. Ziajkiewicz 192kbps"
  → Core title: "Fabryka absolutu"
  → Author: "Karel Capek"
  → Narrator: "A. Ziajkiewicz" (IGNORE for matching)
  → Bitrate: "192kbps" (IGNORE for matching)

DIACRITICS AND CHARACTER EQUIVALENCE:
- Treat diacritics and accented characters as equivalent to their base characters:
  * Latin Extended: č/c, ć/c, ę/e, ą/a, ł/l, ó/o, ń/n, ś/s, ź/z, ż/z
  * French: é/e, è/e, ê/e, ç/c, à/a, ù/u, û/u
  * German: ä/a, ö/o, ü/u, ß/ss
  * Spanish: ñ/n, á/a, é/e, í/i, ó/o, ú/u
  * Nordic: å/a, ø/o, æ/ae
  * And all other language-specific diacritics
- Examples:
  * "Karel Čapek" (Czech) = "Karel Capek" (romanized)
  * "José García" = "Jose Garcia"
  * "François" = "Francois"
- Case differences are NOT significant: "Fabryka Absolutu" = "fabryka absolutu"

LANGUAGE MATCHING:
- Same language is a strong positive indicator
- Different romanization/transliteration of same language content is acceptable
- If folder and candidate use same alphabet/script (Cyrillic, Latin, etc) → likely GOOD match
- If folder is one language but candidate is clearly different language → POOR match (different edition)
- Examples of GOOD matches despite character differences:
  * "Müller" (German) = "Muller" (romanized)
  * "Dostoyevsky" (English) = "Достоевский" (Cyrillic original) = "Dostoievski" (alternate romanization)

IMPORTANT RULES FOR CONFLICTING METADATA:
- **When ID3 tags conflict with folder name, consider BOTH sources:**
  * Folder name is often more reliable (manually organized)
  * ID3 "Album/Series" field may contain the ACTUAL book title
  * ID3 "Title" field may contain track info like "1. I", "Chapter 1", "Part 1"
  * Strip common prefixes from ID3 titles: "Author:", "Title:", labels, etc.
- **Example of misleading ID3 tags:**
  * Folder: "Slaughter Karin - Moje sliczne czyta Filip Kosior 224kbps"
  * ID3 Title: "1. I" (track/chapter number - IGNORE)
  * ID3 Album/Series: "Moje śliczne" (actual book title - USE THIS!)
  * Candidate: "Moje śliczne by Karin Slaughter"
  * → This IS a match! Use Album/Series field as the real title.
- **Matching strategy:**
  1. If folder name clearly contains book title → trust folder name
  2. If ID3 Title looks like track info ("1.", "Chapter", "Part") → check Album/Series field
  3. If Album/Series matches candidate → HIGH score (folder+series agreement)
  4. Compare ALL available clues (folder, ID3 title, series, author) against candidates
- When ID3 tags are explicitly marked as garbage (⚠ WARNING), IGNORE them completely
- Being "part of the same series" is NOT a match if it's a different volume number
- It is COMPLETELY ACCEPTABLE to score all candidates as 0.0 if none match
- Focus on CORE book title and author, ignore technical metadata (narrator, bitrate)
- When in doubt about narrator/bitrate differences, score HIGH if title+author match
- Only score LOW if the actual book content is different (wrong volume, wrong language, wrong book)

RESPONSE FORMAT:
Return ONLY the scores for each candidate, one per line:
Candidate 1: <score>
Candidate 2: <score>
Candidate 3: <score>
...

Each score must be a number between 0.0 and 1.0.

SCORES:"""

        return prompt

    def _parse_batch_scores(self, response_text: str, expected_count: int) -> List[float]:
        """
        Parse scores from batch LLM response.

        Args:
            response_text: Raw LLM response with multiple scores
            expected_count: Number of candidates scored

        Returns:
            List of scores (0.0-1.0), padded with 0.0 if needed
        """
        scores = []

        # Look for patterns like "Candidate 1: 0.85" or "1: 0.85" or "0.85"
        lines = response_text.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Try different patterns in order of specificity
            # Pattern 1: "Candidate N: 0.85" - extract the score after the colon
            match = re.search(r'[Cc]andidate\s+\d+\s*:\s*([0-9]*\.?[0-9]+)', line)
            if match:
                try:
                    score = float(match.group(1))
                    # Clamp to 0-1 range
                    score = max(0.0, min(1.0, score))
                    scores.append(score)
                    continue
                except ValueError:
                    pass

            # Pattern 2: "N: 0.85" - number followed by colon and score
            match = re.search(r'^\d+\s*:\s*([0-9]*\.?[0-9]+)', line)
            if match:
                try:
                    score = float(match.group(1))
                    score = max(0.0, min(1.0, score))
                    scores.append(score)
                    continue
                except ValueError:
                    pass

            # Pattern 3: Just a number on its own line (0.85)
            match = re.search(r'^([0-9]*\.?[0-9]+)$', line)
            if match:
                try:
                    score = float(match.group(1))
                    score = max(0.0, min(1.0, score))
                    scores.append(score)
                    continue
                except ValueError:
                    pass

        # If we didn't get enough scores, pad with 0.0
        while len(scores) < expected_count:
            scores.append(0.0)
            log.warning(f"Missing score in batch response, padding with 0.0")

        # If we got too many scores, truncate
        if len(scores) > expected_count:
            log.warning(f"Got {len(scores)} scores but expected {expected_count}, truncating")
            scores = scores[:expected_count]

        log.debug(f"Parsed {len(scores)} scores from batch response: {scores}")
        return scores

    def _parse_score(self, score_text: str) -> float:
        """
        Parse score from LLM response.

        Args:
            score_text: Raw LLM response

        Returns:
            Parsed score clamped to 0-1 range
        """
        # Extract first number (handle formats like "0.85" or "Score: 0.85")
        match = re.search(r'([0-9]*\.?[0-9]+)', score_text)
        if match:
            score = float(match.group(1))
            # Clamp to 0-1 range
            return max(0.0, min(1.0, score))

        log.warning(f"Could not parse score from: {score_text}")
        return 0.0


def test_llm_connection() -> bool:
    """
    Test LLM connection with a simple ping prompt.

    Returns:
        True if connection successful, False otherwise
    """
    from ..config import LLM_CONFIG
    from ..utils import safe_encode_text

    print("\n" + "="*80)
    print(safe_encode_text("🔌 Testing LLM Connection"))
    print("="*80)

    # Check if LLM is configured
    if not LLM_CONFIG['enabled']:
        print(safe_encode_text("\n❌ LLM not configured"))
        print("   No LLM_API_KEY found in environment variables.")
        print("\n   Please set up your .env file with:")
        print("   - LLM_API_KEY=your-api-key")
        print("   - LLM_MODEL=your-model (optional, default: gpt-3.5-turbo)")
        print("   - OPENAI_BASE_URL=your-base-url (optional, for local models)")
        return False

    print(f"\nConfiguration:")
    print(f"  Model: {LLM_CONFIG['model']}")
    if LLM_CONFIG['base_url']:
        print(f"  Base URL: {LLM_CONFIG['base_url']}")
    else:
        print(f"  Provider: OpenAI/Anthropic (default)")
    print(f"  API Key: {'*' * 20}{LLM_CONFIG['api_key'][-4:] if len(LLM_CONFIG['api_key']) > 4 else '****'}")

    # Try to import litellm
    try:
        import litellm
        print(safe_encode_text("\n✅ litellm library found"))
    except ImportError:
        print(safe_encode_text("\n❌ litellm library not found"))
        print("   Install with: pip install litellm")
        return False

    # Configure litellm
    if LLM_CONFIG['base_url']:
        litellm.api_base = LLM_CONFIG['base_url']

    # Send test prompt
    print(safe_encode_text("\n🔄 Sending test prompt to LLM..."))

    try:
        response = litellm.completion(
            model=LLM_CONFIG['model'],
            api_key=LLM_CONFIG['api_key'],
            messages=[{
                "role": "user",
                "content": "Respond with only the word 'SUCCESS' if you can read this message."
            }],
            temperature=0.0,
            max_tokens=10
        )

        response_text = response.choices[0].message.content.strip()

        print(safe_encode_text(f"\n✅ Connection successful!"))
        print(f"   Response: {response_text}")

        # Show token usage if available
        if hasattr(response, 'usage') and response.usage:
            print(f"\n   Token usage:")
            print(f"   - Prompt tokens: {response.usage.prompt_tokens}")
            print(f"   - Completion tokens: {response.usage.completion_tokens}")
            print(f"   - Total tokens: {response.usage.total_tokens}")

        print(safe_encode_text("\n✅ LLM connection test passed!"))
        print("="*80)
        return True

    except Exception as e:
        print(safe_encode_text(f"\n❌ Connection failed!"))
        print(f"   Error: {str(e)}")
        print("\n   Troubleshooting:")
        print("   1. Check your API key is correct")
        print("   2. Verify the model name is valid for your provider")
        if LLM_CONFIG['base_url']:
            print("      For local models (LM Studio/Ollama), use model name like:")
            print("      - openai/gpt-oss-20b (for LM Studio OpenAI-compatible)")
            print("      - ollama/llama2 (for Ollama)")
        print("   3. If using local models, ensure the server is running")
        print("   4. Check your internet connection (for cloud providers)")
        print("="*80)
        return False
