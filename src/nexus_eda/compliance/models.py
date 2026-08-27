# SPDX-License-Identifier: Apache-2.0
"""Data models for Nexus-EDA ITAR / Defense Enterprise compliance.

This module defines the core domain objects used by the ITAR compliance
audit-trail system (T4-W17.2, Defense Enterprise tier).

Key concepts
------------
* **ControlledArtifact** — Any design data, netlist, BOM, simulation result,
  or file that has been marked as containing ITAR-controlled technology.
  Each artifact carries a ``control_marking`` and a list of authorized
  user IDs who may access it.

* **AuditEvent** — An immutable, timestamped record of every access to,
  modification of, or export attempt on a controlled artifact.  Events
  are append-only and include the actor, action type, justification
  (legal basis), and outcome.

* **ComplianceTier** — Enum-like descriptor for the compliance tier
  associated with a subscription.  Only the Enterprise tier supports ITAR;
  lower tiers are limited to GDPR/SOC-2.

Design goals
------------
* **Graceful degradation**: The compliance module has no hard external
  dependencies.  ``cryptography`` is optional — when absent, encryption
  helpers raise :class:`ComplianceError` at call time so the rest of the
  system still imports and runs in non-ITAR mode.
* **Testability**: All public functions accept injected parameters or
  return deterministic stubs in test mode.
* **Thread safety**: The audit log writer uses a lock-protected buffer;
  the :class:`ComplianceService` singleton is also thread-safe.

Configuration (environment variables)
--------------------------------------
    NEXUS_COMPLIANCE_ENABLED   – '1' to activate ITAR audit trail globally
    NEXUS_COMPLIANCE_JOURNAL   – path to the append-only audit log directory
    NEXUS_ITAR_ENCRYPTION_KEY  – base64-encoded AES-256 key for key material
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

__all__ = [
    "ComplianceError",
    "ComplianceTier",
    "ControlMarking",
    "ControlledArtifact",
    "AuditEventType",
    "AuditOutcome",
    "AuditEvent",
    "AccessRequest",
    "ITAR_KEYWORDS",
    "is_itar_controlled",
    "ALL_COMPLIANCE_TIERS",
]


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class ComplianceError(RuntimeError):
    """Raised on compliance policy violations or misconfiguration."""


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class ComplianceTier(enum.Enum):
    """Compliance tier associated with a subscription."""

    NONE = "none"
    GDPR = "gdpr"
    SOC2 = "soc2"
    ITAR = "itar"

    @property
    def supports_itar(self) -> bool:
        """True only for the ITAR tier."""
        return self is ComplianceTier.ITAR

    @property
    def requires_audit_trail(self) -> bool:
        """True for GDPR, SOC2, and ITAR tiers."""
        return self is not ComplianceTier.NONE


class ControlMarking(enum.Enum):
    """ITAR/EAR control markings that may appear on artifacts."""

    UNCLASSIFIED = "UNCLASSIFIED"
    CUI = "CUI"  # Controlled Unclassified Information
    ITAR = "ITAR"
    EAR = "EAR"  # Export Administration Regulations
    NONE = "NONE"


class AuditEventType(enum.Enum):
    """Categories of audit events for the ITAR trail."""

    # Access events
    ACCESS = "access"
    VIEW = "view"
    EDIT = "edit"
    DOWNLOAD = "download"

    # Export / transfer events
    EXPORT = "export"
    TRANSFER = "transfer"
    SYNC = "sync"

    # Administrative
    GRANT = "grant_access"
    REVOKE = "revoke_access"
    MARK = "mark_controlled"
    UNMARK = "unmark_controlled"
    AUDIT_EXPORT = "audit_export"
    CONFIG_CHANGE = "config_change"


class AuditOutcome(enum.Enum):
    """Whether an audited action was allowed or denied."""

    ALLOWED = "allowed"
    DENIED = "denied"


# --------------------------------------------------------------------------- #
# ITAR keyword heuristics
# --------------------------------------------------------------------------- #
#: Keywords whose presence in artifact metadata suggests ITAR control.
#: These trigger automatic marking when ``auto_mark`` is enabled.
ITAR_KEYWORDS: frozenset[str] = frozenset({
    "defense", "military", "weapon", "munition", "firearm",
    "night-vision", "guided-missile", "anti-aircraft", "ballistic",
    "armament", "tactical", "combat", "munitions", "ordnance",
    "itart", "usml", "dd-form", "dsp-5", "cca", "pcn",
    "export-controlled", "defense-service",
    # Defense agency project patterns
    "navy", "army", "air-force", "marines", "afospace",
    "darpa", "nsa", "nro", "cia",
})


def is_itar_controlled(text: str) -> bool:
    """Heuristic check: does *text* contain ITAR-indicative terms?

    Performs a case-insensitive substring search.  This is intentionally
    conservative — false positives are preferable to false negatives
    in an ITAR context.
    """
    lowered = text.lower()
    return any(kw in lowered for kw in ITAR_KEYWORDS)


# --------------------------------------------------------------------------- #
# Core data classes
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ControlledArtifact:
    """Represents a design artifact subject to ITAR audit.

    Attributes:
        artifact_id:   Opaque unique identifier (e.g. UUID4 hex).
        name:          Human-readable name or path.
        control_marking: Marking applied to this artifact.
        is_itar:       True if the artifact contains ITAR-controlled tech.
        owner:         User UUID of the artifact creator / owner.
        authorized_users: Set of user UUIDs permitted to access.
        created_at:    ISO-8601 creation timestamp.
        metadata:      Free-form key/value metadata (e.g. project name).
    """

    artifact_id: str
    name: str
    control_marking: ControlMarking
    is_itar: bool
    owner: str
    authorized_users: Set[str] = field(default_factory=set)
    created_at: str = ""
    metadata: Dict[str, str] = field(default_factory=dict)

    def can_access(self, user_id: str) -> bool:
        """Return True if *user_id* is authorized to access this artifact.

        The owner always has access.  This is an O(1) set lookup.
        """
        return user_id == self.owner or user_id in self.authorized_users


@dataclass(frozen=True)
class AuditEvent:
    """An immutable, append-only audit-log entry.

    Attributes:
        event_id:      Opaque unique identifier.
        timestamp:     ISO-8601 with microsecond precision.
        actor:         User UUID performing the action.
        event_type:    Category of the action (see :class:`AuditEventType`).
        artifact_id:   ID of the artifact involved (may be empty for
                       system-level events like config changes).
        outcome:       ALLOWED or DENIED.
        justification: Legal/engineering basis (e.g. "DDTC DSP-5 license").
        ip_address:    Requesting client IP (truncated to /24 for privacy).
        user_agent:    Client UA string (truncated).
        detail:        Free-form detail string.
    """

    event_id: str
    timestamp: str
    actor: str
    event_type: AuditEventType
    artifact_id: str
    outcome: AuditOutcome
    justification: str = ""
    ip_address: str = ""
    user_agent: str = ""
    detail: str = ""

    def to_log_line(self) -> str:
        """Serialize to a single-line JSON string for the audit journal."""
        import json

        return json.dumps({
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "actor": self.actor,
            "event_type": self.event_type.value,
            "artifact_id": self.artifact_id,
            "outcome": self.outcome.value,
            "justification": self.justification,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "detail": self.detail,
        }, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class AccessRequest:
    """A user's request to access an ITAR-controlled artifact.

    The compliance service evaluates this against the artifact's
    authorization policy and produces an :class:`AuditEvent`.
    """

    user_id: str
    artifact_id: str
    requested_action: AuditEventType
    justification: str
    ip_address: str = ""
    user_agent: str = ""


# --------------------------------------------------------------------------- #
# Tier catalog
# --------------------------------------------------------------------------- #
#: All compliance tiers, ordered from most restrictive to least.
ALL_COMPLIANCE_TIERS: List[ComplianceTier] = [
    ComplianceTier.ITAR,
    ComplianceTier.SOC2,
    ComplianceTier.GDPR,
    ComplianceTier.NONE,
]
