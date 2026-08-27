# SPDX-License-Identifier: Apache-2.0
"""Comprehensive unit tests for Nexus-EDA support automation.

Covers:
    - Data model serialisation (Ticket, TicketCategory, FAQEntry, RoutingDecision)
    - Config loading (built-in defaults + custom YAML)
    - TicketRouter keyword classification and LLM fallback paths
    - FAQBot TF-IDF retrieval and answer generation
    - Edge cases: empty input, no match, low confidence, LLM unavailable
"""

import json
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

# Ensure src is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from nexus_eda.support import (
    FAQBot,
    FAQEntry,
    RoutingDecision,
    SupportConfig,
    Ticket,
    TicketCategory,
    TicketRouter,
    TicketStatus,
)
from nexus_eda.support.config import (
    DEFAULT_CATEGORIES,
    DEFAULT_FAQ_ENTRIES,
    load_config,
)
from nexus_eda.support.models import TicketCategory as TC


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def simple_config() -> SupportConfig:
    return SupportConfig(
        categories=[
            TicketCategory(
                name="billing",
                label="Billing",
                description="Billing questions",
                keywords=["refund", "invoice", "subscription", "cancel", "stripe"],
                agent_profile="nexus-minimal",
                priority=4,
                sla_hours=4.0,
            ),
            TicketCategory(
                name="technical",
                label="Technical",
                description="Technical issues",
                keywords=["error", "crash", "plugin", "kicad", "model", "cuda"],
                agent_profile="nexus-llm",
                priority=5,
                sla_hours=8.0,
            ),
            TicketCategory(
                name="feature",
                label="Feature Request",
                description="New features",
                keywords=["feature", "request", "roadmap", "add", "suggestion"],
                agent_profile="nexus-fast",
                priority=2,
                sla_hours=48.0,
            ),
        ],
        faq_entries=[
            FAQEntry(
                question="How do I install the plugin?",
                answer="Use the KiCad Plugin Manager.",
                keywords=["install", "plugin", "kicad"],
                category="technical",
                confidence_boost=1.2,
            ),
            FAQEntry(
                question="How do I cancel my subscription?",
                answer="Visit account/billing and click cancel.",
                keywords=["cancel", "subscription", "billing"],
                category="billing",
                confidence_boost=1.0,
            ),
        ],
        confidence_threshold=0.5,
    )


@pytest.fixture
def default_config() -> SupportConfig:
    return SupportConfig(
        categories=list(DEFAULT_CATEGORIES),
        faq_entries=list(DEFAULT_FAQ_ENTRIES),
        confidence_threshold=0.5,
    )


@pytest.fixture
def billing_ticket() -> Ticket:
    return Ticket(
        id="t_001",
        subject="Refund not showing up on my invoice",
        body="I was charged $49 for the Pro plan but my refund request "
             "has not been processed. Please help.",
        customer_email="user@example.com",
        customer_id="cus_abc123",
        source="stripe",
    )


@pytest.fixture
def technical_ticket() -> Ticket:
    return Ticket(
        id="t_002",
        subject="Plugin crashes on load in KiCad 7.0",
        body="When I load the Nexus-EDA plugin, pcbnew crashes with a "
             "segfault. The error trace mentions CUDA and VRAM.",
        customer_email="dev@example.com",
        source="email",
    )


@pytest.fixture
def feature_ticket() -> Ticket:
    return Ticket(
        id="t_003",
        subject="Feature request: add Altium format import",
        body="It would be nice if you could add support for importing "
             "Altium .PrjPcb files. This would help teams migrating from Altium.",
        customer_email="engineer@example.com",
        source="api",
    )


# --------------------------------------------------------------------------- #
# Model tests
# --------------------------------------------------------------------------- #

