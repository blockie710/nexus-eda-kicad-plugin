# SPDX-License-Identifier: Apache-2.0
"""Customer support automation for Nexus-EDA SaaS.

Provides ticket routing (keyword + LLM classification) and an FAQ bot
(RAG-style retrieval with local LLM fallback) for Phase 5.  All components
are pure-Python and degrade gracefully when ``llama-cpp-python`` or a model
file is unavailable — a keyword / TF-IDF fallback then handles classification
and retrieval so the support automation keeps working offline.

Submodules:
    - :mod:`nexus_eda.support.models`       — data models
    - :mod:`nexus_eda.support.config`       — YAML config loading
    - :mod:`nexus_eda.support.router`       — ticket classification & routing
    - :mod:`nexus_eda.support.faq_bot`      — FAQ retrieval & answering
"""

from .models import (
    Ticket,
    TicketCategory,
    RoutingDecision,
    FAQEntry,
    SupportConfig,
    TicketStatus,
)
from .router import TicketRouter
from .faq_bot import FAQBot

__all__ = [
    "Ticket",
    "TicketCategory",
    "TicketStatus",
    "RoutingDecision",
    "FAQEntry",
    "SupportConfig",
    "TicketRouter",
    "FAQBot",
]
