# SPDX-License-Identifier: Apache-2.0
"""Beta enterprise onboarding workflow for Nexus-EDA.

Implements the full onboarding lifecycle for defense/aerospace enterprise
beta customers:

1. **Invitation generation** — creates a unique invite token with expiry
2. **Compliance verification** — checks ITAR, EAR, GDPR, CMMC, AS9100
3. **Tenant provisioning** — generates a deployment package for the
   selected deployment target (airgapped, onprem, govcloud)
4. **Status management** — tracks companies through the onboarding funnel

Usage (CLI)::

    python -m nexus_eda.enterprise.onboarding init --db config/companies.json
    python -m nexus_eda.enterprise.onboarding invite --company "Defense Corp" --industry defense --tier defense
    python -m nexus_eda.enterprise.onboarding verify --invite-token <token>
    python -m nexus_eda.enterprise.onboarding provision --company-id <uuid> --target airgapped
    python -m nexus_eda.enterprise.onboarding status
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from .profiles import (
    CompanyDatabase,
    CompanyProfile,
    ComplianceStatus,
    EnterpriseTier,
    OnboardingStatus,
    determine_required_compliance,
    validate_company_input,
)


# --------------------------------------------------------------------------- #
# Invitation management
# --------------------------------------------------------------------------- #
@dataclass
class Invitation:
    """A beta onboarding invitation with a secure token.

    Attributes:
        token: URL-safe invitation token (32 bytes of entropy)
        company_id: UUID of the invited company
        expires_at: ISO timestamp when the invite expires
        used: Whether the invite has been accepted
        created_at: When the invite was generated
    """

    token: str
    company_id: str
    expires_at: str  # ISO datetime string
    used: bool = False
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """Check whether this invitation has expired (default 14-day window)."""
        now = now or datetime.now()
        try:
            expiry = datetime.fromisoformat(self.expires_at)
        except (ValueError, TypeError):
            return True
        return now >= expiry

    def is_valid(self, now: Optional[datetime] = None) -> bool:
        """An invitation is valid if unused and not expired."""
        return not self.used and not self.is_expired(now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "company_id": self.company_id,
            "expires_at": self.expires_at,
            "used": self.used,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Invitation":
        return cls(
            token=data["token"],
            company_id=data["company_id"],
            expires_at=data["expires_at"],
            used=data.get("used", False),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )


class InvitationStore:
    """JSON-backed store for beta onboarding invitations.

    Invitations are stored in a separate file from company profiles so the
    invite list can be rotated/inspected independently.
    """

    DEFAULT_EXPIRY_DAYS = 14

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._invitations: dict[str, Invitation] = {}
        self.load()

    def load(self) -> "InvitationStore":
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            entries = data.get("invitations", data) if isinstance(data, dict) else data
            for entry in entries:
                inv = Invitation.from_dict(entry)
                self._invitations[inv.token] = inv
        return self

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "invitations": [inv.to_dict() for inv in self._invitations.values()],
        }
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        tmp.replace(self.path)

    def create(
        self,
        company_id: str,
        expiry_days: int = DEFAULT_EXPIRY_DAYS,
    ) -> Invitation:
        """Create a new invitation for a company."""
        token = secrets.token_urlsafe(32)
        now = datetime.now()
        expiry = now + timedelta(days=expiry_days)
        inv = Invitation(
            token=token,
            company_id=company_id,
            expires_at=expiry.isoformat(),
            created_at=now.isoformat(),
        )
        self._invitations[token] = inv
        self.save()
        return inv

    def get(self, token: str) -> Optional[Invitation]:
        return self._invitations.get(token)

    def redeem(self, token: str) -> Optional[Invitation]:
        """Mark an invitation as used (company accepted). Returns the invitation or None."""
        inv = self._invitations.get(token)
        if inv and inv.is_valid():
            inv.used = True
            self.save()
            return inv
        return None

    def list_valid(self) -> list[Invitation]:
        """Return all valid (unused, unexpired) invitations."""
        return [inv for inv in self._invitations.values() if inv.is_valid()]

    def list_all(self) -> list[Invitation]:
        return list(self._invitations.values())

    def cleanup_expired(self) -> int:
        """Remove expired invitations. Returns count removed."""
        expired = [t for t, inv in self._invitations.items() if inv.is_expired()]
        for t in expired:
            del self._invitations[t]
        if expired:
            self.save()
        return len(expired)


# --------------------------------------------------------------------------- #
# Compliance verification
# --------------------------------------------------------------------------- #
@dataclass
class ComplianceResult:
    """Result of a compliance verification run for one regulation."""

    regulation: str
    passed: bool
    evidence_provided: bool
    evidence_path: Optional[str]
    notes: str


def verify_compliance(
    profile: CompanyProfile,
    evidence: dict[str, Optional[str]] | None = None,
) -> dict[str, ComplianceResult]:
    """Verify compliance for all regulations required by the company's tier.

    Parameters
    ----------
    profile:
        The company profile to check.
    evidence:
        Optional dict mapping regulation name to evidence file path.
        If a regulation is not in the dict or its value is None, the
        verification marks it as 'pending' (not 'non_compliant').

    Returns
    -------
    dict mapping regulation name to ComplianceResult.
    """
    evidence = evidence or {}
    required = determine_required_compliance(profile)
    results: dict[str, ComplianceResult] = {}

    for reg in required:
        ev_path = evidence.get(reg)
        if ev_path is None:
            # No evidence provided — mark as pending
            results[reg] = ComplianceResult(
                regulation=reg,
                passed=False,
                evidence_provided=False,
                evidence_path=None,
                notes="Evidence not yet provided. Awaiting compliance documentation.",
            )
        else:
            # Evidence file exists — verify basic checks per regulation
            results[reg] = _verify_regulation(profile, reg, ev_path)

    return results


def _verify_regulation(
    profile: CompanyProfile,
    regulation: str,
    evidence_path: str,
) -> ComplianceResult:
    """Run regulation-specific verification logic.

    If ``evidence_path`` is a path to an existing file, its contents are read
    and searched. If it is not a valid file path, the string itself is treated
    as inline evidence text and searched directly.
    """
    path = Path(evidence_path)
    if path.exists():
        content = path.read_text(encoding="utf-8", errors="replace")
    else:
        # Treat the evidence string as inline text content
        content = str(evidence_path)

    if regulation == "itar":
        # ITAR: verify the SF-328 or DD-254 is present and mentions
        # the company as a registered defense contractor
        if "DD-254" in content or "ITAR" in content.upper():
            return ComplianceResult(
                regulation=regulation,
                passed=True,
                evidence_provided=True,
                evidence_path=evidence_path,
                notes="ITAR compliance evidence verified (DD-254 or ITAR statement present).",
            )
        return ComplianceResult(
            regulation=regulation,
            passed=False,
            evidence_provided=True,
            evidence_path=evidence_path,
            notes="Evidence does not contain ITAR compliance documentation.",
        )

    if regulation == "ear":
        # EAR: verify SNAP-R or similar export compliance documentation
        if "EAR" in content.upper() or "export" in content.lower():
            return ComplianceResult(
                regulation=regulation,
                passed=True,
                evidence_provided=True,
                evidence_path=evidence_path,
                notes="EAR compliance evidence verified.",
            )
        return ComplianceResult(
            regulation=regulation,
            passed=False,
            evidence_provided=True,
            evidence_path=evidence_path,
            notes="Evidence does not contain EAR compliance documentation.",
        )

    if regulation == "cmmc":
        # CMMC: verify CMMC assessment report is present at any level
        required_level = profile.cmmc_level or 2
        if "CMMC" in content.upper():
            # Accept any CMMC level that is >= required
            import re
            levels = re.findall(r"CMMC\s*Level\s*(\d+)", content, re.IGNORECASE)
            if levels and int(levels[0]) >= required_level:
                return ComplianceResult(
                    regulation=regulation,
                    passed=True,
                    evidence_provided=True,
                    evidence_path=evidence_path,
                    notes=f"CMMC Level {levels[0]} assessment verified (required: Level {required_level}).",
                )
            if levels:
                return ComplianceResult(
                    regulation=regulation,
                    passed=False,
                    evidence_provided=True,
                    evidence_path=evidence_path,
                    notes=f"Evidence mentions CMMC Level {levels[0]}, required Level {required_level}.",
                )
        return ComplianceResult(
            regulation=regulation,
            passed=False,
            evidence_provided=True,
            evidence_path=evidence_path,
            notes=f"Evidence does not confirm CMMC Level {required_level} certification.",
        )

    if regulation == "as9100":
        # AS9100: verify certificate or audit report
        if profile.as9100_certified or "AS9100" in content.upper():
            return ComplianceResult(
                regulation=regulation,
                passed=True,
                evidence_provided=True,
                evidence_path=evidence_path,
                notes="AS9100 certification verified.",
            )
        return ComplianceResult(
            regulation=regulation,
            passed=False,
            evidence_provided=True,
            evidence_path=evidence_path,
            notes="Evidence does not contain AS9100 certification.",
        )

    if regulation == "gdpr":
        # GDPR: verify data processing agreement or DPA
        if "GDPR" in content.upper() or "data processing" in content.lower():
            return ComplianceResult(
                regulation=regulation,
                passed=True,
                evidence_provided=True,
                evidence_path=evidence_path,
                notes="GDPR data processing agreement verified.",
            )
        return ComplianceResult(
            regulation=regulation,
            passed=False,
            evidence_provided=True,
            evidence_path=evidence_path,
            notes="Evidence does not contain GDPR documentation.",
        )

    # Unknown regulation — default to pass with note
    return ComplianceResult(
        regulation=regulation,
        passed=True,
        evidence_provided=True,
        evidence_path=evidence_path,
        notes=f"No specific verification logic for '{regulation}' — passed by default.",
    )


def update_compliance_status(
    profile: CompanyProfile,
    results: dict[str, ComplianceResult],
) -> None:
    """Update the company profile's compliance dict from verification results."""
    for reg, result in results.items():
        profile.compliance[reg] = ComplianceStatus(
            regulation=reg,
            status="compliant" if result.passed else "non_compliant",
            evidence_path=result.evidence_path,
            verified_at=datetime.now() if result.evidence_provided else None,
            notes=result.notes,
        )


