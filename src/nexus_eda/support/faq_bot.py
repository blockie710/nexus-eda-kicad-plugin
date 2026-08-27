# SPDX-License-Identifier: Apache-2.0
"""FAQ bot for Nexus-EDA support automation.

Implements a lightweight RAG-style FAQ bot:

1. **TF-IDF retrieval** (always available, offline):
   Tokenises the user question and each FAQ entry's question + keywords,
   computes cosine similarity, and returns the top-N matches.

2. **LLM answer generation** (optional):
   When the LLM engine is available, the bot constructs a prompt from the
   retrieved FAQ entries (as RAG context) and asks the LLM to generate a
   helpful, grounded response.  If the LLM is not loaded or fails, the bot
   falls back to returning the best-matching FAQ answer verbatim and
   reports ``method="tfidf"``.

Confidence is reported as the cosine similarity score, adjusted by the
FAQ entry's ``confidence_boost`` multiplier.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from ..llm.engine import LLMEngine, LLMError
from .config import _text_for_matching
from .models import FAQEntry, SupportConfig

__all__ = ["FAQBot", "FAQMatch", "FAQAnswer"]


FAQ_ANSWER_PROMPT = """\
You are a helpful Nexus-EDA support assistant.  Answer the customer's question
using ONLY the FAQ context below.  If the context does not contain the answer,
say so briefly and suggest contacting support.  Do not hallucinate facts.

FAQ CONTEXT:
{context}

CUSTOMER QUESTION: {question}

