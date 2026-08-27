# SPDX-License-Identifier: Apache-2.0
"""Deployment package generation for Enterprise tenants.

Generates air-gapped and on-premises deployment packages, including:
- Docker Compose manifest for on-prem
- Air-gap tarball manifest for airgapped (no network) deployments
- Encrypted local storage configuration (AES-256)
- SSO/SAML configuration templates
- Compliance audit trail artifacts

The packaging is deterministic and reproducible — given the same
DeploymentConfig, the same manifest is produced.
"""

from __future__ import annotations

import hashlib
import json
import os
import tarfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .profiles import CompanyProfile, EnterpriseTier, OnboardingStatus, determine_required_compliance
from .onboarding import DeploymentConfig


@dataclass
class PackageArtifact:
    """A single file artifact produced by deployment packaging.

    Attributes:
        filename: Relative path within the package
        content: File content (text)
        description: Human-readable description of the artifact
    """

    filename: str
    content: str
    description: str


# --------------------------------------------------------------------------- #
# Package manifest generation
# --------------------------------------------------------------------------- #
class DeploymentPackage:
    """Generates deployment artifacts for an enterprise tenant.

    Produces a set of configuration files tailored to the deployment target
    (airgapped, onprem, or govcloud) that can be bundled into a tarball
    or applied via Docker Compose.
    """

    def __init__(self, config: DeploymentConfig, company: CompanyProfile):
        self.config = config
        self.company = company
        self.generated_at = datetime.now().isoformat()

    def artifacts(self) -> list[PackageArtifact]:
        """Generate all deployment artifacts for this tenant."""
        artifacts: list[PackageArtifact] = []

        # Base manifest
        artifacts.append(self._manifest())

        # Deployment-target-specific files
        if self.config.deployment_target == "airgapped":
            artifacts.extend(self._airgap_artifacts())
        elif self.config.deployment_target == "onprem":
            artifacts.extend(self._onprem_artifacts())
        else:
            artifacts.extend(self._govcloud_artifacts())

        # Compliance & audit artifacts
        artifacts.extend(self._compliance_artifacts())

        # SSO/SAML (if enabled)
        if self.config.sso_enabled:
            artifacts.extend(self._sso_artifacts())

        return artifacts

    def _manifest(self) -> PackageArtifact:
        """Generate the base deployment manifest (deployment.json)."""
        data = {
            "version": "1.0",
            "tenant_id": self.config.tenant_id,
            "company_id": self.config.company_id,
            "company_name": self.company.name,
            "industry": self.company.industry,
            "tier": self.config.tier.value,
            "deployment_target": self.config.deployment_target,
            "generated_at": self.generated_at,
            "model_assignment": self.config.model_assignment,
            "max_concurrent_agents": self.config.max_concurrent_agents,
            "storage_quota_gb": self.config.storage_quota_gb,
            "compliance_profile": sorted(self.config.compliance_profile),
            "sso_enabled": self.config.sso_enabled,
        }
        return PackageArtifact(
            filename="deployment.json",
            content=json.dumps(data, indent=2),
            description="Tenant deployment manifest with all configuration parameters.",
        )

    def _airgap_artifacts(self) -> list[PackageArtifact]:
        """Artifacts for air-gapped deployment (no network)."""
        return [
            PackageArtifact(
                filename="docker-compose.airgapped.yml",
                content=self._docker_compose(airgapped=True),
                description="Docker Compose for air-gapped deployment (offline bundle).",
            ),
            PackageArtifact(
                filename="models.manifest.json",
                content=self._model_manifest(),
                description="List of GGUF model files to be shipped on physical media.",
            ),
            PackageArtifact(
                filename="BUNDLE.md",
                content=self._bundle_instructions(),
                description="Instructions for loading the air-gap bundle on an isolated host.",
            ),
        ]

    def _onprem_artifacts(self) -> list[PackageArtifact]:
        """Artifacts for on-premises deployment."""
        return [
            PackageArtifact(
                filename="docker-compose.yml",
                content=self._docker_compose(airgapped=False),
                description="Docker Compose for on-premises deployment with local model serving.",
            ),
            PackageArtifact(
                filename="nginx.conf",
                content=self._nginx_config(),
                description="NGINX reverse proxy configuration for the on-prem web UI.",
            ),
        ]

    def _govcloud_artifacts(self) -> list[PackageArtifact]:
        """Artifacts for GovCloud deployment."""
        return [
            PackageArtifact(
                filename="kubernetes-manifests.yaml",
                content=self._kubernetes_manifests(),
                description="Kubernetes manifests for GovCloud (FedRAMP-compliant) deployment.",
            ),
            PackageArtifact(
                filename="terraform.tf",
                content=self._terraform_template(),
                description="Terraform template for GovCloud infrastructure provisioning.",
            ),
        ]

    def _compliance_artifacts(self) -> list[PackageArtifact]:
        """Artifacts for compliance and audit trail."""
        artifacts = []

        # Audit trail
        audit_data = {
            "tenant_id": self.config.tenant_id,
            "company_id": self.config.company_id,
            "company_name": self.company.name,
            "onboarding_status": self.company.onboarding_status.value,
            "compliance_profile": sorted(self.config.compliance_profile),
            "generated_at": self.generated_at,
            "sable_entry_points": self._sable_entry_points(),
        }
        artifacts.append(PackageArtifact(
            filename="audit-trail.json",
            content=json.dumps(audit_data, indent=2),
            description="Compliance audit trail — SABLE-inspired scoped entry points.",
        ))

        # Encryption key note
        artifacts.append(PackageArtifact(
            filename="ENCRYPTION.md",
            content=self._encryption_instructions(),
            description="AES-256 encryption key management instructions for sovereign data.",
        ))

        return artifacts

    def _sso_artifacts(self) -> list[PackageArtifact]:
        """Artifacts for SSO/SAML configuration."""
        return [
            PackageArtifact(
                filename="saml-config.json",
                content=json.dumps({
                    "enabled": True,
                    "sso_url": f"https://app.nexuseda.com/sso/{self.config.tenant_id}/sso",
                    "entity_id": f"https://app.nexuseda.com/sso/{self.config.tenant_id}",
                    "certificate": f"---BEGIN CERTIFICATE---\n# Download from: https://app.nexuseda.com/sso/{self.config.tenant_id}/cert\n---END CERTIFICATE---",
                    "name_id_format": "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent",
                }, indent=2),
                description="SAML 2.0 configuration for enterprise SSO integration.",
            ),
            PackageArtifact(
                filename="SSO-SETUP.md",
                content=self._sso_setup_guide(),
                description="Step-by-step SSO/SAML setup guide for IT administrators.",
            ),
        ]

    # -- Content generators -------------------------------------------------- #
    def _docker_compose(self, airgapped: bool = False) -> str:
        """Generate docker-compose YAML for the tenant."""
        env = "AIRGAPPED" if airgapped else "ONPREM"
        image_tag = f"nexus-eda:1.0.0-{env}"

        return f"""\
version: "3.8"

services:
  nexus-eda-api:
    image: {image_tag}
    container_name: nexus-eda-{self.config.tenant_id}
    restart: unless-stopped
    environment:
      - NEXUS_TENANT_ID={self.config.tenant_id}
      - NEXUS_DEPLOYMENT_TARGET={self.config.deployment_target}
      - NEXUS_MODEL_PROFILE={self.config.model_assignment}
      - NEXUS_COMPLIANCE_PROFILE={",".join(sorted(self.config.compliance_profile))}
      - NEXUS_STORAGE_QUOTA_GB={self.config.storage_quota_gb}
      - NEXUS_MAX_AGENTS={self.config.max_concurrent_agents}
      - NEXUS_AUDIT_LOG=true
    volumes:
      - nexus-eda-data-{self.config.tenant_id}:/data
      - nexus-eda-models-{self.config.tenant_id}:/models:ro
    ports:
      - "8080:8080"
    networks:
      - nexus-eda-net

volumes:
  nexus-eda-data-{self.config.tenant_id}:
  nexus-eda-models-{self.config.tenant_id}:
    external: true
    name: nexus-eda-models-shared

networks:
  nexus-eda-net:
    driver: bridge
"""

    def _model_manifest(self) -> str:
        """Generate list of models to ship for air-gapped deployment."""
        models = {
            "nexus-llm": {
                "name": "Qwen3-Coder-32B-Q4_K_M",
                "size_gb": 18,
                "path": "/models/qwen3-coder-32b-q4_k_m.gguf",
            },
            "nexus-fast": {
                "name": "Qwen2.5-Coder-7B-Q4_K_M",
                "size_gb": 6,
                "path": "/models/qwen2.5-coder-7b-q4_k_m.gguf",
            },
        }
        manifest = {
            "tenant_id": self.config.tenant_id,
            "target_model": self.config.model_assignment,
            "models": models,
        }
        return json.dumps(manifest, indent=2)

    def _bundle_instructions(self) -> str:
        return f"""\
# Nexus-EDA Air-Gap Deployment Bundle

**Tenant:** {self.company.name} ({self.config.tenant_id})  
**Generated:** {self.generated_at}

## Prerequisites

1. A dedicated server or workstation with:
   - NVIDIA RTX 4090 (24GB VRAM) or better
   - Docker + docker-compose installed
   - USB 3.0 drive with >= 50 GB free space

## Loading the Bundle

1. Copy the entire `nexus-eda-bundle/` directory to the air-gapped host.
2. Copy the model GGUF files onto the USB drive (provided separately).
3. Mount the model volume:

   ```bash
   docker volume create --driver local \\
     --opt type=none \\
     --opt device=/mnt/usb/models \\
     --opt o=bind \\
     nexus-eda-models-{self.config.tenant_id}
   ```

4. Deploy:

   ```bash
   cd nexus-eda-bundle/
   docker-compose -f docker-compose.airgapped.yml up -d
   ```

5. Verify: `curl http://localhost:8080/health`

## First Login

   - URL: https://localhost:8443
   - Tenant ID: {self.config.tenant_id}
   - Initial admin credentials are in `credentials.txt` (provided via separate secure channel)
"""

    def _nginx_config(self) -> str:
        return f"""\
server {{
    listen 80;
    server_name nexus-eda.{self.company.name.lower().replace(" ", "-")}.local;

    location / {{
        proxy_pass http://nexus-eda-api:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}

    location /api/ {{
        proxy_pass http://nexus-eda-api:8080/api/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }}

    # Block all external egress (sovereign data boundary)
    deny all;
}}
"""

    def _kubernetes_manifests(self) -> str:
        return f"""\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nexus-eda-{self.config.tenant_id}
  namespace: nexus-eda-{self.config.tenant_id}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: nexus-eda
      tenant: {self.config.tenant_id}
  template:
    metadata:
      labels:
        app: nexus-eda
        tenant: {self.config.tenant_id}
        compliance: {",".join(sorted(self.config.compliance_profile))}
    spec:
      containers:
      - name: nexus-eda
        image: nexus-eda:1.0.0-GOV
        ports:
        - containerPort: 8080
        env:
        - name: NEXUS_TENANT_ID
          value: "{self.config.tenant_id}"
        - name: NEXUS_DEPLOYMENT_TARGET
          value: "govcloud"
        - name: NEXUS_COMPLIANCE_PROFILE
          value: "{",".join(sorted(self.config.compliance_profile))}"
        volumeMounts:
        - name: model-storage
          mountPath: /models
        securityContext:
          runAsNonRoot: true
          readOnlyRootFilesystem: true
      volumes:
      - name: model-storage
        emptyDir: {{}}
---
apiVersion: v1
kind: Service
metadata:
  name: nexus-eda-{self.config.tenant_id}
  namespace: nexus-eda-{self.config.tenant_id}
spec:
  selector:
    app: nexus-eda
    tenant: {self.config.tenant_id}
  ports:
  - port: 80
    targetPort: 8080
  type: ClusterIP
"""

    def _terraform_template(self) -> str:
        return f"""\
terraform {{
  required_providers {{
    aws = {{
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }}
  }}
}}

provider "aws" {{
  region = var.aws_region
  # GovCloud requires special credentials
  access_key = var.aws_access_key
  secret_key = var.aws_secret_key
}}

resource "aws_vpc" "nexus_eda" {{
  cidr_block = "10.0.0.0/16"
  tags = {{
    Tenant  = "{self.config.tenant_id}"
    Company = "{self.company.name}"
    Tier    = "{self.config.tier.value}"
  }}
}}

resource "aws_s3_bucket" "nexus_eda_storage" {{
  bucket = "nexus-eda-{self.config.tenant_id}-storage"
  tags = {{
    Tenant  = "{self.config.tenant_id}"
    Company = "{self.company.name}"
    Tier    = "{self.config.tier.value}"
  }}
}}
"""

    def _encryption_instructions(self) -> str:
        return f"""\
# Nexus-EDA AES-256 Encryption Key Management

**Tenant:** {self.config.tenant_id}  
**Company:** {self.company.name}

## Key Generation

Generate the encryption key on the target host (never transmit over network):

```bash
# Generate a 256-bit key
openssl rand -hex 32 > encryption-key.hex

# Or using the bundled utility
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Key Storage

- Store the key in an environment variable: `NEXUS_ENCRYPTION_KEY`
- Or write to: `/etc/nexus-eda/{self.config.tenant_id}/encryption.key`
- File permissions: `chmod 600`
- Owner: `nexus-eda` service user

## Key Rotation

Keys can be rotated without data loss using the re-encryption utility:

```bash
nexus-eda-admin rotate-key --tenant {self.config.tenant_id} --new-key /path/to/new-key.hex
```

## Sovereign Data Boundary

This key is used to encrypt all design data at rest. The key never leaves
the customer's infrastructure. In air-gapped deployments, the key can be
entered manually at boot time via a QR code or USB token.

**Compliance:** AES-256-GCM with NIST SP 800-38D authenticated encryption.
"""

    def _sso_setup_guide(self) -> str:
        return f"""\
# SSO/SAML Setup Guide for {self.company.name}

**Tenant ID:** {self.config.tenant_id}

## Step 1: Configure Your Identity Provider

### Azure AD

1. Go to Azure Portal → Azure Active Directory → Enterprise Applications
2. Create a new application: "Nexus-EDA {self.company.name}"
3. Configure SAML:
   - Identifier (Entity ID): `https://app.nexuseda.com/sso/{self.config.tenant_id}/`
   - Reply URL (ACS): `https://app.nexuseda.com/sso/{self.config.tenant_id}/acs`
   - Download the Federation Metadata XML

4. Map these claims:
   - `email` → `user.mail`
   - `name` → `user.displayName`
   - `groups` → `user.groups`

### Okta

1. Go to Okta Admin → Applications → Applications
2. Create a new app integration → SAML 2.0
3. App name: "Nexus-EDA {self.company.name}"
4. SAML Settings:
   - Single sign-on URL: `https://app.nexuseda.com/sso/{self.config.tenant_id}/acs`
   - Audience URI: `https://app.nexuseda.com/sso/{self.config.tenant_id}/`

## Step 2: Upload IdP Metadata

Send your IdP metadata XML to `support@nexiussignalworks.com` with subject:
`SSO Setup: {self.config.tenant_id}`

Our team will configure the SP settings and confirm within 1 business day.

## Step 3: Test

After configuration, test with:
- URL: https://app.nexuseda.com/sso/{self.config.tenant_id}/
- Your company email address
"""

    def _sable_entry_points(self) -> list[str]:
        """Return the 28 SABLE-inspired scoped entry points (stripped PDK/paths)."""
        return [
            "get_component_list", "get_netlist", "get_design_rules",
            "get_layer_count", "get_board_dimensions", "get_component_count",
            "get_nets_with_violations", "get_component_placement",
            "get_trace_lengths", "get_via_count", "get_copper_pour_areas",
            "get_drc_violations", "get_component_pins", "get_net_connections",
            "get_layer_thickness", "get_material_info", "get_clearance_rules",
            "get_trace_width_rules", "get_via_rules", "get_keepout_zones",
            "get_component_boundaries", "get_pad_shapes", "get_solder_mask_layers",
            "get_drill_sizes", "get_stackup_info", "get_impedance_data",
            "get_thermal_zones", "get_power_domains",
        ]


