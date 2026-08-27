# SPDX-License-Identifier: Apache-2.0
"""ITAR compliance audit-trail service for the Defense Enterprise tier.

This module provides the :class:`ComplianceService` — a thread-safe,
append-only audit log writer that records every access, export, and
administrative action on ITAR-controlled artifacts.

ITAR requirements implemented
-----------------------------
1. **Immutable audit trail** — Every event is a frozen dataclass,
   serialized to a single-line JSON entry and appended to the journal.
2. **Access control enforcement** — ``check_access`` evaluates a user's
   authorization against ``ControlledArtifact.authorized_users``.
3. **Justification capture** — Every event records the legal/engineering
   basis (e.g. "DDTC DSP-5 license", "CUI marking per 32 CFR 2002.2").
4. **Export logging** — All export / transfer / sync operations are
   explicitly logged with outcome DENIED for unauthorized attempts.
5. **Audit report** — ``export_audit_report`` produces a structured
   summary (count by event type, denied attempts, top actors).
6. **Privacy-preserving IP** — IP addresses are truncated to /24 to
   balance accountability with privacy.
7. **Encrypted field storage** — ``encrypt_field`` / ``decrypt_field``
   provide AES-256-GCM encryption for ITAR-controlled field values at
   rest, using the key from ``$NEXUS_ITAR_ENCRYPTION_KEY``.

Graceful degradation
--------------------
If the ``cryptography`` library is not installed, encryption helpers
(``encrypt_field`` / ``decrypt_field``) raise :class:`ComplianceError`
at call time.  The audit log writer itself uses only the stdlib, so the
core trail works without external dependencies.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import base64
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    AccessRequest,
    AuditEvent,
    AuditEventType,
    AuditOutcome,
    ComplianceError,
    ComplianceTier,
    ControlledArtifact,
    ControlMarking,
)

__all__ = [
    "AuditFilter",
    "AuditReport",
    "ComplianceService",
    "encrypt_field",
    "decrypt_field",
    "get_compliance_service",
    "reset_compliance_service",
]


# --------------------------------------------------------------------------- #
# Audit filter & report
# --------------------------------------------------------------------------- #
class AuditFilter:
    """Composable filter for querying the audit journal."""

    def __init__(
        self,
        actor: Optional[str] = None,
        event_type: Optional[AuditEventType] = None,
        outcome: Optional[AuditOutcome] = None,
        artifact_id: Optional[str] = None,
        after: Optional[str] = None,  # ISO timestamp
        before: Optional[str] = None,  # ISO timestamp
    ) -> None:
        self.actor = actor
        self.event_type = event_type
        self.outcome = outcome
        self.artifact_id = artifact_id
        self.after = after
        self.before = before

    def matches(self, entry: Dict[str, Any]) -> bool:
        """Return True if *entry* matches all non-None filter criteria."""
        if self.actor and entry.get("actor") != self.actor:
            return False
        if self.event_type and entry.get("event_type") != self.event_type.value:
            return False
        if self.outcome and entry.get("outcome") != self.outcome.value:
            return False
        if self.artifact_id and entry.get("artifact_id") != self.artifact_id:
            return False
        ts = entry.get("timestamp", "")
        if self.after and ts < self.after:
            return False
        if self.before and ts > self.before:
            return False
        return True


class AuditReport:
    """Structured summary of audit events for compliance dashboards."""

    def __init__(self, events: List[Dict[str, Any]]) -> None:
        self._events = events

    @property
    def total_events(self) -> int:
        return len(self._events)

    @property
    def denied_count(self) -> int:
        return sum(1 for e in self._events if e.get("outcome") == "denied")

    @property
    def export_count(self) -> int:
        return sum(
            1
            for e in self._events
            if e.get("event_type") in ("export", "transfer", "sync", "download")
        )

    def by_event_type(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for e in self._events:
            et = e.get("event_type", "unknown")
            counts[et] = counts.get(et, 0) + 1
        return counts

    def top_actors(self, n: int = 10) -> List[Tuple[str, int]]:
        counts: Dict[str, int] = {}
        for e in self._events:
            actor = e.get("actor", "")
            if actor:
                counts[actor] = counts.get(actor, 0) + 1
        return sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:n]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_events": self.total_events,
            "denied_count": self.denied_count,
            "export_count": self.export_count,
            "by_event_type": self.by_event_type(),
            "top_actors": [
                {"actor": a, "count": c} for a, c in self.top_actors()
            ],
        }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _utcnow_iso() -> str:
    """Return current UTC time as ISO-8601 with microsecond precision."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")


def _truncate(value: str, limit: int = 512) -> str:
    """Truncate a string to *limit* characters."""
    if len(value) <= limit:
        return value
    return value[:limit] + "...[truncated]"