class TestTicketCategory:
    def test_from_dict(self):
        data = {
            "name": "billing",
            "label": "Billing & Subscriptions",
            "description": "Billing questions",
            "keywords": ["refund", "invoice"],
            "agent_profile": "nexus-minimal",
            "priority": 4,
            "sla_hours": 2.0,
        }
        cat = TicketCategory.from_dict(data)
        assert cat.name == "billing"
        assert cat.label == "Billing & Subscriptions"
        assert cat.keywords == ["refund", "invoice"]
        assert cat.agent_profile == "nexus-minimal"
        assert cat.priority == 4
        assert cat.sla_hours == 2.0

    def test_from_dict_defaults(self):
        cat = TicketCategory.from_dict({"name": "general"})
        assert cat.label == "General"
        assert cat.description == ""
        assert cat.keywords == []
        assert cat.agent_profile == "nexus-fast"
        assert cat.priority == 3
        assert cat.sla_hours == 24.0

    def test_to_dict_roundtrip(self):
        cat = TicketCategory(
            name="tech",
            label="Tech Support",
            description="Tech issues",
            keywords=["bug", "error"],
            agent_profile="nexus-llm",
            priority=5,
            sla_hours=6.0,
        )
        d = cat.to_dict()
        cat2 = TicketCategory.from_dict(d)
        assert cat2 == cat


class TestFAQEntry:
    def test_from_dict(self):
        data = {
            "question": "How to install?",
            "answer": "Use pip.",
            "keywords": ["install", "pip"],
            "category": "technical",
            "confidence_boost": 1.3,
        }
        entry = FAQEntry.from_dict(data)
        assert entry.question == "How to install?"
        assert entry.answer == "Use pip."
        assert entry.keywords == ["install", "pip"]
        assert entry.category == "technical"
        assert entry.confidence_boost == 1.3

    def test_to_dict_roundtrip(self):
        entry = FAQEntry(
            question="Q?", answer="A", keywords=["q", "a"],
            category="general", confidence_boost=0.8,
        )
        d = entry.to_dict()
        entry2 = FAQEntry.from_dict(d)
        assert entry2 == entry


class TestTicket:
    def test_to_dict(self):
        from datetime import datetime
        t = Ticket(
            id="t_99", subject="Subject", body="Body text",
            customer_email="a@b.com", customer_id="cus_1",
            created_at=datetime(2026, 8, 27, 12, 0, 0),
            source="stripe", status=TicketStatus.OPEN,
        )
        d = t.to_dict()
        assert d["id"] == "t_99"
        assert d["subject"] == "Subject"
        assert d["source"] == "stripe"
        assert d["status"] == "open"
        assert d["created_at"] == "2026-08-27T12:00:00"

    def test_defaults(self):
        t = Ticket(id="1", subject="s", body="b", customer_email="x@y.com")
        assert t.customer_id is None
        assert t.source == "api"
        assert t.status == TicketStatus.OPEN


class TestRoutingDecision:
    def test_is_confident(self):
        cat = TicketCategory(name="x", label="X", description="d")
        d = RoutingDecision(category=cat, confidence=0.6)
        assert d.is_confident is True

    def test_is_not_confident(self):
        cat = TicketCategory(name="x", label="X", description="d")
        d = RoutingDecision(category=cat, confidence=0.3)
        assert d.is_confident is False

    def test_to_dict(self):
        cat = TicketCategory(name="billing", label="Billing", description="d",
                             keywords=["refund"])
        d = RoutingDecision(
            category=cat, confidence=0.85,
            matched_keywords=["refund", "invoice"],
            method="keyword", suggestion="test suggestion",
        )
        result = d.to_dict()
        assert result["category"] == "billing"
        assert result["confidence"] == 0.85
        assert result["matched_keywords"] == ["refund", "invoice"]
        assert result["method"] == "keyword"
        assert result["is_confident"] is True


# --------------------------------------------------------------------------- #
# Config tests
# --------------------------------------------------------------------------- #

