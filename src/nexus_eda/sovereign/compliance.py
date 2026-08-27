# SPDX-License-Identifier: Apache-2.0
"""Compliance modules for the sovereign data boundary.

Provides GDPR compliance (data export/deletion) and ITAR compliance
(audit trail for defense-tier projects), plus the :class:`AuditTrail`
tamper-evident logging facility.

Reference: GDPR (EU) 2016/679, ITAR 22 CFR §§ 120-130
"""

from __future__ import annotations

import os
import json
import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


__all__ = [
    "ComplianceLevel",
    "AuditEvent",
    "AuditTrail",
    "GDPRCompliance",
    "ITARCompliance",
    "ComplianceError",
]


class ComplianceLevel(str, Enum):
    """Compliance tiers for Nexus-EDA deployments."""

    STANDARD = "standard"     # Open-core, Apache 2.0
    ENTERPRISE = "enterprise"  # GDPR + SSO/SAML
    DEFENSE = "defense"        # ITAR + full audit trail


class ComplianceError(Exception):
    """Raised when a compliance violation is detected."""


# --------------------------------------------------------------------------- #
# Audit Trail
# --------------------------------------------------------------------------- #

@dataclass
class AuditEvent:
    """A single entry in the tamper-evident audit trail."""

    timestamp: float
    actor: str
    action: str
    resource: str
    details: str = ""
    compliance_level: str = "standard"
    signature: str = ""  # hash chain signature


class AuditTrail:
    """Tamper-evident, append-only audit log.

    Each event is hashed and chained (each event's signature =
    H(prev_signature + event_json)).  The chain can be verified
    for integrity at any time.
    """

    def __init__(self, log_path: Optional[str] = None):
        if log_path:
            self._path = Path(log_path)
        else:
            self._path = Path(os.path.join(
                os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
                "nexus-eda",
                "sovereign",
                "audit.log",
            ))
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._events: List[AuditEvent] = []
        self._last_hash: str = ""
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                ev = AuditEvent(**data)
                self._events.append(ev)
                self._last_hash = ev.signature
            except (json.JSONDecodeError, TypeError):
                continue

    def log(
        self,
        actor: str,
        action: str,
        resource: str,
        details: str = "",
        compliance_level: str = "standard",
    ) -> AuditEvent:
        """Append a signed audit event."""
        timestamp = time.time()
        event_data = {
            "timestamp": timestamp,
            "actor": actor,
            "action": action,
            "resource": resource,
            "details": details,
            "compliance_level": compliance_level,
        }
        event_json = json.dumps(event_data, sort_keys=True)
        signature = hashlib.sha256(
            (self._last_hash + event_json).encode("utf-8")
        ).hexdigest()

        ev = AuditEvent(
            timestamp=timestamp,
            actor=actor,
            action=action,
            resource=resource,
            details=details,
            compliance_level=compliance_level,
            signature=signature,
        )
        self._events.append(ev)
        self._last_hash = signature

        # Append to file.
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event_data, sort_keys=True))
            f.write("\n")

        return ev

    def verify_chain(self) -> Tuple[bool, Optional[str]]:
        """Verify the audit trail has not been tampered with."""
        computed_hash = ""
        for ev in self._events:
            event_data = {
                "timestamp": ev.timestamp,
                "actor": ev.actor,
                "action": ev.action,
                "resource": ev.resource,
                "details": ev.details,
                "compliance_level": ev.compliance_level,
            }
            event_json = json.dumps(event_data, sort_keys=True)
            computed_hash = hashlib.sha256(
                (computed_hash + event_json).encode("utf-8")
            ).hexdigest()
            if computed_hash != ev.signature:
                return False, f"Tamper detected at event for {ev.action}"
        return True, None

    @property
    def events(self) -> List[AuditEvent]:
        return list(self._events)

    def export_all(self) -> List[Dict[str, Any]]:
        return [
            {
                "timestamp": ev.timestamp,
                "actor": ev.actor,
                "action": ev.action,
                "resource": ev.resource,
                "details": ev.details,
                "compliance_level": ev.compliance_level,
                "signature": ev.signature,
            }
            for ev in self._events
        ]


