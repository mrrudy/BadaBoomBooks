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
        Score all candidates using LLM.

        Args:
            candidates: List of search candidates
            search_term: Original search term
            book_info: Optional book context (from existing metadata)

        Returns:
            List of (candidate, score) tuples where score is 0-1
        """
        if not self.llm_available:
            return [(c, 0.0) for c in candidates]

        scored = []
        for candidate in candidates:
            score = self._score_single_candidate(candidate, search_term, book_info)
            scored.append((candidate, score))

        return scored

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
                max_tokens=50  # Just need a number
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
        context = f"Search term: {search_term}\n"

        if book_info:
            context += "Book information:\n"
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
