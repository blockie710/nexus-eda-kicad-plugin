# SPDX-License-Identifier: Apache-2.0
"""Ticket router for Nexus-EDA customer support automation.

Classifies incoming :class:`~nexus_eda.support.models.Ticket` objects into
categories using a two-tier strategy:

1. **Cosine-similarity keyword scoring** (default, offline-capable):
   Tokenises the ticket text, computes a cosine-similarity score between the
   ticket's token-frequency vector and each category's keyword token set,
   and picks the best match.  This needs no model and always works.

2. **LLM fallback** (optional):
   When keyword confidence is below ``confidence_threshold`` **and** the
   local LLM engine is available, the router delegates to the LLM engine
   with a structured prompt that returns JSON.

The :class:`TicketRouter` exposes :meth:`route` which returns a
:class:`~nexus_eda.support.models.RoutingDecision`.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Optional

from ..llm.engine import LLMEngine, LLMError
from .config import _text_for_matching
from .models import (
    RoutingDecision,
    SupportConfig,
    Ticket,
    TicketCategory,
)

__all__ = ["TicketRouter", "TicketClassifier"]


# --------------------------------------------------------------------------- #
# Prompts
# --------------------------------------------------------------------------- #
ROUTING_PROMPT = """\
You are a Nexus-EDA support ticket classifier. Classify the following ticket
into exactly one of these categories:

{categories}

Respond with a JSON object only — no prose, no markdown fences:
{{
  "category": "<one of the category names above>",
  "confidence": <0.0-1.0>,
  "reason": "<one-sentence explanation>"
}}

TICKET SUBJECT: {subject}
TICKET BODY: {body}

JSON:"""


class TicketClassifier:
    """Pure keyword / cosine-similarity classifier — no external dependencies.

    This is the deterministic, offline-first classification path.  The LLM
    engine is only consulted when keyword confidence falls below the
    threshold configured on :class:`TicketRouter`.
    """

    def __init__(self, config: SupportConfig) -> None:
        self.categories = config.categories
        self.confidence_threshold = config.confidence_threshold

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Tokenise text into lowercase alphanumeric tokens."""
        return [t for t in re.findall(r"[a-z0-9]+", text.lower())]

    def _keyword_score(
        self, tokens: list[str], category: TicketCategory
    ) -> tuple[float, list[str]]:
        """Compute a normalised keyword-match score for *category*.

        Returns
        -------
        (score, matched_keywords)
            ``score`` is in [0, 1]; higher means more keyword overlap.
        """
        if not self.categories or not category.keywords:
            return 0.0, []

        # Build keyword token sets (multi-word keywords are tokenised too)
        keyword_tokens: set[str] = set()
        matched: list[str] = []

        for kw in category.keywords:
            kw_tokens = set(self._tokenize(kw))
            keyword_tokens.update(kw_tokens)

        token_set = set(tokens)
        matched_tokens = token_set & keyword_tokens
        matched = [kw for kw in category.keywords if kw in " ".join(tokens) or set(self._tokenize(kw)) & token_set]

        if not keyword_tokens:
            return 0.0, []

        # Normalised overlap: fraction of keywords that matched
        score = len(matched_tokens) / len(keyword_tokens)
        return score, matched

    def _tfidf_score(
        self, tokens: list[str], category: TicketCategory, all_keywords: list[str]
    ) -> tuple[float, list[str]]:
        """Enhanced scoring: TF-IDF-like with cosine-similarity normalisation.

        Computes a cosine-similarity score between the ticket's token-frequency
        vector and the category's keyword token set.  This gives a [0, 1] score
        where ~0.3 is a reasonable low-confidence match and ~0.7+ is strong.
        """
        if not category.keywords:
            return 0.0, []

        # Build the set of keyword tokens for this category
        keyword_tokens: list[str] = []
        keyword_to_kw: dict[str, str] = {}
        for kw in category.keywords:
            for tk in self._tokenize(kw):
                keyword_tokens.append(tk)
                if tk not in keyword_to_kw:
                    keyword_to_kw[tk] = kw

        if not keyword_tokens:
            return 0.0, []

        # Token frequency in the ticket
        token_freq = Counter(tokens)

        # Cosine similarity: dot product of ticket-tf and keyword-binary vectors
        # divided by norms.  Keyword vector uses 1 for presence (binary IDF-free).
        dot_product = 0.0
        matched_kws: set[str] = set()
        for tk in keyword_tokens:
            freq = token_freq.get(tk, 0)
            if freq > 0:
                matched_kws.add(keyword_to_kw[tk])
                dot_product += freq

        # Norm of keyword vector (sqrt of total keyword tokens counted with multiplicity)
        kw_norm = len(keyword_tokens) ** 0.5
        # Norm of ticket vector over matched tokens only (sqrt of sum of freq^2)
        matched_freq_sq = sum(token_freq[t] ** 2 for t in set(keyword_tokens) if token_freq.get(t, 0) > 0)
        ticket_norm = matched_freq_sq ** 0.5 if matched_freq_sq > 0 else 1e-10

        norm_product = kw_norm * ticket_norm
        score = dot_product / norm_product if norm_product > 0 else 0.0
        score = min(score, 1.0)

        return score, sorted(matched_kws)

    def classify(
        self, ticket: Ticket
    ) -> tuple[Optional[TicketCategory], float, list[str], str]:
        """Classify a ticket using keyword scoring.

        Returns
        -------
        (category, confidence, matched_keywords, method)
        """
        combined_text = _text_for_matching(f"{ticket.subject} {ticket.body}")
        tokens = self._tokenize(combined_text)

        if not self.categories:
            return None, 0.0, [], "none"

        all_keywords: list[str] = []
        for cat in self.categories:
            all_keywords.extend(cat.keywords)

        best_cat: Optional[TicketCategory] = None
        best_score = 0.0
        best_matched: list[str] = []

        for cat in self.categories:
            score, matched = self._tfidf_score(tokens, cat, all_keywords)
            if score > best_score:
                best_score = score
                best_cat = cat
                best_matched = matched

        return best_cat, min(best_score, 1.0), best_matched, "keyword"

    def classify_with_llm(
        self,
        ticket: Ticket,
        engine: LLMEngine,
    ) -> tuple[Optional[TicketCategory], float, list[str], str]:
        """Classify using the LLM engine as the sole decision maker.

        Used when ``use_llm_only=True`` or for testing the LLM path directly.
        """
        category_lines = "\n".join(
            f"- {c.name} ({c.label}): {c.description}"
            for c in self.categories
        )
        prompt = ROUTING_PROMPT.format(
            categories=category_lines,
            subject=ticket.subject,
            body=ticket.body[:2000],
        )

        try:
            raw = engine.generate(prompt, max_tokens=512)
            data = json.loads(raw.strip().strip("```json").strip("```"))
        except (LLMError, json.JSONDecodeError, KeyError):
            return None, 0.0, [], "llm"

        cat_name = data.get("category", "")
        confidence = float(data.get("confidence", 0.0))
        reason = data.get("reason", "")

        cat = next(
            (c for c in self.categories if c.name == cat_name), None
        )
        matched = _text_for_matching(reason).split() if reason else []
        return cat, min(confidence, 1.0), matched, "llm"