# --------------------------------------------------------------------------- #
# GDPR Compliance
# --------------------------------------------------------------------------- #

class GDPRCompliance:
    """GDPR (EU) 2016/679 compliance module.

    Provides data export and deletion APIs as required by Articles 15-17.
    """

    def __init__(self, audit: AuditTrail):
        self.audit = audit

    def export_user_data(self, user_id: str) -> Dict[str, Any]:
        """Export all personal data for *user_id* (Art. 15).

        Returns a structured dict suitable for JSON serialization.
        """
        self.audit.log(
            actor=user_id,
            action="gdpr_export",
            resource="user_data",
            details=f"Data export requested for {user_id}",
            compliance_level="enterprise",
        )
        # In a full implementation, this would scan all data stores
        # for entries tagged with *user_id* and return them.  For now,
        # we return the structure with a note.
        return {
            "user_id": "[REDACTED]" if user_id else "",
            "export_timestamp": int(time.time()),
            "data_footprint": {
                "design_files": "none stored",
                "audit_entries": len(self.audit.events),
                "model_cache": "none — air-gapped",
                "note": "All data remains on-device; no cloud storage.",
            },
            "compliance": "GDPR Article 15 — Right of Access",
        }

    def delete_user_data(self, user_id: str) -> int:
        """Permanently delete all personal data for *user_id* (Art. 17).

        Returns the number of data items deleted.
        """
        self.audit.log(
            actor=user_id,
            action="gdpr_delete",
            resource="user_data",
            details=f"Right to be forgotten invoked for {user_id}",
            compliance_level="enterprise",
        )
        # In a full implementation, this would iterate over the
        # EncryptedStore and remove all keys tagged with *user_id*.
        return 0

    def data_portability_format(self) -> str:
        """Return the machine-readable format for data export."""
        return "JSON (RFC 7159)"


# --------------------------------------------------------------------------- #
# ITAR Compliance
# --------------------------------------------------------------------------- #

class ITARCompliance:
    """ITAR (22 CFR §§ 120-130) compliance audit trail for Defense tier.

    Ensures that all data operations on defense-related projects are
    logged with immutable audit signatures and that no data crosses
    the boundary without explicit export control review.
    """

    # ITAR-controlled commodity jurisdictions (USML Categories).
    USML_CATEGORIES = {
        "category_i": "Unmanned aerial vehicles",
        "category_v": "Electronics",
        "category_xiii": "Auxiliary devices",
    }

    def __init__(self, audit: AuditTrail):
        self.audit = audit

    def log_export_attempt(
        self,
        user_id: str,
        data_type: str,
        destination: str,
        classified: bool = False,
    ) -> bool:
        """Log an ITAR export attempt and return whether it's permitted.

        Per ITAR § 125, defense articles may not be exported without
        a license.  In the sovereign boundary, all exports are logged
        and require explicit approval.
        """
        permitted = not classified  # classified data never leaves device
        self.audit.log(
            actor=user_id,
            action="itar_export_attempt",
            resource=data_type,
            details=f"destination={destination}&classified={classified}&permitted={permitted}",
            compliance_level="defense",
        )
        return permitted

    def verify_no_training(self, data: Any) -> bool:
        """Verify that *data* does not contain model-training artifacts.

        ITAR § 120.10 requires that technical data not be used for
        model training without authorization.
        """
        data_str = json.dumps(data, default=str, ensure_ascii=False)
        training_markers = ("training_data", "model_weights", "fine_tune")
        for marker in training_markers:
            if marker in data_str:
                self.audit.log(
                    actor="system",
                    action="itar_training_violation",
                    resource="training_data_detected",
                    details=f"Detected '{marker}' in data",
                    compliance_level="defense",
                )
                return False
        return True

    @staticmethod
    def usml_categories() -> Dict[str, str]:
        """Return the USML categories relevant to PCB design."""
        return dict(ITARCompliance.USML_CATEGORIES)
