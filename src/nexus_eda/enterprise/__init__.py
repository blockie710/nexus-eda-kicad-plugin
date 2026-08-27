# SPDX-License-Identifier: Apache-2.0
"""Enterprise onboarding and compliance module for Nexus-EDA.

Provides beta enterprise onboarding workflows for defense and aerospace
companies, including ITAR/GDPR compliance verification, tenant provisioning,
and deployment packaging for the sovereign (self-hosted) Enterprise tier.

Submodules:
    - :mod:`nexus_eda.enterprise.profiles` -- company data models and database
    - :mod:`nexus_eda.enterprise.onboarding` -- CLI tool for beta onboarding
    - :mod:`nexus_eda.enterprise.packaging` -- deployment package generation
"""

from .profiles import (
    CompanyProfile,
    ComplianceStatus,
    EnterpriseTier,
    OnboardingStatus,
    CompanyDatabase,
    determine_required_compliance,
    validate_company_input,
)
from .onboarding import (
    OnboardingWizard,
    Invitation,
    InvitationStore,
    DeploymentConfig,
    ComplianceResult,
    verify_compliance,
    update_compliance_status,
    determine_deployment_target,
    determine_model_assignment,
    provision_tenant,
)
from .packaging import (
    DeploymentPackage,
    PackageArtifact,
    build_airgap_tarball,
    generate_deployment_summary,
)

__all__ = [
    # profiles
    "CompanyProfile",
    "ComplianceStatus",
    "EnterpriseTier",
    "OnboardingStatus",
    "CompanyDatabase",
    "determine_required_compliance",
    "validate_company_input",
    # onboarding
    "OnboardingWizard",
    "Invitation",
    "InvitationStore",
    "DeploymentConfig",
    "ComplianceResult",
    "verify_compliance",
    "update_compliance_status",
    "determine_deployment_target",
    "determine_model_assignment",
    "provision_tenant",
    # packaging
    "DeploymentPackage",
    "PackageArtifact",
    "build_airgap_tarball",
    "generate_deployment_summary",
]