ANSWER:"""


@dataclass
class FAQMatch:
    """A single FAQ match with its score and metadata.

    Attributes:
        entry: The matched :class:`FAQEntry`.
        score: Cosine-similarity score in [0, 1].
        confidence: Adjusted confidence (score x confidence_boost).
        method: ``"tfidf"`` or ``"llm"``.
    """

    entry: FAQEntry
    score: float
    confidence: float
    method: str = "tfidf"
    answer: Optional[str] = None


@dataclass
class FAQAnswer:
    """The result of an FAQ lookup.

    Attributes:
        question: The original user question.
        answer: The best answer found (or a fallback message).
        confidence: Confidence in the answer [0, 1].
        matched_entry: The FAQEntry that was matched, if any.
        matches: Top-N matches (sorted by confidence).
        method: ``"tfidf"`` or ``"llm"``.
    """

    question: str
    answer: str
    confidence: float
    matched_entry: Optional[FAQEntry] = None
    matches: list[FAQMatch] = field(default_factory=list)
    method: str = "tfidf"


class FAQBot:
    """RAG-style FAQ bot with TF-IDF retrieval and optional LLM generation.

    Usage::

        bot = FAQBot(config)
        result = bot.answer("How do I install the plugin?")
        print(result.answer, result.confidence)
    """

    def __init__(
        self,
        config: SupportConfig,
        engine: Optional[LLMEngine] = None,
        top_k: int = 3,
    ) -> None:
        self.config = config
        self._engine = engine
        self.top_k = top_k
        self._tfidf = _TFIDFIndex(config.faq_entries)

    @property
    def engine(self) -> Optional[LLMEngine]:
        """The LLM engine, loaded lazily on first use."""
        if self._engine is not None and not self._engine.is_loaded:
            try:
                self._engine.load()
            except LLMError:
                self._engine = None
        return self._engine

    # -- retrieval ----------------------------------------------------------- #

    def search(
        self,
        question: str,
        top_k: Optional[int] = None,
    ) -> list[FAQMatch]:
        """Search the FAQ index for entries similar to *question*.

        Returns a list of :class:`FAQMatch` sorted by confidence (descending).
        """
        k = top_k or self.top_k
        return self._tfidf.search(question, k)

    def answer(
        self,
        question: str,
        *,
        use_llm: bool = True,
    ) -> FAQAnswer:
        """Answer a customer question.

        Parameters
        ----------
        question:
            The customer's question text.
        use_llm:
            If *True* and the LLM engine is available, generate a response
            grounded in the retrieved FAQ context.  Otherwise, return the
            best-matching FAQ answer verbatim.  If the LLM fails at call
            time, the bot transparently falls back to the TF-IDF answer and
            reports ``method="tfidf"``.

        Returns
        -------
        FAQAnswer
        """
        matches = self.search(question, self.top_k)

        if not matches:
            return FAQAnswer(
                question=question,
                answer=(
                    "I don't have a matching FAQ entry for that question. "
                    "Please contact support@nexus-eda.com for assistance."
                ),
                confidence=0.0,
                method="tfidf",
            )

        best = matches[0]

        if use_llm:
            eng = self.engine
            if eng is not None:
                try:
                    answer_text = self._generate_llm_answer(
                        question, matches, eng
                    )
                except LLMError:
                    # LLM failed — fall back to best match answer
                    return FAQAnswer(
                        question=question,
                        answer=best.entry.answer,
                        confidence=best.confidence,
                        matched_entry=best.entry,
                        matches=matches,
                        method="tfidf",
                    )
                # LLM answers inherit the best match's confidence
                return FAQAnswer(
                    question=question,
                    answer=answer_text,
                    confidence=best.confidence,
                    matched_entry=best.entry,
                    matches=matches,
                    method="llm",
                )

        # Offline / fallback: return the best matching FAQ answer
        return FAQAnswer(
            question=question,
            answer=best.entry.answer,
            confidence=best.confidence,
            matched_entry=best.entry,
            matches=matches,
            method="tfidf",
        )

    # -- LLM generation ----------------------------------------------------- #

    def _generate_llm_answer(
        self,
        question: str,
        matches: list[FAQMatch],
        engine: LLMEngine,
    ) -> str:
        """Generate an LLM answer grounded in the retrieved FAQ matches.

        Raises :class:`LLMError` if generation fails, so callers can fall
        back to the TF-IDF answer.
        """
        context_parts = []
        for i, m in enumerate(matches):
            context_parts.append(
                f"[[FAQ {i + 1} (score={m.score:.2f})]] "
                f"Q: {m.entry.question}\n"
                f"A: {m.entry.answer}"
            )
        context = "\n\n".join(context_parts)

        prompt = FAQ_ANSWER_PROMPT.format(
            context=context,
            question=question,
        )

        return engine.generate(
            prompt,
            max_tokens=self.config.llm_max_tokens,
            temperature=self.config.llm_temperature,
        ).strip()

class _TFIDFIndex:
    """In-memory TF-IDF / cosine-similarity index over FAQ entries.

    Uses a simple token-overlap cosine similarity.  For very large FAQ
    sets, a sparse matrix (scipy / numpy) would be faster, but for the
    expected ~50-200 entries, pure-Python is sufficient and dependency-free.
    """

    def __init__(self, entries: list[FAQEntry]) -> None:
        self.entries = entries
        # Pre-compute token vectors
        self._vocab: dict[str, int] = {}
        self._doc_vectors: list[Counter] = []
        self._doc_norms: list[float] = []

        for entry in entries:
            text = _text_for_matching(
                f"{entry.question} {entry.answer} "
                f"{' '.join(entry.keywords)}"
            )
            tokens = _tokenize(text)
            vec = Counter(tokens)
            for token in vec:
                if token not in self._vocab:
                    self._vocab[token] = len(self._vocab)
            self._doc_vectors.append(vec)
            norm = math.sqrt(sum(w * w for w in vec.values()))
            self._doc_norms.append(norm if norm > 0 else 1e-10)

    def search(self, question: str, top_k: int) -> list[FAQMatch]:
        """Search for the top-k FAQ entries by cosine similarity."""
        if not self.entries:
            return []

        query_text = _text_for_matching(question)
        query_tokens = _tokenize(query_text)
        query_vec = Counter(query_tokens)
        query_norm = math.sqrt(sum(w * w for w in query_vec.values()))
        if query_norm == 0:
            return []

        scores: list[tuple[float, int]] = []
        for i, doc_vec in enumerate(self._doc_vectors):
            # Dot product over shared tokens
            dot = 0.0
            for token, q_count in query_vec.items():
                d_count = doc_vec.get(token, 0)
                if d_count:
                    dot += q_count * d_count
            norm_product = query_norm * self._doc_norms[i]
            sim = dot / norm_product if norm_product > 0 else 0.0
            scores.append((sim, i))

        # Sort by similarity descending, take top-k
        scores.sort(key=lambda x: x[0], reverse=True)
        top = scores[:top_k]

        results: list[FAQMatch] = []
        for sim, idx in top:
            if sim <= 0.0:
                continue
            entry = self.entries[idx]
            confidence = sim * entry.confidence_boost
            confidence = min(confidence, 1.0)
            results.append(FAQMatch(
                entry=entry,
                score=sim,
                confidence=confidence,
                method="tfidf",
            ))

        return results


def _tokenize(text: str) -> list[str]:
    """Tokenise text into lowercase alphanumeric tokens."""
    return [t for t in re.findall(r"[a-z0-9]+", text.lower())]