class TestConfig:
    def test_builtin_defaults(self):
        config = load_config("/nonexistent/path.yaml")
        assert len(config.categories) > 0
        assert len(config.faq_entries) > 0
        assert config.confidence_threshold == 0.5
        # Check that expected categories exist
        names = [c.name for c in config.categories]
        assert "billing" in names
        assert "technical" in names

    def test_custom_yaml(self, tmp_path):
        yaml_content = """
categories:
  - name: custom
    label: Custom Category
    description: A custom category
    keywords:
      - customword
      - test
    agent_profile: nexus-fast
    priority: 5
    sla_hours: 2.0

faq:
  - question: What is custom?
    answer: It is a test.
    keywords:
      - custom
      - test
    category: custom
    confidence_boost: 1.0

confidence_threshold: 0.6
auto_reply: true
auto_reply_categories:
  - custom
"""
        config_file = tmp_path / "support_config.yaml"
        config_file.write_text(yaml_content)

        config = load_config(config_file)
        assert len(config.categories) == 1
        assert config.categories[0].name == "custom"
        assert config.categories[0].sla_hours == 2.0
        assert len(config.faq_entries) == 1
        assert config.confidence_threshold == 0.6
        assert config.auto_reply is True
        assert config.auto_reply_categories == ["custom"]

    def test_default_categories_exist(self):
        assert len(DEFAULT_CATEGORIES) == 4
        names = [c.name for c in DEFAULT_CATEGORIES]
        assert set(names) == {"billing", "technical", "feature", "bug"}

    def test_default_faq_exist(self):
        assert len(DEFAULT_FAQ_ENTRIES) >= 3
        questions = [e.question for e in DEFAULT_FAQ_ENTRIES]
        assert any("install" in q.lower() for q in questions)
        assert any("cancel" in q.lower() for q in questions)
        assert any("pricing" in q.lower() for q in questions)


# --------------------------------------------------------------------------- #
# TicketRouter tests
# --------------------------------------------------------------------------- #

