# SPDX-License-Identifier: Apache-2.0
"""Data models and company database for enterprise beta onboarding.

Defines the core data structures used by the Enterprise tier onboarding
workflow: company profiles, compliance requirements (ITAR/GDPR), enterprise
tiers, and a persistent JSON-backed company database.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class EnterpriseTier(str, Enum):
    """Enterprise subscription tiers for the Nexus-EDA Enterprise plan."""

    STANDARD = "standard"      # 1-10 engineers, basic ITAR/GDPR compliance
    DEFENSE = "defense"        # ITAR/EAR + CMMC, 11-100 engineers
    AEROSPACE = "aerospace"    # ITAR + AS9100, 100+ engineers, SLA

    @property
    def monthly_price_usd(self) -> float:
        return {
            EnterpriseTier.STANDARD: 2_500.0,
            EnterpriseTier.DEFENSE: 7_500.0,
            EnterpriseTier.AEROSPACE: 15_000.0,
        }[self]

    @property
    def max_engineers(self) -> int:
        return {
            EnterpriseTier.STANDARD: 10,
            EnterpriseTier.DEFENSE: 100,
            EnterpriseTier.AEROSPACE: 1_000,
        }[self]

    @property
    def requires_cma(self) -> bool:
        """Whether Controlled Unclassified Information (CMA) compliance is needed."""
        return self in (EnterpriseTier.DEFENSE, EnterpriseTier.AEROSPACE)

    @property
    def requires_as9100(self) -> bool:
        """Whether AS9100 aerospace quality management is required."""
        return self == EnterpriseTier.AEROSPACE


class OnboardingStatus(str, Enum):
    """Lifecycle state of an enterprise onboarding."""

    INVITED = "invited"          # Beta invite sent
    ACCEPTED = "accepted"         # Company accepted invite
    COMPLIANCE_CHECK = "compliance_check"  # Running compliance verification
    PROVISIONING = "provisioning"  # Tenant/deployment being set up
    ACTIVE = "active"            # Fully onboarded, active subscription
    REJECTED = "rejected"        # Declined or failed compliance


@dataclass
class ComplianceStatus:
    """Compliance verification result for a single regulation."""

    regulation: str
    status: str  # "compliant", "pending", "non_compliant", "exempt"
    evidence_path: Optional[str] = None
    verified_at: Optional[datetime] = None
    notes: str = ""


@dataclass
class CompanyProfile:
    """A registered enterprise customer profile.

    Attributes:
        id: UUIDv4 identifier
        name: Company legal name
        industry: 'defense', 'aerospace', or 'other'
        website: Company website URL
        employee_count: Headcount estimate
        tier: Enterprise tier assigned
        onboarding_status: Current onboarding state
        compliance: Per-regulation compliance status
        tenant_id: Provisioned tenant identifier (once active)
        deployment_target: 'airgapped', 'onprem', 'govcloud'
        contact_email: Primary contact
        uei: Unique Executive Identifier (SAM.gov) for federal contracting eligibility
        cmmc_level: CMMC assessment level (defense only)
        as9100_certified: Whether AS9100 certification is held (aerospace only)
        created_at: Profile creation timestamp
        updated_at: Last modification timestamp
    """

    id: str
    name: str
    industry: str
    website: str
    employee_count: int
    tier: EnterpriseTier
    onboarding_status: OnboardingStatus
    compliance: dict[str, ComplianceStatus] = field(default_factory=dict)
    tenant_id: Optional[str] = None
    deployment_target: Optional[str] = None
    contact_email: str = ""
    uei: Optional[str] = None
    cmmc_level: Optional[int] = None
    as9100_certified: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    @classmethod
    def create(
        cls,
        name: str,
        industry: str,
        website: str,
        employee_count: int,
        tier: EnterpriseTier,
        contact_email: str,
        uei: Optional[str] = None,
        cmmc_level: Optional[int] = None,
        as9100_certified: bool = False,
    ) -> "CompanyProfile":
        """Create a new company profile in the 'invited' state."""
        now = datetime.now()
        return cls(
            id=str(uuid4()),
            name=name,
            industry=industry.lower(),
            website=website,
            employee_count=employee_count,
            tier=tier,
            onboarding_status=OnboardingStatus.INVITED,
            contact_email=contact_email,
            uei=uei,
            cmmc_level=cmmc_level,
            as9100_certified=as9100_certified,
            created_at=now,
            updated_at=now,
        )

    @property
    def is_defense(self) -> bool:
        return self.industry == "defense"

    @property
    def is_aerospace(self) -> bool:
        return self.industry == "aerospace"

    @property
    def is_beta_candidate(self) -> bool:
        """Whether this company qualifies for beta onboarding."""
        return self.industry in ("defense", "aerospace")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "industry": self.industry,
            "website": self.website,
            "employee_count": self.employee_count,
            "tier": self.tier.value,
            "onboarding_status": self.onboarding_status.value,
            "compliance": {
                k: {
                    "regulation": v.regulation,
                    "status": v.status,
                    "evidence_path": v.evidence_path,
                    "verified_at": v.verified_at.isoformat() if v.verified_at else None,
                    "notes": v.notes,
                }
                for k, v in self.compliance.items()
            },
            "tenant_id": self.tenant_id,
            "deployment_target": self.deployment_target,
            "contact_email": self.contact_email,
            "uei": self.uei,
            "cmmc_level": self.cmmc_level,
            "as9100_certified": self.as9100_certified,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompanyProfile":
        compliance: dict[str, ComplianceStatus] = {}
        for k, v in (data.get("compliance") or {}).items():
            verified_at = None
            if v.get("verified_at"):
                try:
                    verified_at = datetime.fromisoformat(v["verified_at"])
                except (ValueError, TypeError):
                    pass
            compliance[k] = ComplianceStatus(
                regulation=v.get("regulation", k),
                status=v.get("status", "pending"),
                evidence_path=v.get("evidence_path"),
                verified_at=verified_at,
                notes=v.get("notes", ""),
            )

        now = datetime.now()
        created = now
        if data.get("created_at"):
            try:
                created = datetime.fromisoformat(data["created_at"])
            except (ValueError, TypeError):
                pass
        updated = now
        if data.get("updated_at"):
            try:
                updated = datetime.fromisoformat(data["updated_at"])
            except (ValueError, TypeError):
                pass

        return cls(
            id=data.get("id", str(uuid4())),
            name=data["name"],
            industry=data["industry"],
            website=data["website"],
            employee_count=data["employee_count"],
            tier=EnterpriseTier(data["tier"]),
            onboarding_status=OnboardingStatus(data["onboarding_status"]),
            compliance=compliance,
            tenant_id=data.get("tenant_id"),
            deployment_target=data.get("deployment_target"),
            contact_email=data.get("contact_email", ""),
            uei=data.get("uei"),
            cmmc_level=data.get("cmmc_level"),
            as9100_certified=data.get("as9100_certified", False),
            created_at=created,
            updated_at=updated,
        )


# --------------------------------------------------------------------------- #
# Company database (JSON-backed persistence)
# --------------------------------------------------------------------------- #
class CompanyDatabase:
    """JSON-backed persistent store for enterprise company profiles.

    The database is a single JSON file with an array of company dicts.
    All read/write operations are atomic (write to temp, then rename).
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._companies: dict[str, CompanyProfile] = {}

    def load(self) -> "CompanyDatabase":
        """Load companies from the JSON database file.

        If the file does not exist, starts with an empty database.
        """
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            entries = data.get("companies", data) if isinstance(data, dict) else data
            for entry in entries:
                profile = CompanyProfile.from_dict(entry)
                self._companies[profile.id] = profile
        return self

    def save(self) -> None:
        """Persist all companies to the JSON database file atomically."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "companies": [p.to_dict() for p in self._companies.values()],
        }
        tmp_path = self.path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)
        tmp_path.replace(self.path)

    def add(self, profile: CompanyProfile) -> None:
        """Add a new company profile to the database."""
        self._companies[profile.id] = profile
        self.save()

    def get(self, company_id: str) -> Optional[CompanyProfile]:
        """Retrieve a company by its UUID."""
        return self._companies.get(company_id)

    def get_by_name(self, name: str) -> Optional[CompanyProfile]:
        """Retrieve a company by exact name match (case-insensitive)."""
        name_lower = name.lower()
        for profile in self._companies.values():
            if profile.name.lower() == name_lower:
                return profile
        return None

    def update(self, profile: CompanyProfile) -> None:
        """Update an existing company profile."""
        profile.updated_at = datetime.now()
        self._companies[profile.id] = profile
        self.save()

    def remove(self, company_id: str) -> bool:
        """Remove a company by ID. Returns True if removed."""
        if company_id in self._companies:
            del self._companies[company_id]
            self.save()
            return True
        return False

    def list_all(self) -> list[CompanyProfile]:
        """Return all company profiles."""
        return list(self._companies.values())

    def list_by_status(self, status: OnboardingStatus) -> list[CompanyProfile]:
        """Return companies with a given onboarding status."""
        return [
            p for p in self._companies.values()
            if p.onboarding_status == status
        ]

    def list_beta_candidates(self) -> list[CompanyProfile]:
        """Return companies that qualify for beta (defense/aerospace)."""
        return [p for p in self._companies.values() if p.is_beta_candidate]

    def list_active(self) -> list[CompanyProfile]:
        """Return companies with active onboarding status."""
        return self.list_by_status(OnboardingStatus.ACTIVE)

    @property
    def count(self) -> int:
        return len(self._companies)


# --------------------------------------------------------------------------- #
# Compliance rules
# --------------------------------------------------------------------------- #
def determine_required_compliance(profile: CompanyProfile) -> list[str]:
    """Determine which compliance regulations apply to a company based on tier/industry.

    Returns a list of regulation IDs (e.g. 'itar', 'gdpr', 'cmmc', 'as9100').
    """
    regulations: list[str] = []

    if profile.tier.requires_cma:
        regulations.append("itar")
        regulations.append("cmmc")
    if profile.tier.requires_as9100:
        regulations.append("as9100")

    # GDPR applies to any EU-facing company regardless of tier
    if profile.is_eu_facing():
        regulations.append("gdpr")

    # Defense and aerospace contractors need EAR
    if profile.is_defense or profile.is_aerospace:
        regulations.append("ear")

    # Deduplicate, preserving order
    seen: set[str] = set()
    result: list[str] = []
    for r in regulations:
        if r not in seen:
            seen.add(r)
            result.append(r)
    return result


# Extend CompanyProfile with helper methods for compliance
def _company_is_eu_facing(self: CompanyProfile) -> bool:
    """Check if the company is EU-facing (website domain or contact in EU)."""
    eu_tlds = (".eu", ".de", ".fr", ".nl", ".be", ".it", ".es", ".se", ".fi",
               ".no", ".dk", ".at", ".ch", ".ie", ".pt", ".gr", ".pl", ".cz",
               ".hu", ".sk", ".si", ".lt", ".lv", ".ee", ".lu", ".bg", ".ro",
               ".hr")
    if self.website:
        domain = self.website.lower()
        if any(domain.endswith(tld) for tld in eu_tlds):
            return True
    return False


# Attach the helper to CompanyProfile (monkey-patch for clean separation)
CompanyProfile.is_eu_facing = _company_is_eu_facing  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# Validation helpers
# --------------------------------------------------------------------------- #
_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
)
_UEI_RE = re.compile(r"^\d{12}$")
_WEBSITE_RE = re.compile(
    r"^https?://[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)*$"
)


def validate_company_input(
    name: str,
    website: str,
    employee_count: int,
    contact_email: str,
    industry: str,
    uei: Optional[str] = None,
) -> list[str]:
    """Validate input fields for a new company profile. Returns list of error strings."""
    errors: list[str] = []

    if not name or len(name.strip()) < 2:
        errors.append("Company name must be at least 2 characters.")
    if not website or not _WEBSITE_RE.match(website):
        errors.append(f"Invalid website URL: {website}")
    if employee_count < 1:
        errors.append("Employee count must be >= 1.")
    if not contact_email or not _EMAIL_RE.match(contact_email):
        errors.append(f"Invalid contact email: {contact_email}")
    if industry.lower() not in ("defense", "aerospace", "other"):
        errors.append(f"Industry must be 'defense', 'aerospace', or 'other'; got '{industry}'.")
    if uei is not None and not _UEI_RE.match(uei):
        errors.append(f"UEI must be a 12-digit number; got '{uei}'.")

    return errors