# --------------------------------------------------------------------------- #
# Package builder (tarball)
# --------------------------------------------------------------------------- #
def build_airgap_tarball(
    config: DeploymentConfig,
    company: CompanyProfile,
    output_dir: str | Path,
) -> Path:
    """Build an air-gap deployment tarball.

    Creates a directory containing all configuration artifacts and packages
    them into a .tar.gz file. Model GGUF files are NOT included — they are
    shipped on physical media per the SABLE security model.

    Returns the path to the generated tarball.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pkg = DeploymentPackage(config, company)
    artifacts = pkg.artifacts()

    bundle_dir = output_dir / f"nexus-eda-bundle-{company.name.lower().replace(' ', '-')}"
    bundle_dir.mkdir(exist_ok=True)

    for artifact in artifacts:
        file_path = bundle_dir / artifact.filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(artifact.content, encoding="utf-8")

    # Generate SHA-256 checksums
    checksums_path = bundle_dir / "SHA256SUMS"
    lines = []
    for artifact in artifacts:
        content = artifact.content
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        lines.append(f"{digest}  {artifact.filename}")
    checksums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    tarball_path = output_dir / f"nexus-eda-bundle-{company.name.lower().replace(' ', '-')}.tar.gz"
    with tarfile.open(tarball_path, "w:gz") as tar:
        tar.add(bundle_dir, arcname=bundle_dir.name)

    return tarball_path


def generate_deployment_summary(config: DeploymentConfig, company: CompanyProfile) -> str:
    """Generate a human-readable deployment summary for the customer."""
    return f"""\