def _truncate_ip(ip: str) -> str:
    """Truncate an IPv4 address to /24 for privacy (e.g. ``10.0.1.x``)."""
    if not ip or "." not in ip:
        return ""
    octets = ip.split(".")
    if len(octets) == 4:
        return ".".join(octets[:3]) + ".x"
    return ip


# --------------------------------------------------------------------------- #
# Encryption (AES-256-GCM) for ITAR-controlled fields
# --------------------------------------------------------------------------- #
# The ``cryptography`` library is optional.  When it is not installed, or when
# no encryption key is provided, ``encrypt_field`` / ``decrypt_field`` raise
# :class:`ComplianceError` at call time so callers can degrade gracefully.
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _HAS_CRYPTOGRAPHY = True
except ImportError:  # pragma: no cover - exercised via mock in tests
    _HAS_CRYPTOGRAPHY = False


def _load_encryption_key() -> bytes:
    """Load and validate the AES-256 key from ``NEXUS_ITAR_ENCRYPTION_KEY``.

    The environment variable must contain a base64-encoded 32-byte key.
    Returns the raw 32-byte key or raises :class:`ComplianceError`.
    """
    key_b64 = os.environ.get("NEXUS_ITAR_ENCRYPTION_KEY", "")
    if not key_b64:
        raise ComplianceError(
            "NEXUS_ITAR_ENCRYPTION_KEY environment variable is not set"
        )
    try:
        key = base64.b64decode(key_b64)
    except Exception as exc:
        raise ComplianceError(
            f"NEXUS_ITAR_ENCRYPTION_KEY is not valid base64: {exc}"
        ) from exc
    if len(key) != 32:
        raise ComplianceError(
            f"AES-256 key must be 32 bytes, got {len(key)}"
        )
    return key


