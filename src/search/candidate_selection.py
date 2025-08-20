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
    
    def select_best_candidate(self, candidates: List[SearchCandidate], 
                            search_term: str) -> Optional[SearchCandidate]:
        """
        Select the best candidate from a list.
        
        Args:
            candidates: List of search candidates
            search_term: Original search term
            
        Returns:
            Best candidate or None if none suitable
        """
        if not candidates:
            return None
        
        if len(candidates) == 1:
            return candidates[0]
        
        # Try AI selection if enabled
        if self.enable_ai_selection:
            ai_choice = self._ai_select_candidate(candidates, search_term)
            if ai_choice is not None:
                return ai_choice
        
        # Fallback to heuristic selection
        return self._heuristic_select_candidate(candidates, search_term)
    
    def _ai_select_candidate(self, candidates: List[SearchCandidate], 
                           search_term: str) -> Optional[SearchCandidate]:
        """
        Use AI to select the best candidate.
        
        This is a placeholder for future AI-powered selection.
        Could use language models to analyze titles, snippets, and content
        to determine the best match for the search term.
        
        Args:
            candidates: List of candidates to choose from
            search_term: Original search term
            
        Returns:
            Selected candidate or None
        """
        # TODO: Implement AI-powered candidate selection
        # This could involve:
        # - Analyzing title similarity to search term
        # - Checking snippet content relevance
        # - Parsing HTML content for additional metadata
        # - Using fuzzy matching or semantic similarity
        
        log.info("AI candidate selection not yet implemented, falling back to heuristics")
        return None
    
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
