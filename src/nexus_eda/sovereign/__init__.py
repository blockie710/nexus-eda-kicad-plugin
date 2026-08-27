# SPDX-License-Identifier: Apache-2.0
"""Nexus-EDA Sovereign Data Boundary — Phase 4 (SABLE-inspired).

Implements the NDA-safe, air-gapped, non-training data boundary that sits
between the open-core plugin and any on-prem / enterprise deployment.
All design data stays on-device; no telemetry, no model training, no exfil.

28 scoped entry points are defined in ``ENTRY_POINTS``.  Each entry point
strips or redacts specific categories of sensitive data (PDK paths, project
paths, proprietary model paths, user identifiers) before any operation that
could leak outside the trusted boundary.
"""

from .boundary import (
    SovereignBoundary,
    SovereignPolicy,
    SovereignResult,
    ENTRY_POINTS,
    ENTRY_POINT_COUNT,
    BoundaryError,
)
from .store import EncryptedStore, AES256Crypto, StoreError
from .compliance import (    GDPRCompliance,
    ITARCompliance,
    ComplianceLevel,
    AuditTrail,
)

__all__ = [
    "SovereignBoundary",
    "SovereignPolicy",
    "SovereignResult",
    "ENTRY_POINTS",
    "ENTRY_POINT_COUNT",
    "BoundaryError",
    "EncryptedStore",
    "AES256Crypto",
    "StoreError",
    "GDPRCompliance",
    "ITARCompliance",
    "ComplianceLevel",
    "AuditTrail",
]

__version__ = "1.0.0"
