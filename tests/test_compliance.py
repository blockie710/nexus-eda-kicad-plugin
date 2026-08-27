# SPDX-License-Identifier: Apache-2.0
"""Tests for the Nexus-EDA ITAR compliance audit-trail module (T4-W17.2).

Covers:
- ComplianceTier properties
- ITAR keyword detection
- ControlledArtifact authorization
- AuditEvent serialization
- ComplianceService: log, query, filter, report
- Access control: allowed, denied (unauthorized), denied (ITAR export
  without DSP license), grant/revoke
- Singleton lifecycle
"""

import json
import os
import sys
import tempfile
import secrets
from pathlib import Path

import pytest

# Ensure src is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from nexus_eda.compliance import (
    AccessRequest,
    AuditEvent,
    AuditFilter,
    AuditEventType,
    AuditOutcome,
    ComplianceError,
    ComplianceService,
    ComplianceTier,
    ControlledArtifact,
    ControlMarking,
    AuditReport,
    ITAR_KEYWORDS,
    is_itar_controlled,
    encrypt_field,
    decrypt_field,
    get_compliance_service,
    reset_compliance_service,
)


# --------------------------------------------------------------------------- #
# Tier & keyword tests
# --------------------------------------------------------------------------- #
class TestComplianceTier:
    def test_none_tier(self):
        assert not ComplianceTier.NONE.supports_itar
        assert not ComplianceTier.NONE.requires_audit_trail

    def test_gdpr_tier(self):
        assert not ComplianceTier.GDPR.supports_itar
        assert ComplianceTier.GDPR.requires_audit_trail

    def test_soc2_tier(self):
        assert not ComplianceTier.SOC2.supports_itar
        assert ComplianceTier.SOC2.requires_audit_trail

    def test_itar_tier(self):
        assert ComplianceTier.ITAR.supports_itar
        assert ComplianceTier.ITAR.requires_audit_trail


class TestItarKeywords:
    def test_detects_defense(self):
        assert is_itar_controlled("military defense project")

    def test_detects_export_controlled(self):
        assert is_itar_controlled("export-controlled technical data")

    def test_detects_dsp_license(self):
        assert is_itar_controlled("DDTC DSP-5 license")

    def test_empty_text(self):
        assert not is_itar_controlled("")

    def test_case_insensitive(self):
        assert is_itar_controlled("MILITARY APPLICATION")

    def test_keyword_set_not_empty(self):
        assert len(ITAR_KEYWORDS) > 10


# --------------------------------------------------------------------------- #
# ControlledArtifact tests
# --------------------------------------------------------------------------- #
class TestControlledArtifact:
    def test_owner_always_has_access(self):
        artifact = ControlledArtifact(
            artifact_id="art_001",
            name="board.zbb",
            control_marking=ControlMarking.ITAR,
            is_itar=True,
            owner="user_owner",
        )
        assert artifact.can_access("user_owner")

    def test_authorized_user_has_access(self):
        artifact = ControlledArtifact(
            artifact_id="art_002",
            name="firmware.bin",
            control_marking=ControlMarking.ITAR,
            is_itar=True,
            owner="user_a",
            authorized_users={"user_b", "user_c"},
        )
        assert artifact.can_access("user_b")
        assert artifact.can_access("user_c")

    def test_unauthorized_user_denied(self):
        artifact = ControlledArtifact(
            artifact_id="art_003",
            name="design.kicad_pcb",
            control_marking=ControlMarking.ITAR,
            is_itar=True,
            owner="user_a",
            authorized_users={"user_b"},
        )
        assert not artifact.can_access("user_x")

    def test_frozen_dataclass(self):
        artifact = ControlledArtifact(
            artifact_id="art_004",
            name="test",
            control_marking=ControlMarking.NONE,
            is_itar=False,
            owner="user_a",
        )
        with pytest.raises((AttributeError, TypeError)):
            artifact.name = "changed"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# AuditEvent tests