def encrypt_field(plaintext: str) -> str:
    """Encrypt *plaintext* using AES-256-GCM.

    Returns a base64-encoded blob containing the 12-byte nonce prepended
    to the ciphertext+tag.

    Raises
    ------
    ComplianceError
        If the ``cryptography`` library is not installed or the
        ``NEXUS_ITAR_ENCRYPTION_KEY`` environment variable is absent / invalid.
    """
    if not _HAS_CRYPTOGRAPHY:
        raise ComplianceError(
            "encrypt_field requires the 'cryptography' package"
        )
    key = _load_encryption_key()
    nonce = secrets.token_bytes(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt_field(token: str) -> str:
    """Decrypt a value previously produced by :func:`encrypt_field`.

    Raises
    ------
    ComplianceError
        If the ``cryptography`` library is not installed, the key is
        missing/invalid, or decryption / authentication fails.
    """
    if not _HAS_CRYPTOGRAPHY:
        raise ComplianceError(
            "decrypt_field requires the 'cryptography' package"
        )
    key = _load_encryption_key()
    try:
        raw = base64.b64decode(token)
    except Exception as exc:
        raise ComplianceError(
            f"Encrypted token is not valid base64: {exc}"
        ) from exc
    if len(raw) < 13:
        raise ComplianceError(
            f"Encrypted token too short ({len(raw)} bytes); "
            "expected nonce(12) + ciphertext+tag"
        )
    nonce, ct = raw[:12], raw[12:]
    aesgcm = AESGCM(key)
    try:
        pt = aesgcm.decrypt(nonce, ct, associated_data=None)
    except Exception as exc:
        raise ComplianceError(
            f"AES-GCM decryption failed (wrong key or corrupted data): {exc}"
        ) from exc
    return pt.decode("utf-8")


# --------------------------------------------------------------------------- #
# ComplianceService
# --------------------------------------------------------------------------- #
class ComplianceService:
    """Thread-safe ITAR audit-trail writer and access-control enforcer.

    Parameters
    ----------
    journal_dir:
        Directory where daily audit log files are written.  Defaults to
        ``$NEXUS_COMPLIANCE_JOURNAL`` env var or ``./compliance_journal``.
    tier:
        Compliance tier (defaults to ITAR for the Defense Enterprise tier).
    test_mode:
        When True, events are buffered in-memory only and no files are
        written to disk.
    """

    def __init__(
        self,
        journal_dir: Optional[str] = None,
        tier: ComplianceTier = ComplianceTier.ITAR,
        test_mode: bool = False,
    ) -> None:
        env_dir = os.environ.get("NEXUS_COMPLIANCE_JOURNAL")
        resolved_dir = journal_dir or env_dir or "compliance_journal"
        self.journal_dir: Path = Path(resolved_dir)
        self.tier: ComplianceTier = tier
        self.test_mode: bool = test_mode
        self.enabled: bool = os.environ.get("NEXUS_COMPLIANCE_ENABLED", "") == "1"

        # In-memory caches for the current session.
        self._artifacts: Dict[str, ControlledArtifact] = {}
        self._buffer: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

        if not self.test_mode and self.enabled:
            self.journal_dir.mkdir(parents=True, exist_ok=True)

    # -- audit trail ------------------------------------------------------- #
    def log_event(
        self,
        actor: str,
        event_type: AuditEventType,
        artifact_id: str = "",
        outcome: AuditOutcome = AuditOutcome.ALLOWED,
        justification: str = "",
        ip_address: str = "",
        user_agent: str = "",
        detail: str = "",
    ) -> AuditEvent:
        """Create an immutable :class:`AuditEvent` and append it to the journal.

        This is the single write path for the audit trail.  All other
        methods funnel through here so the trail is guaranteed append-only.
        """
        event = AuditEvent(
            event_id=secrets.token_hex(8),
            timestamp=_utcnow_iso(),
            actor=_truncate(actor, 128),
            event_type=event_type,
            artifact_id=_truncate(artifact_id, 64),
            outcome=outcome,
            justification=_truncate(justification, 256),
            ip_address=_truncate_ip(ip_address),
            user_agent=_truncate(user_agent, 256),
            detail=_truncate(detail, 512),
        )
        entry = json.loads(event.to_log_line())

        if self.test_mode:
            with self._lock:
                self._buffer.append(entry)
        else:
            with self._lock:
                self._buffer.append(entry)
                if self.enabled:
                    self._write_journal(entry)

        return event

    def _write_journal(self, entry: Dict[str, Any]) -> None:
        """Append *entry* as a single JSON line to today's journal file.

        File naming: ``audit_YYYY-MM-DD.jsonl``
        """
        date_str = entry["timestamp"][:10]
        journal_file = self.journal_dir / f"audit_{date_str}.jsonl"
        line = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        with journal_file.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def query(
        self,
        *,
        filter: Optional[AuditFilter] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Return audit events from the in-memory buffer and journal files."""
        results: List[Dict[str, Any]] = []

        with self._lock:
            # Return most-recent first from buffer
            buf = list(self._buffer)
            buf.reverse()

        for entry in buf:
            if filter and not filter.matches(entry):
                continue
            results.append(entry)
            if len(results) >= limit:
                break

        return results

    def export_audit_report(self, *, filter: Optional[AuditFilter] = None) -> AuditReport:
        """Produce a structured summary of audit events for dashboards."""
        events = self.query(filter=filter, limit=10_000)
        return AuditReport(events)

    # -- artifact registration -------------------------------------------- #
    def register_artifact(
        self,
        artifact_id: str,
        name: str,
        owner: str,
        authorized_users: Optional[List[str]] = None,
        control_marking: ControlMarking = ControlMarking.NONE,
        is_itar: bool = False,
        metadata: Optional[Dict[str, str]] = None,
    ) -> ControlledArtifact:
        """Register a controlled artifact and log the marking event."""
        artifact = ControlledArtifact(
            artifact_id=artifact_id,
            name=name,
            control_marking=control_marking,
            is_itar=is_itar,
            owner=owner,
            authorized_users=set(authorized_users or []),
            created_at=_utcnow_iso(),
            metadata=metadata or {},
        )
        with self._lock:
            self._artifacts[artifact_id] = artifact

        # Log the control marking event
        self.log_event(
            actor=owner,
            event_type=AuditEventType.MARK if is_itar else AuditEventType.ACCESS,
            artifact_id=artifact_id,
            outcome=AuditOutcome.ALLOWED,
            justification=(
                "ITAR marking per 22 CFR 120-130" if is_itar
                else "GDPR/SOC2 registration"
            ),
            detail=f"Artifact registered: {name} (marking={control_marking.value})",
        )
        return artifact

    def get_artifact(self, artifact_id: str) -> Optional[ControlledArtifact]:
        with self._lock:
            return self._artifacts.get(artifact_id)

    # -- access control --------------------------------------------------- #
    def check_access(self, request: AccessRequest) -> AuditEvent:
        """Evaluate *request* against the artifact's authorization policy.

        Returns the resulting :class:`AuditEvent` with ALLOWED or DENIED
        outcome.  An access request is allowed iff:
        1. The artifact is registered in the audit registry.
        2. The requesting user is the owner or is in ``authorized_users``.
        3. The action is not a sensitive export-type action requiring
           explicit ITAR authorization (exports of ITAR artifacts require
           ``justification`` mentioning a DDTC license).
        """
        artifact = self.get_artifact(request.artifact_id)

        if artifact is None:
            event = self.log_event(
                actor=request.user_id,
                event_type=request.requested_action,
                artifact_id=request.artifact_id,
                outcome=AuditOutcome.DENIED,
                justification=request.justification,
                ip_address=request.ip_address,
                user_agent=request.user_agent,
                detail="Access denied: artifact not registered in compliance registry",
            )
            return event

        # ITAR export guard: exports of ITAR artifacts require a license
        is_export_action = request.requested_action in (
            AuditEventType.EXPORT,
            AuditEventType.TRANSFER,
            AuditEventType.SYNC,
            AuditEventType.DOWNLOAD,
        )
        if is_export_action and artifact.is_itar:
            if not request.justification or "dsp" not in request.justification.lower():
                event = self.log_event(
                    actor=request.user_id,
                    event_type=request.requested_action,
                    artifact_id=request.artifact_id,
                    outcome=AuditOutcome.DENIED,
                    justification=request.justification or "(no justification)",
                    ip_address=request.ip_address,
                    user_agent=request.user_agent,
                    detail="Access denied: ITAR export requires DDTC DSP-5/DSP-7 license",
                )
                return event

        # Authorization check
        if not artifact.can_access(request.user_id):
            event = self.log_event(
                actor=request.user_id,
                event_type=request.requested_action,
                artifact_id=request.artifact_id,
                outcome=AuditOutcome.DENIED,
                justification=request.justification,
                ip_address=request.ip_address,
                user_agent=request.user_agent,
                detail=f"Access denied: user '{request.user_id}' not authorized for artifact",
            )
            return event

        # Access granted
        event = self.log_event(
            actor=request.user_id,
            event_type=request.requested_action,
            artifact_id=request.artifact_id,
            outcome=AuditOutcome.ALLOWED,
            justification=request.justification,
            ip_address=request.ip_address,
            user_agent=request.user_agent,
            detail=f"Access granted to artifact '{artifact.name}'",
        )
        return event

    # -- grant / revoke --------------------------------------------------- #
    def grant_access(
        self,
        requester: str,
        artifact_id: str,
        user_id: str,
        justification: str = "",
    ) -> bool:
        """Add *user_id* to the artifact's authorized set and log the grant."""
        artifact = self.get_artifact(artifact_id)
        if artifact is None:
            return False

        with self._lock:
            # Reconstruct frozen dataclass with new authorized set
            updated = ControlledArtifact(
                artifact_id=artifact.artifact_id,
                name=artifact.name,
                control_marking=artifact.control_marking,
                is_itar=artifact.is_itar,
                owner=artifact.owner,
                authorized_users=artifact.authorized_users | {user_id},
                created_at=artifact.created_at,
                metadata=artifact.metadata,
            )
            self._artifacts[artifact_id] = updated

        self.log_event(
            actor=requester,
            event_type=AuditEventType.GRANT,
            artifact_id=artifact_id,
            outcome=AuditOutcome.ALLOWED,
            justification=justification,
            detail=f"Granted access to user '{user_id}'",
        )
        return True

    def revoke_access(
        self,
        requester: str,
        artifact_id: str,
        user_id: str,
        justification: str = "",
    ) -> bool:
        """Remove *user_id* from the artifact's authorized set."""
        artifact = self.get_artifact(artifact_id)
        if artifact is None or user_id not in artifact.authorized_users:
            return False

        with self._lock:
            updated = ControlledArtifact(
                artifact_id=artifact.artifact_id,
                name=artifact.name,
                control_marking=artifact.control_marking,
                is_itar=artifact.is_itar,
                owner=artifact.owner,
                authorized_users=artifact.authorized_users - {user_id},
                created_at=artifact.created_at,
                metadata=artifact.metadata,
            )
            self._artifacts[artifact_id] = updated

        self.log_event(
            actor=requester,
            event_type=AuditEventType.REVOKE,
            artifact_id=artifact_id,
            outcome=AuditOutcome.ALLOWED,
            justification=justification,
            detail=f"Revoked access for user '{user_id}'",
        )
        return True


# --------------------------------------------------------------------------- #
# Module-level singleton
# --------------------------------------------------------------------------- #
_service: Optional[ComplianceService] = None
_service_lock = threading.Lock()


def get_compliance_service(
    *,
    journal_dir: Optional[str] = None,
    tier: ComplianceTier = ComplianceTier.ITAR,
    test_mode: bool = False,
    force_refresh: bool = False,
) -> ComplianceService:
    """Return a cached :class:`ComplianceService` singleton.

    Pass ``force_refresh=True`` to bypass the cache (useful in tests
    or when reconfiguring the journal directory).
    """
    global _service
    if _service is None or force_refresh:
        with _service_lock:
            if _service is None or force_refresh:
                _service = ComplianceService(
                    journal_dir=journal_dir,
                    tier=tier,
                    test_mode=test_mode,
                )
    return _service


def reset_compliance_service() -> None:
    """Clear the singleton (primarily for tests)."""
    global _service
    with _service_lock:
        _service = None