class TestTicketRouter:
    def test_route_billing_ticket(self, simple_config, billing_ticket):
        router = TicketRouter(simple_config)
        decision = router.route(billing_ticket)
        assert decision.category.name == "billing"
        assert decision.confidence > 0.3
        assert "refund" in decision.matched_keywords or "invoice" in decision.matched_keywords
        assert decision.method == "keyword"

    def test_route_technical_ticket(self, simple_config, technical_ticket):
        router = TicketRouter(simple_config)
        decision = router.route(technical_ticket)
        assert decision.category.name == "technical"
        assert decision.confidence > 0.3
        assert decision.method == "keyword"

    def test_route_feature_ticket(self, simple_config, feature_ticket):
        router = TicketRouter(simple_config)
        decision = router.route(feature_ticket)
        assert decision.category.name == "feature"
        assert decision.method == "keyword"

    def test_route_no_match_falls_to_default(self, simple_config):
        ticket = Ticket(
            id="t_004",
            subject="General question about something",
            body="I have a question that doesn't match any category.",
            customer_email="user@example.com",
        )
        router = TicketRouter(simple_config)
        decision = router.route(ticket)
        # Should route to some category (default fallback)
        assert decision.category is not None
        assert decision.confidence < simple_config.confidence_threshold

    def test_route_empty_config(self):
        config = SupportConfig()
        router = TicketRouter(config)
        ticket = Ticket(id="1", subject="hi", body="hello",
                        customer_email="a@b.com")
        decision = router.route(ticket)
        assert decision.category.name == "general"
        assert decision.confidence < 0.5

    def test_route_with_llm_fallback(self, simple_config, billing_ticket):
        """When keyword confidence is low, LLM should be consulted."""
        mock_engine = MagicMock()
        mock_engine.is_loaded = True
        mock_engine.generate.return_value = json.dumps({
            "category": "billing",
            "confidence": 0.9,
            "reason": "refund keywords",
        })

        router = TicketRouter(simple_config, engine=mock_engine)
        # Force low keyword confidence by using a low threshold
        simple_config.confidence_threshold = 0.1
        # Use a ticket that won't match well
        bad_ticket = Ticket(
            id="t_005",
            subject="zzz qqq www",
            body="No matching keywords here at all.",
            customer_email="a@b.com",
        )
        decision = router.route(bad_ticket, use_llm_fallback=True)
        assert decision.method == "llm"
        assert decision.category.name == "billing"
        assert decision.confidence > 0.5

    def test_route_llm_only(self, simple_config, billing_ticket):
        mock_engine = MagicMock()
        mock_engine.is_loaded = True
        mock_engine.generate.return_value = json.dumps({
            "category": "technical",
            "confidence": 0.8,
            "reason": "error and crash",
        })

        router = TicketRouter(simple_config, engine=mock_engine)
        decision = router.route(billing_ticket, llm_only=True)
        assert decision.method == "llm"
        assert decision.category.name == "technical"
        assert decision.confidence > 0.5

    def test_route_llm_parse_failure_falls_back(self, simple_config):
        """If the LLM returns invalid JSON, keyword result should be used."""
        mock_engine = MagicMock()
        mock_engine.is_loaded = True
        mock_engine.generate.return_value = "not valid json"

        router = TicketRouter(simple_config, engine=mock_engine)
        simple_config.confidence_threshold = 0.01  # force LLM path
        ticket = Ticket(
            id="t_006", subject="refund", body="I need a refund",
            customer_email="a@b.com",
        )
        decision = router.route(ticket, use_llm_fallback=True)
        # LLM failed to parse — should have fallen back or kept keyword
        assert decision.method in ("keyword", "llm")
        # The category should still be billing (from keyword)
        assert decision.category.name == "billing"

    def test_route_no_llm_available(self, simple_config, billing_ticket):
        """Without an LLM engine, only keyword classification runs."""
        router = TicketRouter(simple_config, engine=None)
        decision = router.route(billing_ticket)
        assert decision.method == "keyword"
        assert decision.category.name == "billing"

    def test_route_auto_reply_suggestion(self, simple_config, billing_ticket):
        """When auto_reply is enabled for a category, a suggestion is generated."""
        simple_config.auto_reply_categories = ["billing"]
        router = TicketRouter(simple_config)
        decision = router.route(billing_ticket)
        assert decision.suggestion is not None
        assert "billing" in decision.suggestion.lower()

    def test_route_no_auto_reply_by_default(self, simple_config, billing_ticket):
        """No auto-reply suggestion when auto_reply is not configured."""
        router = TicketRouter(simple_config)
        decision = router.route(billing_ticket)
        assert decision.suggestion is None


# --------------------------------------------------------------------------- #
# FAQBot tests
# --------------------------------------------------------------------------- #