# --------------------------------------------------------------------------- #
class TestAuditEvent:
    def test_to_log_line_is_valid_json(self):
        event = AuditEvent(
            event_id="evt_001",
            timestamp="2026-08-27T10:00:00.000000",
            actor="user_a",
            event_type=AuditEventType.VIEW,
            artifact_id="art_001",
            outcome=AuditOutcome.ALLOWED,
            justification="DDTC DSP-5 license",
            ip_address="10.0.1.5",
            user_agent="Mozilla/5.0",
            detail="Viewed board layout",
        )
        line = event.to_log_line()
        parsed = json.loads(line)
        assert parsed["event_id"] == "evt_001"
        assert parsed["event_type"] == "view"
        assert parsed["outcome"] == "allowed"

    def test_ip_truncation_in_log(self):
        """IP addresses are truncated to /24 for privacy in service logs."""
        svc = ComplianceService(test_mode=True)
        svc.register_artifact(
            artifact_id="art_002",
            name="board",
            owner="user_a",
            authorized_users=["user_b"],
            is_itar=True,
        )
        req = AccessRequest(
            user_id="user_b",
            artifact_id="art_002",
            requested_action=AuditEventType.DOWNLOAD,
            justification="DDTC DSP-5 license",
            ip_address="192.168.1.100",
        )
        svc.check_access(req)
        entries = svc.query(
            filter=AuditFilter(actor="user_b", event_type=AuditEventType.DOWNLOAD)
        )
        assert len(entries) == 1
        assert entries[0]["ip_address"] == "192.168.1.x"


