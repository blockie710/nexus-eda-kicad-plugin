# SPDX-License-Identifier: Apache-2.0
"""Data models for Nexus-EDA customer support automation.

All models use ``dataclasses`` for concise, type-checked structures and are
serialisable to/from dicts so they can be persisted or transmitted over the
Stripe webhook → local agent bridge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class TicketStatus(str, Enum):
    """Lifecycle state of a support ticket."""

    OPEN = "open"
    ROUTED = "routed"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


@dataclass
class TicketCategory:
    """A support category that tickets can be routed to.

    Attributes:
        name: Unique category identifier (e.g. ``"billing"``).
        label: Human-readable name shown in the UI.
        description: What this category covers.
        keywords: Lowercased keywords used for classification.
        agent_profile: Which agent profile handles this category.
        priority: Integer priority (higher = more urgent routing).
        sla_hours: Target SLA for first response in hours.
    """

    name: str
    label: str
    description: str
    keywords: list[str] = field(default_factory=list)
    agent_profile: str = "nexus-fast"
    priority: int = 3
    sla_hours: float = 24.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TicketCategory":
        return cls(
            name=data["name"],
            label=data.get("label", data["name"].title()),
            description=data.get("description", ""),
            keywords=list(data.get("keywords", [])),
            agent_profile=data.get("agent_profile", "nexus-fast"),
            priority=int(data.get("priority", 3)),
            sla_hours=float(data.get("sla_hours", 24.0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "keywords": self.keywords,
            "agent_profile": self.agent_profile,
            "priority": self.priority,
            "sla_hours": self.sla_hours,
        }


@dataclass
class FAQEntry:
    """A single FAQ question/answer pair with optional search keywords.

    Attributes:
        question: The FAQ question.
        answer: The answer text.
        keywords: Extra search terms beyond those in the question/answer.
        category: Optional category tag for filtering.
        confidence_boost: Multiplier applied when this entry matches
            (1.0 = neutral, >1.0 boosts, <1.0 dampens).
    """

    question: str
    answer: str
    keywords: list[str] = field(default_factory=list)
    category: str = "general"
    confidence_boost: float = 1.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FAQEntry":
        return cls(
            question=data["question"],
            answer=data["answer"],
            keywords=list(data.get("keywords", [])),
            category=data.get("category", "general"),
            confidence_boost=float(data.get("confidence_boost", 1.0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "keywords": self.keywords,
            "category": self.category,
            "confidence_boost": self.confidence_boost,
        }


@dataclass
class Ticket:
    """A customer support ticket received via Stripe webhook or email.

    Attributes:
        id: Unique ticket identifier (UUID or Stripe event id).
        subject: Ticket subject / title.
        body: Full ticket body text.
        customer_email: Customer's email address.
        customer_id: Optional Stripe customer id.
        created_at: When the ticket was received.
        source: Channel the ticket came from (``"stripe"``, ``"email"``,
            ``"chat"``, ``"api"``).
        status: Current lifecycle state.
    """

    id: str
    subject: str
    body: str
    customer_email: str
    customer_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    source: str = "api"
    status: TicketStatus = TicketStatus.OPEN

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "subject": self.subject,
            "body": self.body,
            "customer_email": self.customer_email,
            "customer_id": self.customer_id,
            "created_at": self.created_at.isoformat(),
            "source": self.source,
            "status": self.status.value,
        }


@dataclass
class RoutingDecision:
    """The result of routing a ticket through the classifier.

    Attributes:
        category: The matched :class:`TicketCategory`.
        confidence: Classification confidence 0.0–1.0.
        matched_keywords: Keywords from the best-matching category.
        method: ``"keyword"`` for TF-IDF/keyword match, ``"llm"`` for LLM.
        suggestion: Optional agent-generated reply suggestion.
    """

    category: TicketCategory
    confidence: float
    matched_keywords: list[str] = field(default_factory=list)
    method: str = "keyword"
    suggestion: Optional[str] = None

    @property
    def is_confident(self) -> bool:
        """True when confidence is above the 0.5 threshold."""
        return self.confidence >= 0.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.name,
            "confidence": round(self.confidence, 4),
            "matched_keywords": self.matched_keywords,
            "method": self.method,
            "suggestion": self.suggestion,
            "is_confident": self.is_confident,
        }


@dataclass
class SupportConfig:
    """Configuration for the support automation subsystem.

    Wraps the raw YAML dict and exposes typed accessors so callers don't
    need to deal with nested ``dict.get`` chains.
    """

    categories: list[TicketCategory] = field(default_factory=list)
    faq_entries: list[FAQEntry] = field(default_factory=list)
    router_fallback_model: str = "Qwen2.5-Coder-7B-Q4_K_M"
    faq_fallback_model: str = "Qwen2.5-Coder-7B-Q4_K_M"
    confidence_threshold: float = 0.5
    llm_max_tokens: int = 512
    llm_temperature: float = 0.1
    auto_reply: bool = False
    auto_reply_categories: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def get_category(self, name: str) -> Optional[TicketCategory]:
        """Look up a category by name."""
        for cat in self.categories:
            if cat.name == name:
                return cat
        return None

    def get_faq_by_category(self, category: str) -> list[FAQEntry]:
        """Return FAQ entries matching *category* (or all if ``"all"``)."""
        return [e for e in self.faq_entries if e.category == category]

    @property
    def has_llm_models(self) -> bool:
        """Whether the local LLM engine is available for fallback routing."""
        # The engine is checked separately; this is a static hint.
        return bool(self.router_fallback_model)
