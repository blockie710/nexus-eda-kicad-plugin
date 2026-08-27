# SPDX-License-Identifier: Apache-2.0
"""Unit tests for Nexus-EDA enterprise onboarding module.

Tests the core onboarding workflow:
- Company profile creation and validation
- Invitation generation and redemption
- Compliance verification (ITAR, EAR, GDPR, CMMC, AS9100)
- Tenant provisioning and deployment configuration
- Air-gap bundle generation
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from nexus_eda.enterprise import (
    CompanyDatabase,
    CompanyProfile,
    ComplianceResult,
    ComplianceStatus,
    DeploymentConfig,
    EnterpriseTier,
    Invitation,
    InvitationStore,
    OnboardingStatus,
    OnboardingWizard,
    determine_required_compliance,
    validate_company_input,
    verify_compliance,
    update_compliance_status,
    provision_tenant,
    build_airgap_tarball,
    generate_deployment_summary,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def sample_company_data():
    return {
        "name": "Defense Dynamics Inc",
        "industry": "defense",
        "website": "https://defensedynamics.example.com",
        "employee_count": 75,
        "tier": EnterpriseTier.DEFENSE,
        "contact_email": "security@defensedynamics.example.com",
        "uei": "123456789012",
        "cmmc_level": 3,
        "as9100_certified": False,
    }


@pytest.fixture
def sample_aerospace_data():
    return {
        "name": "AeroSpace Systems Ltd",
        "industry": "aerospace",
        "website": "https://aerosystems.example.co.uk",
        "employee_count": 150,
        "tier": EnterpriseTier.AEROSPACE,
        "contact_email": "compliance@aerosystems.example.co.uk",
        "uei": "987654321098",
        "cmmc_level": None,
        "as9100_certified": True,
    }


@pytest.fixture
def wizard(temp_dir):
    return OnboardingWizard(
        db_path=temp_dir / "companies.json",
        invitations_path=temp_dir / "invitations.json",
        deployments_path=temp_dir / "deployments.json",
    )


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_company_profile_creation(sample_company_data):
    """Test creating a company profile."""
    profile = CompanyProfile.create(**sample_company_data)

    assert profile.name == sample_company_data["name"]
    assert profile.industry == sample_company_data["industry"]
    assert profile.tier == sample_company_data["tier"]
    assert profile.onboarding_status == OnboardingStatus.INVITED
    assert profile.employee_count == sample_company_data["employee_count"]
    assert profile.contact_email == sample_company_data["contact_email"]
    assert profile.uei == sample_company_data["uei"]
    assert profile.cmmc_level == sample_company_data["cmmc_level"]
    assert profile.as9100_certified == sample_company_data["as9100_certified"]

    # Check computed properties
    assert profile.is_defense is True
    assert profile.is_aerospace is False
    assert profile.is_beta_candidate is True
    assert profile.tier.monthly_price_usd == 7500.0
    assert profile.tier.max_engineers == 100
    assert profile.tier.requires_cma is True


def test_company_profile_serialization(sample_company_data):
    """Test to_dict/from_dict roundtrip."""
    original = CompanyProfile.create(**sample_company_data)
    data = original.to_dict()
    restored = CompanyProfile.from_dict(data)

    assert restored.id == original.id
    assert restored.name == original.name
    assert restored.industry == original.industry
    assert restored.tier == original.tier
    assert restored.onboarding_status == original.onboarding_status
    assert restored.contact_email == original.contact_email
    assert restored.uei == original.uei
    assert restored.cmmc_level == original.cmmc_level
    assert restored.as9100_certified == original.as9100_certified
    assert restored.created_at == original.created_at
    assert restored.updated_at == original.updated_at


def test_validate_company_input():
    """Test input validation."""
    # Valid input
    errors = validate_company_input(
        name="Test Corp",
        website="https://test.example.com",
        employee_count=50,
        contact_email="test@example.com",
        industry="defense",
    )
    assert errors == []

    # Invalid name
    errors = validate_company_input(
        name="A",  # too short
        website="https://test.example.com",
        employee_count=50,
        contact_email="test@example.com",
        industry="defense",
    )
    assert any("at least 2 characters" in e for e in errors)

    # Invalid website
    errors = validate_company_input(
        name="Test Corp",
        website="not-a-url",
        employee_count=50,
        contact_email="test@example.com",
        industry="defense",
    )
    assert any("Invalid website URL" in e for e in errors)

    # Invalid employee count
    errors = validate_company_input(
        name="Test Corp",
        website="https://test.example.com",
        employee_count=0,
        contact_email="test@example.com",
        industry="defense",
    )
    assert any(">= 1" in e for e in errors)

    # Invalid email
    errors = validate_company_input(
        name="Test Corp",
        website="https://test.example.com",
        employee_count=50,
        contact_email="not-an-email",
        industry="defense",
    )
    assert any("Invalid contact email" in e for e in errors)

    # Invalid industry
    errors = validate_company_input(
        name="Test Corp",
        website="https://test.example.com",
        employee_count=50,
        contact_email="test@example.com",
        industry="invalid",
    )
    assert any("must be" in e for e in errors)

    # Invalid UEI
    errors = validate_company_input(
        name="Test Corp",
        website="https://test.example.com",
        employee_count=50,
        contact_email="test@example.com",
        industry="defense",
        uei="12345",  # not 12 digits
    )
    assert any("12-digit number" in e for e in errors)


def test_company_database(temp_dir):
    """Test JSON-backed company database."""
    db = CompanyDatabase(temp_dir / "companies.json")

    # Start empty
    assert db.count == 0
    assert db.list_all() == []

    # Add a company
    profile = CompanyProfile.create(
        name="Test Corp",
        industry="defense",
        website="https://test.example.com",
        employee_count=50,
        tier=EnterpriseTier.DEFENSE,
        contact_email="test@example.com",
    )
    db.add(profile)

    assert db.count == 1
    retrieved = db.get(profile.id)
    assert retrieved is not None
    assert retrieved.name == "Test Corp"
    assert retrieved.onboarding_status == OnboardingStatus.INVITED

    # Update status
    retrieved.onboarding_status = OnboardingStatus.ACCEPTED
    db.update(retrieved)

    updated = db.get(profile.id)
    assert updated.onboarding_status == OnboardingStatus.ACCEPTED
    assert updated.updated_at >= updated.created_at  # updated_at should change

    # Remove company
    assert db.remove(profile.id) is True
    assert db.get(profile.id) is None
    assert db.count == 0

    # Removing non-existent returns False
    assert db.remove("non-existent") is False

    # List by status
    p1 = CompanyProfile.create(
        name="Corp A", industry="defense", website="https://a.example.com",
        employee_count=10, tier=EnterpriseTier.STANDARD, contact_email="a@example.com"
    )
    p2 = CompanyProfile.create(
        name="Corp B", industry="aerospace", website="https://b.example.com",
        employee_count=20, tier=EnterpriseTier.AEROSPACE, contact_email="b@example.com"
    )
    p1.onboarding_status = OnboardingStatus.ACTIVE
    p2.onboarding_status = OnboardingStatus.INVITED

    db.add(p1)
    db.add(p2)

    assert len(db.list_by_status(OnboardingStatus.ACTIVE)) == 1
    assert len(db.list_by_status(OnboardingStatus.INVITED)) == 1
    assert len(db.list_beta_candidates()) == 2  # both defense and aerospace
    assert len(db.list_active()) == 1


def test_invitation_store(temp_dir):
    """Test invitation generation and redemption."""
    store = InvitationStore(temp_dir / "invitations.json")

    # Create invitation
    company_id = "test-company-id"
    inv = store.create(company_id, expiry_days=7)

    assert inv.company_id == company_id
    assert len(inv.token) >= 32  # secrets.token_urlsafe(32) yields ~43 chars
    assert not inv.used
    assert inv.is_valid() is True
    assert inv.is_expired() is False

    # Store persistence
    store2 = InvitationStore(temp_dir / "invitations.json")
    inv2 = store2.get(inv.token)
    assert inv2 is not None
    assert inv2.token == inv.token
    assert inv2.company_id == company_id

    # Redeem invitation
    redeemed = store.redeem(inv.token)
    assert redeemed is not None
    assert redeemed.used is True
    assert redeemed.is_valid() is False  # used = invalid

    # Trying to redeem again returns None
    assert store.redeem(inv.token) is None

    # Expired invitation
    expired_inv = store.create("expired", expiry_days=-1)  # already expired
    assert expired_inv.is_valid() is False
    assert expired_inv.is_expired() is True

    # Cleanup
    removed = store.cleanup_expired()
    assert removed >= 1  # at least the expired one
    assert store.get(expired_inv.token) is None


def test_determine_required_compliance():
    """Test compliance determination logic."""
    # Standard tier (no CMA/AS9100)
    std_profile = CompanyProfile.create(
        name="Std Corp",
        industry="other",
        website="https://std.example.com",
        employee_count=5,
        tier=EnterpriseTier.STANDARD,
        contact_email="std@example.com",
    )
    assert determine_required_compliance(std_profile) == []  # not EU-facing

    # Make it EU-facing
    std_profile_eu = CompanyProfile.create(
        name="Std Corp EU",
        industry="other",
        website="https://std.example.de",  # .de TLD
        employee_count=5,
        tier=EnterpriseTier.STANDARD,
        contact_email="std@example.de",
    )
    assert determine_required_compliance(std_profile_eu) == ["gdpr"]

    # Defense tier
    def_profile = CompanyProfile.create(
        name="Def Corp",
        industry="defense",
        website="https://def.example.com",
        employee_count=50,
        tier=EnterpriseTier.DEFENSE,
        contact_email="def@example.com",
        cmmc_level=3,
    )
    regs = determine_required_compliance(def_profile)
    assert "itar" in regs
    assert "cmmc" in regs  # DEFENSE tier requires CMMC
    assert "ear" in regs
    # Not EU-facing by default
    assert "gdpr" not in regs

    # Aerospace tier
    aero_profile = CompanyProfile.create(
        name="Aero Corp",
        industry="aerospace",
        website="https://aero.example.com",
        employee_count=200,
        tier=EnterpriseTier.AEROSPACE,
        contact_email="aero@example.com",
        as9100_certified=True,
    )
    regs = determine_required_compliance(aero_profile)
    assert "itar" in regs
    assert "as9100" in regs  # AEROSPACE requires AS9100
    assert "cmmc" in regs  # AEROSPACE tier also requires CMMC
    assert "ear" in regs

    # EU-facing defense
    def_eu = CompanyProfile.create(
        name="Def Corp EU",
        industry="defense",
        website="https://def.example.fr",
        employee_count=30,
        tier=EnterpriseTier.DEFENSE,
        contact_email="def@example.fr",
        cmmc_level=2,
    )
    regs = determine_required_compliance(def_eu)
    assert "gdpr" in regs  # EU-facing adds GDPR
    assert "itar" in regs
    assert "cmmc" in regs
    assert "ear" in regs


def test_onboarding_wizard_add_and_invite(temp_dir, sample_company_data):
    """Test the full add_company -> invite workflow."""
    wizard = OnboardingWizard(
        db_path=temp_dir / "companies.json",
        invitations_path=temp_dir / "invitations.json",
    )

    # Add company and generate invite
    profile, invite = wizard.add_company(**sample_company_data)

    # Check company was added to DB
    db_profile = wizard.db.get(profile.id)
    assert db_profile is not None
    assert db_profile.name == sample_company_data["name"]
    assert db_profile.onboarding_status == OnboardingStatus.INVITED
    assert db_profile.tier == EnterpriseTier.DEFENSE

    # Check invitation was created
    assert invite.company_id == profile.id
    assert not invite.used
    assert invite.is_valid() is True

    # Accept invitation
    accepted_profile = wizard.accept_invitation(invite.token)
    assert accepted_profile.id == profile.id
    assert accepted_profile.onboarding_status == OnboardingStatus.ACCEPTED
    assert invite.used is True  # invitation store updated

    # Trying to accept again should fail
    with pytest.raises(ValueError, match="already been used"):
        wizard.accept_invitation(invite.token)

    # Test invalid token
    with pytest.raises(ValueError, match="Invalid invitation token"):
        wizard.accept_invitation("invalid-token")

    # Test expired token
    expired_inv = wizard.invitations.create(profile.id, expiry_days=-1)
    with pytest.raises(ValueError, match="expired"):
        wizard.accept_invitation(expired_inv.token)


def test_compliance_verification(temp_dir, sample_company_data, sample_aerospace_data):
    """Test compliance verification workflow."""
    wizard = OnboardingWizard(
        db_path=temp_dir / "companies.json",
        invitations_path=temp_dir / "invitations.json",
    )

    # Add defense company
    profile, _ = wizard.add_company(**sample_company_data)
    assert profile.onboarding_status == OnboardingStatus.INVITED

    # Accept invite
    wizard.accept_invitation(
        wizard.invitations.list_valid()[0].token
    )  # get the valid invite we just made

    # Verify compliance (no evidence provided)
    results = wizard.run_compliance_check(profile.id)
    assert profile.onboarding_status == OnboardingStatus.COMPLIANCE_CHECK

    # Should have ITAR, EAR, CMMC (DEFENSE tier)
    expected = {"itar", "ear", "cmmc"}
    assert set(results.keys()) == expected

    # All should be FAIL (no evidence)
    for reg, result in results.items():
        assert result.passed is False
        assert result.evidence_provided is False
        assert "Evidence not yet provided" in result.notes

    # Update compliance status from results
    update_compliance_status(profile, results)
    # Profile should now have compliance entries
    assert "itar" in profile.compliance
    assert profile.compliance["itar"].status == "non_compliant"
    assert profile.compliance["cmmc"].status == "non_compliant"
    assert profile.compliance["ear"].status == "non_compliant"

    # Now provide fake evidence and re-verify
    evidence = {
        "itar": "fake evidence with ITAR and DD-254 mentioned",
        "ear": "fake evidence with EAR mentioned",
        "cmmc": "fake evidence with CMMC Level 3 mentioned",
    }
    results2 = wizard.run_compliance_check(profile.id, evidence)

    # Now they should PASS
    for reg in expected:
        assert results2[reg].passed is True
        assert results2[reg].evidence_provided is True
        assert "verified" in results2[reg].notes.lower()

    # Check that profile compliance was updated
    assert profile.compliance["itar"].status == "compliant"
    assert profile.compliance["itar"].verified_at is not None

    # Test aerospace company
    aero_profile, _ = wizard.add_company(**sample_aerospace_data)
    wizard.accept_invitation(wizard.invitations.list_valid()[-1].token)  # latest invite

    aero_results = wizard.run_compliance_check(aero_profile.id, {
        "itar": "ITAR compliance evidence",
        "as9100": "AS9100 certificate attached",
        "cmmc": "CMMC Level 3 assessment",  # AEROSPACE also needs CMMC
    })
    assert aero_results["as9100"].passed is True  # key is as9100
    assert aero_results["itar"].passed is True
    assert aero_results["cmmc"].passed is True


def test_provisioning_workflow(temp_dir, sample_company_data):
    """Test tenant provisioning after compliance passes."""
    wizard = OnboardingWizard(
        db_path=temp_dir / "companies.json",
        invitations_path=temp_dir / "invitations.json",
        deployments_path=temp_dir / "deployments.json",
    )

    # Add and invite
    profile, invite = wizard.add_company(**sample_company_data)
    wizard.accept_invitation(invite.token)

    # Run and pass compliance
    evidence = {
        "itar": "DD-254 form present",
        "ear": "EAR compliance documentation",
        "cmmc": "CMMC Level 3 assessment report",
    }
    wizard.run_compliance_check(profile.id, evidence)
    update_compliance_status(profile, verify_compliance(profile, evidence))

    # Provision tenant (should default to airgapped for DEFENSE)
    config = wizard.provision_company(profile.id)
    assert config.company_id == profile.id
    assert config.deployment_target == "airgapped"  # DEFENSE tier -> airgapped
    assert config.tier == EnterpriseTier.DEFENSE
    assert config.sso_enabled is True  # requires CMA
    assert config.model_assignment == "nexus-llm"  # DEFENSE tier
    assert config.max_concurrent_agents == 4  # CMA -> 4 agents
    assert config.storage_quota_gb == 500  # CMA -> 500GB
    assert "itar" in config.compliance_profile
    assert "ear" in config.compliance_profile
    assert "cmmc" in config.compliance_profile

    # Check that company profile was updated
    updated = wizard.db.get(profile.id)
    assert updated.onboarding_status == OnboardingStatus.ACTIVE
    assert updated.tenant_id == config.tenant_id
    assert updated.deployment_target == config.deployment_target

    # Test provisioning fails if compliance not complete
    std_profile, _ = wizard.add_company(
        name="Std Corp",
        industry="other",
        website="https://std.example.com",
        employee_count=10,
        tier=EnterpriseTier.STANDARD,
        contact_email="std@example.com",
    )
    wizard.accept_invitation(wizard.invitations.list_valid()[-1].token)
    # Do NOT run compliance - should fail
    with pytest.raises(ValueError, match="not passed"):
        wizard.provision_company(std_profile.id)

    # Test explicit target override
    config_override = wizard.provision_company(profile.id, target="onprem")
    assert config_override.deployment_target == "onprem"
    assert config_override.sso_enabled is True  # still from tier
    assert config_override.model_assignment == "nexus-llm"


def test_deployment_package_generation(temp_dir, sample_company_data):
    """Test air-gap tarball generation."""
    wizard = OnboardingWizard(
        db_path=temp_dir / "companies.json",
        invitations_path=temp_dir / "invitations.json",
    )

    # Setup company through to active
    profile, invite = wizard.add_company(**sample_company_data)
    wizard.accept_invitation(invite.token)
    evidence = {
        "itar": "DD-254",
        "ear": "EAR docs",
        "cmmc": "CMMC Level 3",
    }
    wizard.run_compliance_check(profile.id, evidence)
    update_compliance_status(profile, verify_compliance(profile, evidence))
    config = wizard.provision_company(profile.id)

    # Generate deployment package
    pkg_dir = temp_dir / "packages"
    tarball = build_airgap_tarball(config, profile, pkg_dir)

    assert tarball.exists()
    assert tarball.name.endswith(".tar.gz")
    assert "defense-dynamics-inc" in tarball.name.lower()

    # Check tarball contents
    import tarfile
    with tarfile.open(tarball, "r:gz") as tf:
        members = tf.getnames()
        assert any("deployment.json" in m for m in members)
        assert any("docker-compose.airgapped.yml" in m for m in members)
        assert any("audit-trail.json" in m for m in members)
        assert any("ENCRYPTION.md" in m for m in members)
        assert any("SHA256SUMS" in m for m in members)
        # Models are NOT included in the tarball (shipped separately)
        assert not any(".gguf" in m for m in members)

    # Check deployment summary
    summary = generate_deployment_summary(config, profile)
    assert "Defense Dynamics Inc" in summary
    assert "DEFENSE" in summary
    assert "$7,500" in summary  # monthly price formatted
    assert "airgapped" in summary
    assert "AES-256" in summary
    assert "SABLE-inspired" in summary
    assert "28 functions" in summary  # scoped entry points count


def test_wizard_status_reporting(temp_dir, sample_company_data, sample_aerospace_data):
    """Test status reporting methods."""
    wizard = OnboardingWizard(
        db_path=temp_dir / "companies.json",
        invitations_path=temp_dir / "invitations.json",
    )

    # Add a few companies in different states
    defense_profile, defense_invite = wizard.add_company(**sample_company_data)
    aero_profile, aero_invite = wizard.add_company(**sample_aerospace_data)

    # Accept defense invite
    wizard.accept_invitation(defense_invite.token)
    # Leave aerospace as INVITED

    # Run compliance on defense (but don't update to compliant)
    defense_profile = wizard.db.get(defense_profile.id)
    update_compliance_status(defense_profile, verify_compliance(defense_profile, {
        "itar": "fake ITAR evidence",
        "ear": "fake EAR evidence",
        "cmmc": "fake CMMC evidence",
    }))
    wizard.db.update(defense_profile)

    # Check status lists
    all_status = wizard.list_all_status()
    assert len(all_status) == 2

    beta_status = wizard.list_beta_companies()
    assert len(beta_status) == 2  # both defense and aerospace are beta candidates

    # Find each in the list
    defense_status = next(s for s in all_status if s["name"] == "Defense Dynamics Inc")
    aero_status = next(s for s in all_status if s["name"] == "AeroSpace Systems Ltd")

    assert defense_status["onboarding_status"] == "accepted"
    assert defense_status["compliance"]["itar"]["status"] == "compliant"
    assert aero_status["onboarding_status"] == "invited"
    assert len(aero_status["compliance"]) == 0  # never ran compliance

    # Test specific company status
    specific = wizard.get_company_status(defense_profile.id)
    assert specific["name"] == "Defense Dynamics Inc"
    assert specific["tenant_id"] is None  # not provisioned yet
    assert specific["onboarding_status"] == "accepted"

    # Test non-existent company
    not_found = wizard.get_company_status("non-existent-id")
    assert "error" in not_found
    assert "not found" in not_found["error"].lower()


def test_cli_integration(temp_dir):
    """Test the CLI entry point."""
    from nexus_eda.enterprise.onboarding import main

    base = temp_dir
    (base / "config").mkdir()

    # Init
    assert main(["init", "--base-dir", str(base)]) == 0
    assert (base / "config" / "companies.json").exists()
    assert (base / "config" / "invitations.json").exists()
    assert (base / "config" / "deployments.json").exists()

    # Invite a defense company
    assert main([
        "invite",
        "--company", "Test Defense Corp",
        "--industry", "defense",
        "--website", "https://testdef.example.com",
        "--employees", "42",
        "--tier", "defense",
        "--email", "sec@testdef.example.com",
        "--uei", "123456789012",
        "--cmmc", "3",
        "--base-dir", str(base),
    ]) == 0

    # Grab the token from the invitations file
    inv_file = base / "config" / "invitations.json"
    data = json.loads(inv_file.read_text())
    token = data["invitations"][0]["token"]

    # Verify compliance (should fail - no evidence)
    assert main([
        "verify",
        "--token", token,
        "--base-dir", str(base),
    ]) != 0  # non-zero exit code because checks fail

    # Verify with fake evidence
    evidence_json = json.dumps({
        "itar": "DD-254 form with ITAR clause",
        "ear": "EAR compliance matrix",
        "cmmc": "CMMC Level 3 assessment report",
    })
    assert main([
        "verify",
        "--token", token,
        "--evidence", evidence_json,
        "--base-dir", str(base),
    ]) == 0  # should pass

    # Provision
    company_id = data["invitations"][0]["company_id"]
    assert main([
        "provision",
        "--company-id", company_id,
        "--base-dir", str(base),
    ]) == 0

    # Status
    assert main(["status", "--base-dir", str(base)]) == 0
    assert main(["status", "--beta", "--base-dir", str(base)]) == 0
    assert main([
        "status",
        "--company-id", company_id,
        "--base-dir", str(base),
    ]) == 0

    # Test invalid commands
    assert main(["invalid"]) != 0
    assert main(["invite"]) != 0  # missing required args


# --------------------------------------------------------------------------- #
# Property-like tests
# --------------------------------------------------------------------------- #
def test_enterprise_tier_properties():
    """Test EnterpriseTier computed properties."""
    assert EnterpriseTier.STANDARD.monthly_price_usd == 2500.0
    assert EnterpriseTier.DEFENSE.monthly_price_usd == 7500.0
    assert EnterpriseTier.AEROSPACE.monthly_price_usd == 15000.0

    assert EnterpriseTier.STANDARD.max_engineers == 10
    assert EnterpriseTier.DEFENSE.max_engineers == 100
    assert EnterpriseTier.AEROSPACE.max_engineers == 1000

    assert EnterpriseTier.STANDARD.requires_cma is False
    assert EnterpriseTier.DEFENSE.requires_cma is True
    assert EnterpriseTier.AEROSPACE.requires_cma is True

    assert EnterpriseTier.STANDARD.requires_as9100 is False
    assert EnterpriseTier.DEFENSE.requires_as9100 is False
    assert EnterpriseTier.AEROSPACE.requires_as9100 is True

    assert EnterpriseTier.STANDARD.value == "standard"
    assert EnterpriseTier.DEFENSE.value == "defense"
    assert EnterpriseTier.AEROSPACE.value == "aerospace"


def test_onboarding_status_values():
    """Test OnboardingStatus enum values."""
    assert OnboardingStatus.INVITED.value == "invited"
    assert OnboardingStatus.ACCEPTED.value == "accepted"
    assert OnboardingStatus.COMPLIANCE_CHECK.value == "compliance_check"
    assert OnboardingStatus.PROVISIONING.value == "provisioning"
    assert OnboardingStatus.ACTIVE.value == "active"
    assert OnboardingStatus.REJECTED.value == "rejected"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])