# --------------------------------------------------------------------------- #
# ComplianceService tests
# --------------------------------------------------------------------------- #
class TestComplianceService:
    def setup_method(self):
        reset_compliance_service()
        self.tmpdir = tempfile.mkdtemp(prefix="compliance_test_")
        self.svc = ComplianceService(
            journal_dir=self.tmpdir,
            tier=ComplianceTier.ITAR,
            test_mode=True,
        )

    def teardown_method(self):
        reset_compliance_service()

    def test_service_tier(self):
        assert self.svc.tier == ComplianceTier.ITAR

    def test_log_event_creates_entry(self):
        event = self.svc.log_event(
            actor="user_a",
            event_type=AuditEventType.VIEW,
            artifact_id="art_001",
            justification="ITAR compliance review",
        )
        assert event.event_id
        assert event.outcome == AuditOutcome.ALLOWED

    def test_log_event_denied(self):
        event = self.svc.log_event(
            actor="user_b",
            event_type=AuditEventType.EXPORT,
            artifact_id="art_001",
            outcome=AuditOutcome.DENIED,
            justification="Unauthorized export attempt",
        )
        assert event.outcome == AuditOutcome.DENIED

    def test_query_returns_logged_events(self):
        self.svc.log_event(
            actor="user_a",
            event_type=AuditEventType.VIEW,
            artifact_id="art_001",
        )
        self.svc.log_event(
            actor="user_b",
            event_type=AuditEventType.EDIT,
            artifact_id="art_001",
        )
        events = self.svc.query()
        assert len(events) == 2

    def test_query_filter_by_actor(self):
        self.svc.log_event(actor="user_a", event_type=AuditEventType.VIEW)
        self.svc.log_event(actor="user_b", event_type=AuditEventType.VIEW)
        filtered = self.svc.query(filter=AuditFilter(actor="user_a"))
        assert len(filtered) == 1
        assert filtered[0]["actor"] == "user_a"

    def test_query_filter_by_event_type(self):
        self.svc.log_event(
            actor="user_a", event_type=AuditEventType.VIEW
        )
        self.svc.log_event(
            actor="user_a", event_type=AuditEventType.EXPORT
        )
        filtered = self.svc.query(
            filter=AuditFilter(event_type=AuditEventType.EXPORT)
        )
        assert len(filtered) == 1
        assert filtered[0]["event_type"] == "export"

    def test_query_filter_by_outcome(self):
        self.svc.log_event(
            actor="user_a", event_type=AuditEventType.VIEW,
            outcome=AuditOutcome.DENIED,
        )
        self.svc.log_event(
            actor="user_b", event_type=AuditEventType.VIEW,
            outcome=AuditOutcome.ALLOWED,
        )
        denied = self.svc.query(
            filter=AuditFilter(outcome=AuditOutcome.DENIED)
        )
        assert len(denied) == 1
        assert denied[0]["outcome"] == "denied"

    def test_register_artifact(self):
        artifact = self.svc.register_artifact(
            artifact_id="art_001",
            name="design.brd",
            owner="user_a",
            authorized_users=["user_b"],
            control_marking=ControlMarking.ITAR,
            is_itar=True,
        )
        assert artifact.artifact_id == "art_001"
        assert artifact.is_itar
        assert "user_b" in artifact.authorized_users

        # Should have logged a MARK event
        events = self.svc.query(
            filter=AuditFilter(event_type=AuditEventType.MARK)
        )
        assert len(events) == 1

    # -- access control --------------------------------------------------- #
    def test_check_access_allowed_for_owner(self):
        self.svc.register_artifact(
            artifact_id="art_001",
            name="board",
            owner="user_a",
            authorized_users=["user_b"],
            is_itar=True,
        )
        req = AccessRequest(
            user_id="user_a",
            artifact_id="art_001",
            requested_action=AuditEventType.VIEW,
            justification="Design review per ITAR 31.105",
        )
        event = self.svc.check_access(req)
        assert event.outcome == AuditOutcome.ALLOWED

    def test_check_access_allowed_for_authorized_user(self):
        self.svc.register_artifact(
            artifact_id="art_001",
            name="board",
            owner="user_a",
            authorized_users=["user_b"],
            is_itar=True,
        )
        req = AccessRequest(
            user_id="user_b",
            artifact_id="art_001",
            requested_action=AuditEventType.VIEW,
            justification="Design review per ITAR 31.105",
        )
        event = self.svc.check_access(req)
        assert event.outcome == AuditOutcome.ALLOWED

    def test_check_access_denied_for_unauthorized(self):
        self.svc.register_artifact(
            artifact_id="art_001",
            name="board",
            owner="user_a",
            authorized_users=[],
            is_itar=True,
        )
        req = AccessRequest(
            user_id="user_x",
            artifact_id="art_001",
            requested_action=AuditEventType.VIEW,
            justification="Just looking",
        )
        event = self.svc.check_access(req)
        assert event.outcome == AuditOutcome.DENIED
        assert "not authorized" in event.detail

    def test_check_access_denied_for_unregistered_artifact(self):
        req = AccessRequest(
            user_id="user_a",
            artifact_id="unknown_art",
            requested_action=AuditEventType.VIEW,
            justification="Need to see this",
        )
        event = self.svc.check_access(req)
        assert event.outcome == AuditOutcome.DENIED
        assert "not registered" in event.detail

    def test_itar_export_denied_without_license(self):
        """ITAR artifact exports require a DDTC DSP license in justification."""
        self.svc.register_artifact(
            artifact_id="art_001",
            name="mil_spec_board",
            owner="user_a",
            authorized_users=["user_b"],
            is_itar=True,
        )
        # Authorized user tries to export without a DSP license mention
        req = AccessRequest(
            user_id="user_b",
            artifact_id="art_001",
            requested_action=AuditEventType.EXPORT,
            justification="Need the gerbers",
        )
        event = self.svc.check_access(req)
        assert event.outcome == AuditOutcome.DENIED
        assert "ITAR export requires" in event.detail

    def test_itar_export_allowed_with_license(self):
        self.svc.register_artifact(
            artifact_id="art_001",
            name="mil_spec_board",
            owner="user_a",
            authorized_users=["user_b"],
            is_itar=True,
        )
        req = AccessRequest(
            user_id="user_b",
            artifact_id="art_001",
            requested_action=AuditEventType.EXPORT,
            justification="DDTC DSP-5 license approved for ally partner",
        )
        event = self.svc.check_access(req)
        assert event.outcome == AuditOutcome.ALLOWED

    def test_non_itar_export_allowed(self):
        """Exports of non-ITAR artifacts don't need ITAR license."""
        self.svc.register_artifact(
            artifact_id="art_002",
            name="hobby_board",
            owner="user_a",
            authorized_users=["user_b"],
            is_itar=False,
        )
        req = AccessRequest(
            user_id="user_b",
            artifact_id="art_002",
            requested_action=AuditEventType.EXPORT,
            justification="Sharing with team",
        )
        event = self.svc.check_access(req)
        assert event.outcome == AuditOutcome.ALLOWED

    # -- grant / revoke --------------------------------------------------- #
    def test_grant_access(self):
        self.svc.register_artifact(
            artifact_id="art_001",
            name="board",
            owner="user_a",
            authorized_users=[],
            is_itar=True,
        )
        assert not self.svc.get_artifact("art_001").can_access("user_c")
        result = self.svc.grant_access(
            requester="user_a",
            artifact_id="art_001",
            user_id="user_c",
            justification="Project collaboration approved",
        )
        assert result is True
        assert self.svc.get_artifact("art_001").can_access("user_c")

        # Should log a GRANT event
        events = self.svc.query(
            filter=AuditFilter(event_type=AuditEventType.GRANT)
        )
        assert len(events) == 1

    def test_revoke_access(self):
        self.svc.register_artifact(
            artifact_id="art_001",
            name="board",
            owner="user_a",
            authorized_users=["user_b"],
            is_itar=True,
        )
        assert self.svc.get_artifact("art_001").can_access("user_b")
        result = self.svc.revoke_access(
            requester="user_a",
            artifact_id="art_001",
            user_id="user_b",
            justification="User departed project",
        )
        assert result is True
        assert not self.svc.get_artifact("art_001").can_access("user_b")

    def test_revoke_non_authorized_user(self):
        self.svc.register_artifact(
            artifact_id="art_001",
            name="board",
            owner="user_a",
            authorized_users=[],
            is_itar=True,
        )
        result = self.svc.revoke_access(
            requester="user_a",
            artifact_id="art_001",
            user_id="user_z",
        )
        assert result is False

    def test_grant_unknown_artifact(self):
        result = self.svc.grant_access(
            requester="user_a",
            artifact_id="nonexistent",
            user_id="user_b",
        )
        assert result is False


