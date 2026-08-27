# SPDX-License-Identifier: Apache-2.0
"""ITAR compliance audit-trail module for the Defense Enterprise tier.

This package provides the audit-trail infrastructure specified in T4-W17.2:
immutable audit events, access control, ITAR export guards, and
report generation.

Public API
----------
* :class:`ComplianceService` — thread-safe audit writer and enforcer.
* :class:`ControlledArtifact` — ITAR-controlled design artifact.
* :class:`AuditEvent` / :class:`AccessRequest` — event and request types.
* :func:`is_itar_controlled` — keyword-based ITAR detection heuristic.
"""

from .models import (
    AccessRequest,
    AuditEvent,
    AuditEventType,
    AuditOutcome,
    ComplianceError,
    ComplianceTier,
    ControlledArtifact,
    ControlMarking,
    ITAR_KEYWORDS,
    is_itar_controlled,
    ALL_COMPLIANCE_TIERS,
)
from .audit import (
    AuditFilter,
    AuditReport,
    ComplianceService,
    encrypt_field,
    decrypt_field,
    get_compliance_service,
    reset_compliance_service,
)

__all__ = [
    # Models
    "AccessRequest",
    "AuditEvent",
    "AuditEventType",
    "AuditOutcome",
    "ComplianceError",
    "ComplianceTier",
    "ControlledArtifact",
    "ControlMarking",
    "ITAR_KEYWORDS",
    "is_itar_controlled",
    "ALL_COMPLIANCE_TIERS",
    # Service
    "AuditFilter",
    "AuditReport",
    "ComplianceService",
    "encrypt_field",
    "decrypt_field",
    "get_compliance_service",
    "reset_compliance_service",
]