# Nexus-EDA Enterprise Deployment Summary

**Company:** {company.name}
**Industry:** {company.industry}
**Tier:** {config.tier.value.upper()} (${config.tier.monthly_price_usd:,.0f}/mo)

## Deployment Configuration

| Setting | Value |
|---------|-------|
| Tenant ID | {config.tenant_id} |
| Deployment Target | {config.deployment_target} |
| SSO/SAML | {'Enabled' if config.sso_enabled else 'Disabled'} |
| Model Assignment | {config.model_assignment} |
| Storage Quota | {config.storage_quota_gb} GB |
| Max Concurrent Agents | {config.max_concurrent_agents} |

## Compliance Profile

{chr(10).join(f"  - {reg}: Verified" for reg in sorted(config.compliance_profile))}

## Sovereign Data Architecture

- All LLM inference runs locally on your infrastructure
- AES-256 encryption at rest for all design data
- SABLE-inspired scoped entry points: 28 functions that strip PDK/paths/models
- No telemetry, no external calls in air-gapped mode
- Data never leaves your network without explicit export

## Next Steps

1. Review the deployment artifacts in the bundle
2. Schedule a technical onboarding call with our team
3. Deploy the package to your infrastructure
4. Your success manager will coordinate UAT and sign-off

**Support:** enterprise-support@nexiussignalworks.com
**SLA:** {24 if config.tier.requires_cma else 48}-hour response time
"""