# --------------------------------------------------------------------------- #
# AuditReport tests
# --------------------------------------------------------------------------- #
class TestAuditReport:
    def setup_method(self):
        reset_compliance_service()
        self.svc = ComplianceService(test_mode=True)

    def teardown_method(self):
        reset_compliance_service()

    def test_report_counts(self):
        for _ in range(5):
            self.svc.log_event(actor="user_a", event_type=AuditEventType.VIEW)
        self.svc.log_event(
            actor="user_b",
            event_type=AuditEventType.EXPORT,
            outcome=AuditOutcome.DENIED,
        )
        self.svc.log_event(
            actor="user_c",
            event_type=AuditEventType.DOWNLOAD,
            outcome=AuditOutcome.ALLOWED,
        )
        report = self.svc.export_audit_report()
        assert report.total_events == 7
        assert report.denied_count == 1
        assert report.export_count == 2  # export + download

    def test_report_by_event_type(self):
        self.svc.log_event(actor="u", event_type=AuditEventType.VIEW)
        self.svc.log_event(actor="u", event_type=AuditEventType.EDIT)
        self.svc.log_event(actor="u", event_type=AuditEventType.VIEW)
        report = self.svc.export_audit_report()
        counts = report.by_event_type()
        assert counts["view"] == 2
        assert counts["edit"] == 1

    def test_report_top_actors(self):
        self.svc.log_event(actor="u1", event_type=AuditEventType.VIEW)
        self.svc.log_event(actor="u1", event_type=AuditEventType.VIEW)
        self.svc.log_event(actor="u2", event_type=AuditEventType.VIEW)
        report = self.svc.export_audit_report()
        top = report.top_actors()
        assert top[0][0] == "u1"
        assert top[0][1] == 2

    def test_report_to_dict(self):
        self.svc.log_event(actor="u1", event_type=AuditEventType.VIEW)
        report = self.svc.export_audit_report()
        d = report.to_dict()
        assert "total_events" in d
        assert "denied_count" in d
        assert "export_count" in d
        assert "by_event_type" in d
        assert "top_actors" in d


# --------------------------------------------------------------------------- #
# Singleton tests
# --------------------------------------------------------------------------- #
class TestComplianceServiceSingleton:
    def teardown_method(self):
        reset_compliance_service()

    def test_singleton_returns_same_instance(self):
        svc1 = get_compliance_service(test_mode=True)
        svc2 = get_compliance_service()
        assert svc1 is svc2

    def test_force_refresh(self):
        svc1 = get_compliance_service(test_mode=True)
        svc2 = get_compliance_service(force_refresh=True, test_mode=True)
        assert svc1 is not svc2

    def test_singleton_propagates_tier(self):
        svc = get_compliance_service(
            tier=ComplianceTier.GDPR, test_mode=True
        )
        assert svc.tier == ComplianceTier.GDPR