class TestFAQBot:
    def test_search_finds_match(self, simple_config):
        bot = FAQBot(simple_config)
        matches = bot.search("How do I install the plugin?")
        assert len(matches) > 0
        assert matches[0].entry.question == "How do I install the plugin?"
        assert matches[0].confidence > 0.0

    def test_search_returns_top_k(self, simple_config):
        bot = FAQBot(simple_config)
        matches = bot.search("install subscription refund", top_k=1)
        assert len(matches) <= 1

    def test_search_no_match(self, simple_config):
        bot = FAQBot(simple_config)
        matches = bot.search("quantum computing blockchain")
        # Should return empty or very low-confidence matches
        for m in matches:
            assert m.score < 0.1

    def test_answer_offline(self, simple_config):
        """Without LLM, the bot returns the best FAQ answer verbatim."""
        bot = FAQBot(simple_config, engine=None)
        result = bot.answer("How to install?")
        assert result.answer == "Use the KiCad Plugin Manager."
        assert result.confidence > 0.0
        assert result.matched_entry is not None
        assert result.method == "tfidf"

    def test_answer_no_match(self, simple_config):
        bot = FAQBot(simple_config, engine=None)
        result = bot.answer("xyz random nonsense zzz")
        assert "don't have a matching faq" in result.answer.lower()
        assert result.confidence == 0.0
        assert result.matched_entry is None

    def test_answer_with_llm(self, simple_config):
        """When LLM is available, it generates a grounded answer."""
        mock_engine = MagicMock()
        mock_engine.is_loaded = True
        mock_engine.generate.return_value = "To install, use the Plugin Manager."

        bot = FAQBot(simple_config, engine=mock_engine)
        result = bot.answer("How to install?", use_llm=True)
        assert result.method == "llm"
        assert result.answer == "To install, use the Plugin Manager."
        assert result.matched_entry is not None
        # Verify the engine was called with a prompt containing FAQ context
        call_args = mock_engine.generate.call_args
        assert call_args is not None
        prompt = call_args[1]["prompt"] if "prompt" in call_args[1] else call_args[0][0]
        assert "FAQ CONTEXT" in prompt
        assert "How do I install the plugin?" in prompt

    def test_answer_llm_fallback_on_engine_failure(self, simple_config):
        """If LLM fails, fall back to TF-IDF answer."""
        mock_engine = MagicMock()
        mock_engine.is_loaded = True
        from nexus_eda.llm.engine import LLMError
        mock_engine.generate.side_effect = LLMError("model not loaded")

        bot = FAQBot(simple_config, engine=mock_engine)
        result = bot.answer("How to install?", use_llm=True)
        assert result.method == "tfidf"
        assert result.answer == "Use the KiCad Plugin Manager."

    def test_confidence_boost_applied(self, simple_config):
        """FAQ entries with confidence_boost should have adjusted confidence."""
        bot = FAQBot(simple_config)
        matches = bot.search("install plugin")
        for m in matches:
            if m.entry.confidence_boost != 1.0:
                # confidence should be score * boost, capped at 1.0
                expected = min(m.score * m.entry.confidence_boost, 1.0)
                assert abs(m.confidence - expected) < 0.001

    def test_empty_faq_index(self):
        """A config with no FAQ entries should handle gracefully."""
        config = SupportConfig(faq_entries=[])
        bot = FAQBot(config)
        result = bot.answer("any question")
        assert "don't have a matching" in result.answer.lower()
        assert result.confidence == 0.0


# --------------------------------------------------------------------------- #
# Integration tests
# --------------------------------------------------------------------------- #

class TestSupportIntegration:
    def test_full_workflow_keyword_only(self, default_config):
        """End-to-end: route a ticket, then answer with FAQ."""
        router = TicketRouter(default_config, engine=None)
        bot = FAQBot(default_config, engine=None)

        ticket = Ticket(
            id="t_int_001",
            subject="Refund on my Pro subscription invoice",
            body="I was charged $49 and need a refund. Also, how do I "
                 "cancel my subscription?",
            customer_email="user@example.com",
        )

        decision = router.route(ticket)
        assert decision.category.name in ("billing", "feature")
        assert decision.confidence > 0.0

        faq_result = bot.answer("how do i cancel my subscription")
        assert faq_result.confidence > 0.0
        assert faq_result.matched_entry is not None

    def test_keyword_vs_llm_consistency(self, simple_config, billing_ticket):
        """LLM and keyword should agree on the category for an obvious ticket."""
        mock_engine = MagicMock()
        mock_engine.is_loaded = True
        mock_engine.generate.return_value = json.dumps({
            "category": "billing",
            "confidence": 0.9,
            "reason": "refund and invoice keywords matched",
        })

        router = TicketRouter(simple_config, engine=mock_engine)

        # Keyword result
        kw_decision = router.route(billing_ticket, use_llm_fallback=False)
        # LLM result
        llm_decision = router.route(billing_ticket, llm_only=True)

        assert kw_decision.category.name == "billing"
        assert llm_decision.category.name == "billing"

    def test_support_module_imports(self):
        """Verify all public symbols are importable from the package."""
        from nexus_eda.support import (
            FAQBot, TicketRouter, Ticket, TicketCategory,
            TicketStatus, RoutingDecision, FAQEntry, SupportConfig,
        )
        assert FAQBot is not None
        assert TicketRouter is not None
        assert TicketStatus.OPEN == "open"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