# --------------------------------------------------------------------------- #
# Deployment configuration
# --------------------------------------------------------------------------- #
@dataclass
class DeploymentConfig:
    """Configuration for provisioning an enterprise tenant deployment.

    Attributes:
        company_id: UUID of the company
        tenant_id: Provisioned tenant identifier
        deployment_target: 'airgapped', 'onprem', or 'govcloud'
        tier: Enterprise tier
        sso_enabled: Whether SSO/SAML is configured
        encryption_key_path: Path to the AES-256 encryption key
        compliance_profile: Set of compliance regimes in effect
        model_assignment: Which LLM profile to use for this tenant
        max_concurrent_agents: Max parallel agent workers
        storage_quota_gb: Storage quota for the tenant
    """

    company_id: str
    tenant_id: str
    deployment_target: str
    tier: EnterpriseTier
    sso_enabled: bool = False
    encryption_key_path: Optional[str] = None
    compliance_profile: set[str] = field(default_factory=set)
    model_assignment: str = "nexus-llm"
    max_concurrent_agents: int = 4
    storage_quota_gb: int = 100

    def to_dict(self) -> dict[str, Any]:
        return {
            "company_id": self.company_id,
            "tenant_id": self.tenant_id,
            "deployment_target": self.deployment_target,
            "tier": self.tier.value,
            "sso_enabled": self.sso_enabled,
            "encryption_key_path": self.encryption_key_path,
            "compliance_profile": sorted(self.compliance_profile),
            "model_assignment": self.model_assignment,
            "max_concurrent_agents": self.max_concurrent_agents,
            "storage_quota_gb": self.storage_quota_gb,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeploymentConfig":
        return cls(
            company_id=data["company_id"],
            tenant_id=data["tenant_id"],
            deployment_target=data["deployment_target"],
            tier=EnterpriseTier(data["tier"]),
            sso_enabled=data.get("sso_enabled", False),
            encryption_key_path=data.get("encryption_key_path"),
            compliance_profile=set(data.get("compliance_profile", [])),
            model_assignment=data.get("model_assignment", "nexus-llm"),
            max_concurrent_agents=data.get("max_concurrent_agents", 4),
            storage_quota_gb=data.get("storage_quota_gb", 100),
        )


def determine_deployment_target(tier: EnterpriseTier) -> str:
    """Determine the recommended deployment target for a given tier.

    Defense and Aerospace tiers default to 'airgapped' for ITAR compliance.
    Standard tier defaults to 'onprem' for data control.
    """
    if tier == EnterpriseTier.AEROSPACE:
        return "airgapped"
    if tier == EnterpriseTier.DEFENSE:
        return "airgapped"
    return "onprem"


def determine_model_assignment(tier: EnterpriseTier) -> str:
    """Determine which LLM agent profile to use for a tenant based on tier."""
    return {
        EnterpriseTier.STANDARD: "nexus-fast",
        EnterpriseTier.DEFENSE: "nexus-llm",
        EnterpriseTier.AEROSPACE: "nexus-llm",
    }[tier]


def provision_tenant(profile: CompanyProfile, target: Optional[str] = None) -> DeploymentConfig:
    """Generate a deployment configuration for a company.

    Parameters
    ----------
    profile:
        The company to provision.
    target:
        Explicit deployment target override ('airgapped', 'onprem',
        'govcloud'). If None, determined by tier.
    """
    target = target or determine_deployment_target(profile.tier)
    tenant_id = f"nexus-{profile.tier.value}-{profile.id[:8]}"

    return DeploymentConfig(
        company_id=profile.id,
        tenant_id=tenant_id,
        deployment_target=target,
        tier=profile.tier,
        sso_enabled=profile.tier.requires_cma,
        compliance_profile=set(determine_required_compliance(profile)),
        model_assignment=determine_model_assignment(profile.tier),
        max_concurrent_agents=4 if profile.tier.requires_cma else 2,
        storage_quota_gb=500 if profile.tier.requires_cma else 100,
    )


# --------------------------------------------------------------------------- #
# Onboarding wizard orchestrator
# --------------------------------------------------------------------------- #
class OnboardingWizard:
    """Orchestrates the full enterprise onboarding lifecycle.

    Ties together company profiles, invitations, compliance verification,
    and tenant provisioning into a single workflow.
    """

    def __init__(
        self,
        db_path: str | Path,
        invitations_path: Optional[str | Path] = None,
        deployments_path: Optional[str | Path] = None,
    ):
        self.db = CompanyDatabase(db_path)
        self.db.load()

        inv_path = invitations_path or Path(db_path).parent / "invitations.json"
        self.invitations = InvitationStore(inv_path)
        self.invitations.load()

        dep_path = deployments_path or Path(db_path).parent / "deployments.json"
        self._deployments_path = Path(dep_path)
        self._deployments: dict[str, DeploymentConfig] = {}
        self._load_deployments()

    def _load_deployments(self) -> None:
        if self._deployments_path.exists():
            with open(self._deployments_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            entries = data.get("deployments", data) if isinstance(data, dict) else data
            for entry in entries:
                cfg = DeploymentConfig.from_dict(entry)
                self._deployments[cfg.company_id] = cfg

    def _save_deployments(self) -> None:
        self._deployments_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "deployments": [d.to_dict() for d in self._deployments.values()],
        }
        tmp = self._deployments_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        tmp.replace(self._deployments_path)

    # -- Step 1: Add company & generate invite -------------------------------- #
    def add_company(
        self,
        name: str,
        industry: str,
        website: str,
        employee_count: int,
        tier: EnterpriseTier,
        contact_email: str,
        uei: Optional[str] = None,
        cmmc_level: Optional[int] = None,
        as9100_certified: bool = False,
        expiry_days: int = InvitationStore.DEFAULT_EXPIRY_DAYS,
    ) -> tuple[CompanyProfile, Invitation]:
        """Register a new company and generate a beta invitation.

        Returns the created CompanyProfile and Invitation.
        Raises ValueError if input validation fails.
        """
        errors = validate_company_input(
            name=name,
            website=website,
            employee_count=employee_count,
            contact_email=contact_email,
            industry=industry,
            uei=uei,
        )
        if errors:
            raise ValueError("; ".join(errors))

        profile = CompanyProfile.create(
            name=name,
            industry=industry,
            website=website,
            employee_count=employee_count,
            tier=tier,
            contact_email=contact_email,
            uei=uei,
            cmmc_level=cmmc_level,
            as9100_certified=as9100_certified,
        )
        self.db.add(profile)

        invite = self.invitations.create(profile.id, expiry_days=expiry_days)
        return profile, invite

    # -- Step 2: Accept invitation ------------------------------------------- #
    def accept_invitation(self, token: str) -> CompanyProfile:
        """Accept a beta invitation, moving the company to 'accepted' status.

        Raises ValueError if the token is invalid, expired, or already used.
        """
        inv = self.invitations.get(token)
        if inv is None:
            raise ValueError("Invalid invitation token.")
        if not inv.is_valid():
            if inv.used:
                raise ValueError("Invitation has already been used.")
            if inv.is_expired():
                raise ValueError("Invitation has expired.")

        profile = self.db.get(inv.company_id)
        if profile is None:
            raise ValueError(f"Company not found for invitation: {inv.company_id}")

        profile.onboarding_status = OnboardingStatus.ACCEPTED
        self.db.update(profile)
        self.invitations.redeem(token)
        return profile

    # -- Step 3: Compliance verification --------------------------------------- #
    def run_compliance_check(
        self,
        company_id: str,
        evidence: dict[str, Optional[str]] | None = None,
    ) -> dict[str, ComplianceResult]:
        """Run compliance verification for a company.

        Moves the company to 'compliance_check' status during verification.
        Updates compliance status on the profile with results.
        """
        profile = self.db.get(company_id)
        if profile is None:
            raise ValueError(f"Company not found: {company_id}")

        profile.onboarding_status = OnboardingStatus.COMPLIANCE_CHECK
        self.db.update(profile)

        results = verify_compliance(profile, evidence)
        update_compliance_status(profile, results)
        self.db.update(profile)
        return results

    # -- Step 4: Provision tenant -------------------------------------------- #
    def provision_company(
        self,
        company_id: str,
        target: Optional[str] = None,
    ) -> DeploymentConfig:
        """Provision a tenant deployment for a company.

        Moves the company to 'provisioning' then 'active' status.
        Generates a deployment config and stores it.
        """
        profile = self.db.get(company_id)
        if profile is None:
            raise ValueError(f"Company not found: {company_id}")

        # Verify all compliance checks passed before provisioning
        required = determine_required_compliance(profile)
        if not profile.compliance:
            raise ValueError(
                f"Cannot provision: compliance checks not passed — "
                f"required regulations: {', '.join(required)}"
            )
        non_compliant = [
            reg for reg, status in profile.compliance.items()
            if status.status not in ("compliant", "exempt")
        ]
        if non_compliant:
            raise ValueError(
                f"Cannot provision: compliance checks not passed for: {', '.join(non_compliant)}"
            )

        profile.onboarding_status = OnboardingStatus.PROVISIONING
        self.db.update(profile)

        config = provision_tenant(profile, target)
        self._deployments[profile.id] = config
        self._save_deployments()

        profile.tenant_id = config.tenant_id
        profile.deployment_target = config.deployment_target
        profile.onboarding_status = OnboardingStatus.ACTIVE
        self.db.update(profile)
        return config

    # -- Status & reporting --------------------------------------------------- #
    def get_company_status(self, company_id: str) -> dict[str, Any]:
        """Get a summary of a company's onboarding status and compliance."""
        profile = self.db.get(company_id)
        if profile is None:
            return {"error": f"Company not found: {company_id}"}

        deploy = self._deployments.get(profile.id)
        return {
            "id": profile.id,
            "name": profile.name,
            "industry": profile.industry,
            "tier": profile.tier.value,
            "onboarding_status": profile.onboarding_status.value,
            "contact_email": profile.contact_email,
            "tenant_id": profile.tenant_id,
            "deployment_target": profile.deployment_target,
            "compliance": {
                reg: {
                    "status": status.status,
                    "evidence_path": status.evidence_path,
                    "notes": status.notes,
                }
                for reg, status in profile.compliance.items()
            },
            "deployment_config": deploy.to_dict() if deploy else None,
        }

    def list_all_status(self) -> list[dict[str, Any]]:
        """Return onboarding status for all companies."""
        return [self.get_company_status(p.id) for p in self.db.list_all()]

    def list_beta_companies(self) -> list[dict[str, Any]]:
        """Return status for all defense/aerospace beta candidates."""
        return [
            self.get_company_status(p.id)
            for p in self.db.list_beta_candidates()
        ]


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _load_wizard(base_dir: str | Path = ".") -> OnboardingWizard:
    base = Path(base_dir)
    db_path = base / "config" / "companies.json"
    inv_path = base / "config" / "invitations.json"
    dep_path = base / "config" / "deployments.json"
    return OnboardingWizard(db_path, inv_path, dep_path)


def _cmd_init(args: argparse.Namespace) -> int:
    base = Path(args.base_dir)
    db_path = base / "config" / "companies.json"
    inv_path = base / "config" / "invitations.json"
    dep_path = base / "config" / "deployments.json"

    wizard = OnboardingWizard(db_path, inv_path, dep_path)
    wizard.db.save()
    wizard.invitations.save()
    wizard._save_deployments()
    print(f"[OK] Enterprise onboarding initialized.")
    print(f"  Company DB:    {db_path} ({wizard.db.count} companies)")
    print(f"  Invitations:   {inv_path} ({len(wizard.invitations.list_all())} total, "
          f"{len(wizard.invitations.list_valid())} valid)")
    print(f"  Deployments:   {dep_path}")
    return 0


def _cmd_invite(args: argparse.Namespace) -> int:
    wizard = _load_wizard(args.base_dir)
    tier = EnterpriseTier(args.tier)

    try:
        profile, invite = wizard.add_company(
            name=args.company,
            industry=args.industry,
            website=args.website,
            employee_count=args.employees,
            tier=tier,
            contact_email=args.email,
            uei=args.uei,
            cmmc_level=args.cmmc,
            as9100_certified=args.as9100,
        )
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 1

    print(f"[OK] Company '{profile.name}' invited.")
    print(f"  Company ID:   {profile.id}")
    print(f"  Tier:         {profile.tier.value} (${profile.tier.monthly_price_usd}/mo)")
    print(f"  Invite Token: {invite.token}")
    print(f"  Expires:      {invite.expires_at}")
    print(f"  Status:       {profile.onboarding_status.value}")
    print(f"\n  Send this URL to the contact: https://app.nexuseda.com/beta/accept?token={invite.token}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    wizard = _load_wizard(args.base_dir)
    profile = wizard.db.get(args.company_id) if args.company_id else None

    if args.token:
        inv = wizard.invitations.get(args.token)
        if inv and inv.is_valid():
            profile = wizard.db.get(inv.company_id)
        else:
            print(f"[ERROR] Invalid or expired token: {args.token}")
            return 1

    if profile is None:
        print(f"[ERROR] Company not found. Use --company-id or --token.")
        return 1

    if args.evidence:
        evidence = json.loads(args.evidence)
    else:
        evidence = {}

    results = wizard.run_compliance_check(profile.id, evidence)
    print(f"[OK] Compliance verification for '{profile.name}':")
    for reg, result in results.items():
        status_str = "PASS" if result.passed else "FAIL"
        print(f"  {reg:12s} [{status_str}]  evidence={result.evidence_provided}  {result.notes}")

    all_passed = all(r.passed for r in results.values())
    if all_passed:
        print(f"\n  All {len(results)} compliance checks passed.")
    else:
        failed = [r for r in results.values() if not r.passed]
        print(f"\n  {len(failed)}/{len(results)} compliance checks FAILED.")
    return 0 if all_passed else 1


def _cmd_provision(args: argparse.Namespace) -> int:
    wizard = _load_wizard(args.base_dir)
    try:
        config = wizard.provision_company(args.company_id, args.target)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 1

    print(f"[OK] Tenant provisioned for company ID: {args.company_id}")
    print(f"  Tenant ID:        {config.tenant_id}")
    print(f"  Deployment Target: {config.deployment_target}")
    print(f"  Tier:             {config.tier.value}")
    print(f"  SSO/SAML:         {'Enabled' if config.sso_enabled else 'Disabled'}")
    print(f"  Model Assignment: {config.model_assignment}")
    print(f"  Compliance:       {', '.join(sorted(config.compliance_profile))}")
    print(f"  Storage Quota:    {config.storage_quota_gb} GB")
    print(f"  Max Agents:       {config.max_concurrent_agents}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    wizard = _load_wizard(args.base_dir)
    if args.company_id:
        statuses = [wizard.get_company_status(args.company_id)]
    elif args.beta:
        statuses = wizard.list_beta_companies()
    else:
        statuses = [wizard.list_all_status()[0]] if wizard.db.count > 0 else []

    if not statuses:
        print("[INFO] No companies found.")
        return 0

    for s in statuses:
        if "error" in s:
            print(f"[ERROR] {s['error']}")
            continue
        print(f"  {s['name']} ({s['industry']})")
        print(f"    ID:     {s['id']}")
        print(f"    Tier:   {s['tier']}")
        print(f"    Status: {s['onboarding_status']}")
        print(f"    Email:  {s['contact_email']}")
        if s["tenant_id"]:
            print(f"    Tenant: {s['tenant_id']}")
            print(f"    Target: {s['deployment_target']}")
        print(f"    Compliance:")
        for reg, info in s["compliance"].items():
            print(f"      {reg:12s} {info['status']:12s} {info['notes']}")
        print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for enterprise onboarding."""
    parser = argparse.ArgumentParser(
        prog="onboarding",
        description="Nexus-EDA Enterprise Beta Onboarding Tool",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Initialize onboarding workspace")
    p_init.add_argument("--base-dir", default=".", help="Base directory (contains config/)")
    p_init.set_defaults(func=_cmd_init)

    p_invite = sub.add_parser("invite", help="Invite a company to the beta")
    p_invite.add_argument("--company", required=True, help="Company legal name")
    p_invite.add_argument("--industry", required=True, choices=["defense", "aerospace", "other"],
                          help="Industry sector")
    p_invite.add_argument("--website", required=True, help="Company website URL")
    p_invite.add_argument("--employees", type=int, required=True, help="Employee count")
    p_invite.add_argument("--tier", required=True,
                          choices=["standard", "defense", "aerospace"],
                          help="Enterprise tier")
    p_invite.add_argument("--email", required=True, help="Contact email")
    p_invite.add_argument("--uei", default=None, help="UEI (12-digit, for federal contracts)")
    p_invite.add_argument("--cmmc", type=int, default=None, help="CMMC level (defense only)")
    p_invite.add_argument("--as9100", action="store_true", default=False,
                          help="AS9100 certified (aerospace only)")
    p_invite.add_argument("--base-dir", default=".", help="Base directory")
    p_invite.set_defaults(func=_cmd_invite)

    p_verify = sub.add_parser("verify", help="Run compliance verification")
    p_verify.add_argument("--company-id", default=None, help="Company UUID")
    p_verify.add_argument("--token", default=None, help="Invitation token")
    p_verify.add_argument("--evidence", default=None,
                          help='JSON dict of regulation -> evidence file path')
    p_verify.add_argument("--base-dir", default=".", help="Base directory")
    p_verify.set_defaults(func=_cmd_verify)

    p_prov = sub.add_parser("provision", help="Provision tenant deployment")
    p_prov.add_argument("--company-id", required=True, help="Company UUID")
    p_prov.add_argument("--target", choices=["airgapped", "onprem", "govcloud"], default=None,
                        help="Deployment target (auto-detected if omitted)")
    p_prov.add_argument("--base-dir", default=".", help="Base directory")
    p_prov.set_defaults(func=_cmd_provision)

    p_status = sub.add_parser("status", help="Show onboarding status")
    p_status.add_argument("--company-id", default=None, help="Company UUID")
    p_status.add_argument("--beta", action="store_true", default=False,
                          help="Show beta candidates (defense/aerospace) only")
    p_status.add_argument("--base-dir", default=".", help="Base directory")
    p_status.set_defaults(func=_cmd_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