class TicketRouter:
    """High-level ticket router that combines keyword + LLM classification.

    Usage::

        router = TicketRouter(config)
        decision = router.route(ticket)
        print(decision.category.name, decision.confidence)
    """

    def __init__(
        self,
        config: SupportConfig,
        engine: Optional[LLMEngine] = None,
    ) -> None:
        self.config = config
        self.classifier = TicketClassifier(config)
        self._engine = engine
        self._llm_available = engine is not None and (
            engine.is_loaded
            # Defer: the engine may not be loaded yet, we'll try at call time
        )

    @property
    def engine(self) -> Optional[LLMEngine]:
        """The LLM engine, loaded lazily on first use."""
        if self._engine is not None and not self._engine.is_loaded:
            try:
                self._engine.load()
            except LLMError:
                self._engine = None
        return self._engine

    def route(
        self,
        ticket: Ticket,
        *,
        use_llm_fallback: bool = True,
        llm_only: bool = False,
    ) -> RoutingDecision:
        """Route *ticket* to the best-matching category.

        Parameters
        ----------
        ticket:
            The support ticket to classify.
        use_llm_fallback:
            If *True* (default) and keyword confidence is below
            ``confidence_threshold``, the router attempts LLM classification.
        llm_only:
            If *True*, always use the LLM engine (useful for testing).

        Returns
        -------
        RoutingDecision
        """
        # 1. Keyword / cosine-similarity classification
        cat, confidence, matched, method = self.classifier.classify(ticket)

        # 2. Optionally escalate to LLM
        if llm_only:
            eng = self.engine
            if eng is not None:
                cat, confidence, matched, method = (
                    self.classifier.classify_with_llm(ticket, eng)
                )
            else:
                # No LLM available — fall back to keyword score
                if cat is None:
                    cat = self._default_category()
                    confidence = 0.1
                    method = "keyword-fallback"
        elif (
            use_llm_fallback
            and confidence < self.config.confidence_threshold
        ):
            eng = self.engine
            if eng is not None:
                llm_cat, llm_conf, llm_matched, llm_method = (
                    self.classifier.classify_with_llm(ticket, eng)
                )
                # Use LLM result if it has a category and meets threshold,
                # or if it has higher confidence than keyword
                if llm_cat is not None and (
                    llm_conf >= self.config.confidence_threshold
                    or llm_conf > confidence
                ):
                    cat, confidence, matched, method = (
                        llm_cat, llm_conf, llm_matched, llm_method
                    )

        # 3. Final fallback to default category if nothing matched
        if cat is None:
            cat = self._default_category()
            confidence = 0.1
            method = "keyword-fallback"

        # 4. Generate a suggestion if confidence is high enough
        suggestion: Optional[str] = None
        if confidence >= self.config.confidence_threshold:
            suggestion = self._generate_suggestion(ticket, cat, confidence)

        return RoutingDecision(
            category=cat,
            confidence=confidence,
            matched_keywords=matched,
            method=method,
            suggestion=suggestion,
        )

    def _default_category(self) -> TicketCategory:
        """Return the lowest-priority category as the fallback."""
        if not self.config.categories:
            return TicketCategory(
                name="general",
                label="General Support",
                description="General support inquiries.",
                keywords=[],
            )
        # Pick the "feature" category if it exists, else the lowest priority
        for cat in self.config.categories:
            if cat.name == "feature":
                return cat
        return min(self.config.categories, key=lambda c: c.priority)

    def _generate_suggestion(
        self,
        ticket: Ticket,
        category: TicketCategory,
        confidence: float,
    ) -> Optional[str]:
        """Generate a brief reply suggestion for auto-reply-capable categories."""
        auto_reply_enabled = (
            self.config.auto_reply
            or category.name in self.config.auto_reply_categories
        )
        if not auto_reply_enabled:
            return None

        return (
            f"Ticket routed to {category.label} (confidence: "
            f"{confidence:.1%}). "
            f"Agent profile '{category.agent_profile}' will review "
            f"and respond within {category.sla_hours}h SLA."
        )