# --------------------------------------------------------------------------- #
# Journal file persistence tests
# --------------------------------------------------------------------------- #
class TestJournalPersistence:
    def setup_method(self):
        reset_compliance_service()
        self.tmpdir = tempfile.mkdtemp(prefix="compliance_journal_")
        os.environ["NEXUS_COMPLIANCE_ENABLED"] = "1"
        self.svc = ComplianceService(
            journal_dir=self.tmpdir,
            tier=ComplianceTier.ITAR,
            test_mode=False,
        )

    def teardown_method(self):
        reset_compliance_service()
        os.environ.pop("NEXUS_COMPLIANCE_ENABLED", None)

    def test_journal_file_written(self):
        self.svc.log_event(
            actor="user_a",
            event_type=AuditEventType.VIEW,
            artifact_id="art_001",
            justification="ITAR compliance review",
        )
        # Journal file should exist
        journal_files = list(Path(self.tmpdir).glob("audit_*.jsonl"))
        # import here to avoid polluting module-level imports
        assert len(journal_files) >= 1

        # Content should be valid JSON lines
        with open(journal_files[0], "r") as f:
            lines = f.readlines()
        parsed = json.loads(lines[0])
        assert parsed["actor"] == "user_a"
        assert parsed["event_type"] == "view"


# --------------------------------------------------------------------------- #
# Encryption helper tests
# --------------------------------------------------------------------------- #
class TestEncryptionHelpers:
    """Tests for AES-256-GCM encrypt_field / decrypt_field helpers."""

    def setup_method(self):
        # Generate a valid 32-byte base64 key
        import base64

        self._orig_key = os.environ.pop("NEXUS_ITAR_ENCRYPTION_KEY", None)
        key = secrets.token_bytes(32)
        os.environ["NEXUS_ITAR_ENCRYPTION_KEY"] = (
            base64.b64encode(key).decode("ascii")
        )

    def teardown_method(self):
        if self._orig_key is not None:
            os.environ["NEXUS_ITAR_ENCRYPTION_KEY"] = self._orig_key
        else:
            os.environ.pop("NEXUS_ITAR_ENCRYPTION_KEY", None)

    def test_encrypt_decrypt_roundtrip(self):
        plaintext = "Sensitive ITAR-controlled design data"
        encrypted = encrypt_field(plaintext)
        decrypted = decrypt_field(encrypted)
        assert decrypted == plaintext

    def test_encrypt_produces_different_ciphertexts(self):
        """Same plaintext should produce different ciphertext (random nonce)."""
        plaintext = "same input"
        ct1 = encrypt_field(plaintext)
        ct2 = encrypt_field(plaintext)
        assert ct1 != ct2
        # Both should decrypt back to the same plaintext
        assert decrypt_field(ct1) == plaintext
        assert decrypt_field(ct2) == plaintext

    def test_encrypt_no_key_raises(self):
        os.environ.pop("NEXUS_ITAR_ENCRYPTION_KEY", None)
        with pytest.raises(ComplianceError, match="NEXUS_ITAR_ENCRYPTION_KEY"):
            encrypt_field("data")

    def test_decrypt_no_key_raises(self):
        os.environ.pop("NEXUS_ITAR_ENCRYPTION_KEY", None)
        with pytest.raises(ComplianceError, match="NEXUS_ITAR_ENCRYPTION_KEY"):
            decrypt_field("sometoken")

    def test_decrypt_invalid_token_raises(self):
        with pytest.raises(ComplianceError, match="base64|too short"):
            decrypt_field("not-valid-base64!!!")

    def test_decrypt_wrong_key_raises(self):
        """Decrypting with a different key should fail authentication."""
        import base64

        plaintext = "secret data"
        encrypted = encrypt_field(plaintext)

        # Set a different key and try to decrypt
        key2 = secrets.token_bytes(32)
        os.environ["NEXUS_ITAR_ENCRYPTION_KEY"] = (
            base64.b64encode(key2).decode("ascii")
        )
        with pytest.raises(ComplianceError, match="decryption failed"):
            decrypt_field(encrypted)
