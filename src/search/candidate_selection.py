"""
Candidate selection logic.

This module handles selection logic for choosing the best
candidate from multiple search results.
"""

import logging as log
from typing import List, Optional

from ..models import SearchCandidate


class CandidateSelector:
    """Handles candidate selection logic."""

    def __init__(self, enable_ai_selection: bool = False):
        self.enable_ai_selection = enable_ai_selection
        self.llm_scorer = None
        self.last_scored_candidates = []  # Store last scoring results for display
        self.llm_rejected_all = False  # Track if LLM actively rejected all candidates

        if enable_ai_selection:
            from .llm_scoring import LLMScorer
            self.llm_scorer = LLMScorer()

    def select_best_candidate(self, candidates: List[SearchCandidate],
                            search_term: str,
                            book_info: dict = None) -> Optional[SearchCandidate]:
        """
        Select the best candidate from a list.

        Args:
            candidates: List of search candidates
            search_term: Original search term
            book_info: Optional book context information

        Returns:
            Best candidate or None if none suitable
        """
        if not candidates:
            return None

        if len(candidates) == 1:
            return candidates[0]

        # Reset rejection flag
        self.llm_rejected_all = False

        # Try AI selection if enabled
        if self.enable_ai_selection:
            # Check if LLM is actually available
            if not self.llm_scorer or not self.llm_scorer.llm_available:
                log.info("LLM not available, falling back to heuristics")
                # LLM unavailable - fall back to heuristics
                return self._heuristic_select_candidate(candidates, search_term)

            ai_choice = self._ai_select_candidate(candidates, search_term, book_info)
            if ai_choice is not None:
                return ai_choice

            # If LLM actively rejected all candidates (flag set by _ai_select_candidate),
            # respect that decision and return None - do NOT fall back to heuristics
            if self.llm_rejected_all:
                log.info("LLM rejected all candidates, respecting LLM's decision (no fallback)")
                return None

        # Fallback to heuristic selection (only when LLM not enabled or unavailable)
        return self._heuristic_select_candidate(candidates, search_term)
    
    def _ai_select_candidate(self, candidates: List[SearchCandidate],
                           search_term: str,
                           book_info: dict = None) -> Optional[SearchCandidate]:
        """
        Use AI to select the best candidate.

        Args:
            candidates: List of candidates to choose from
            search_term: Original search term
            book_info: Optional book context information

        Returns:
            Selected candidate or None if no good match
        """
        if not self.llm_scorer or not self.llm_scorer.llm_available:
            # LLM is unavailable - caller should handle fallback
            return None

        # Score all candidates using LLM
        scored_candidates = self.llm_scorer.score_candidates(
            candidates, search_term, book_info
        )

        # Apply weights as tiebreaker for similar scores
        scored_with_weights = self._apply_scraper_weights(scored_candidates)

        # Sort by weighted score (highest first)
        scored_with_weights.sort(key=lambda x: x[2], reverse=True)

        # Store scores for later display
        self.last_scored_candidates = scored_with_weights

        # Get best candidate
        best_candidate, llm_score, final_score = scored_with_weights[0]

        # Define acceptance threshold (0.5 = 50% confidence minimum)
        ACCEPTANCE_THRESHOLD = 0.5

        if llm_score < ACCEPTANCE_THRESHOLD:
            log.info(f"Best LLM score ({llm_score:.2f}) below threshold ({ACCEPTANCE_THRESHOLD}), rejecting all")
            # Set flag to indicate LLM actively rejected all candidates
            self.llm_rejected_all = True
            return None

        log.info(f"LLM selected '{best_candidate.title}' with score {llm_score:.2f} (weighted: {final_score:.2f})")
        return best_candidate

    def _apply_scraper_weights(self, scored_candidates: List[tuple]) -> List[tuple]:
        """
        Apply scraper weights as tiebreaker for similar LLM scores.

        When LLM scores are within a quality bracket (0.1 difference), use scraper
        weights to favor preferred sources (e.g., lubimyczytac over others).

        Args:
            scored_candidates: List of (candidate, llm_score) tuples

        Returns:
            List of (candidate, llm_score, final_score) tuples
        """
        from ..config import SCRAPER_REGISTRY

        # Quality bracket threshold - scores within this range are considered "similar"
        SIMILARITY_THRESHOLD = 0.1
        # Minimum score threshold - don't apply weights if all scores are too low
        ACCEPTANCE_THRESHOLD = 0.5

        if not scored_candidates:
            return []

        # Get the best LLM score
        best_llm_score = max(score for _, score in scored_candidates)

        # Don't apply weights if best score is below acceptance threshold
        # This prevents selecting a candidate when all scores are 0.0 or very low
        should_apply_weights = best_llm_score >= ACCEPTANCE_THRESHOLD

        weighted_results = []
        for candidate, llm_score in scored_candidates:
            # Get weight for this scraper (default to 1.0 if not specified)
            weight = SCRAPER_REGISTRY.get(candidate.site_key, {}).get('weight', 1.0)

            # If score is within similarity threshold of best AND above acceptance threshold, apply weight
            if should_apply_weights and (best_llm_score - llm_score <= SIMILARITY_THRESHOLD):
                # Apply weight as multiplier (small boost to preserve LLM score primacy)
                final_score = llm_score * (1.0 + (weight - 1.0) * 0.1)
                log.debug(f"Applied weight {weight} to '{candidate.site_key}': "
                         f"LLM={llm_score:.3f} -> Final={final_score:.3f}")
            else:
                # Outside quality bracket or scores too low, weight doesn't apply
                final_score = llm_score

            weighted_results.append((candidate, llm_score, final_score))

        return weighted_results

    def _heuristic_select_candidate(self, candidates: List[SearchCandidate], 
                                  search_term: str) -> Optional[SearchCandidate]:
        """
        Use heuristics to select the best candidate.
        
        Args:
            candidates: List of candidates to choose from
            search_term: Original search term
            
        Returns:
            Selected candidate based on heuristics
        """
        # Score candidates based on various factors
        scored_candidates = []
        
        for candidate in candidates:
            score = self._calculate_candidate_score(candidate, search_term)
            scored_candidates.append((candidate, score))
        
        # Sort by score (highest first)
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        
        best_candidate, best_score = scored_candidates[0]
        
        log.debug(f"Selected candidate '{best_candidate.title}' with score {best_score}")
        return best_candidate
    
    def _calculate_candidate_score(self, candidate: SearchCandidate, search_term: str) -> float:
        """
        Calculate a relevance score for a candidate.
        
        Args:
            candidate: Candidate to score
            search_term: Original search term
            
        Returns:
            Relevance score (higher is better)
        """
        score = 0.0
        search_lower = search_term.lower()
        title_lower = candidate.title.lower()
        snippet_lower = candidate.snippet.lower()
        
        # Title similarity
        if search_lower in title_lower:
            score += 10.0
        
        # Count matching words in title
        search_words = set(search_lower.split())
        title_words = set(title_lower.split())
        matching_words = len(search_words.intersection(title_words))
        score += matching_words * 2.0
        
        # Snippet relevance
        if search_lower in snippet_lower:
            score += 5.0
        
        # Prefer certain sites (could be configurable)
        site_preferences = {
            'audible': 3.0,
            'goodreads': 2.0,
            'lubimyczytac': 1.0
        }
        score += site_preferences.get(candidate.site_key, 0.0)
        
        # Penalty for very short titles (likely not specific enough)
        if len(candidate.title) < 10:
            score -= 2.0
        
        # Bonus for longer, more descriptive snippets
        if len(candidate.snippet) > 100:
            score += 1.0
        
        return score
    
    def rank_candidates(self, candidates: List[SearchCandidate], 
                       search_term: str) -> List[SearchCandidate]:
        """
        Rank all candidates by relevance.
        
        Args:
            candidates: List of candidates to rank
            search_term: Original search term
            
        Returns:
            List of candidates sorted by relevance (best first)
        """
        scored_candidates = []
        
        for candidate in candidates:
            score = self._calculate_candidate_score(candidate, search_term)
            scored_candidates.append((candidate, score))
        
        # Sort by score (highest first)
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        
        return [candidate for candidate, score in scored_candidates]
    
    def explain_selection(self, candidate: SearchCandidate, search_term: str) -> str:
        """
        Provide explanation for why a candidate was selected.
        
        Args:
            candidate: Selected candidate
            search_term: Original search term
            
        Returns:
            Human-readable explanation
        """
        score = self._calculate_candidate_score(candidate, search_term)
        
        explanations = []
        search_lower = search_term.lower()
        title_lower = candidate.title.lower()
        
        if search_lower in title_lower:
            explanations.append("search term found in title")
        
        search_words = set(search_lower.split())
        title_words = set(title_lower.split())
        matching_words = len(search_words.intersection(title_words))
        
        if matching_words > 0:
            explanations.append(f"{matching_words} matching words in title")
        
        if candidate.site_key == 'audible':
            explanations.append("from preferred site (Audible)")
        elif candidate.site_key == 'goodreads':
            explanations.append("from trusted site (Goodreads)")
        
        explanation = f"Selected with score {score:.1f}: " + ", ".join(explanations)
        return explanation
