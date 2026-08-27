# SPDX-License-Identifier: Apache-2.0
# Nexus-EDA RELEASE NOTES
# This file is released alongside the v1.0.0 tag.

# Changelog
All notable changes to Nexus-EDA are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-08-27 — "Enterprise with Sovereign Data"

### Added — Sovereign Data Boundary (Phase 4)
- **28 scoped entry points** (SABLE-inspired): 8 export, 6 import, 7 query, 7 control
  - Deny-by-default policy: only explicit entry points allow data to cross the boundary
  - PDK paths, project paths, model paths, and user IDs are stripped before export
  - Network isolation (air-gap) mode enforced by default for `export` family
  - Approval gates for sensitive export operations
- **AES-256-GCM encrypted local storage**
  - `EncryptedStore` with PBKDF2-HMAC-SHA256 key derivation (600k iterations)
  - Atomic writes (temp + rename), tamper-evident audit trail
  - `cryptography` package integration; graceful degradation if unavailable
- **GDPR Compliance module** (Article 15 — Right of Access, Article 17 — Right to Erasure)
  - `GDPRCompliance.export_user_data()` — structured data export
  - `GDPRCompliance.delete_user_data()` — permanent data deletion
- **ITAR Compliance module** (22 CFR §§ 120-130)
  - `ITARCompliance.log_export_attempt()` — immutable export attempt logging
  - `ITARCompliance.verify_no_training()` — non-training guarantee enforcement
  - USML category references for defense-tier projects
- **Immutable Audit Trail** (`AuditTrail`)
  - Append-only, hash-chained signatures (SHA-256)
  - `verify_chain()` for tamper detection
  - GDPR/ITAR events tagged with compliance level

### Added — Core Engine
- `nexus_eda.sovereign` package — full sovereign data boundary implementation
- `nexus_eda.sovereign.boundary` — SovereignBoundary, 28 entry points, stripping engine
- `nexus_eda.sovereign.store` — AES256Crypto, EncryptedStore with atomic writes
- `nexus_eda.sovereign.compliance` — GDPRCompliance, ITARCompliance, AuditTrail

### Changed
- Version bumped from 0.1.0 → 1.0.0 (first stable release)
- Default model updated: DeepSeek-V3-8B → Qwen3-Coder-32B (Q4_K_M, ~18GB on RTX 4090)
- README updated with architecture diagram including sovereign boundary layer
- Model manifest (`models/manifest.yaml`) updated to reflect new primary model

### Security
- **Non-training guarantee**: SovereignBoundary refuses any data referencing
  model training; ITAR module enforces same at defense tier
- **Air-gapped by default**: network_isolation=True blocks all export operations
  that reference network endpoints
- **Key separation**: AES-256 keys never persisted; derived per-session from passphrase
- **Tamper evidence**: audit trail uses hash-chain signatures; `verify_chain()` detects
  any modification

### Licensing
- Core engine & plugin: Apache 2.0
- Sovereign data boundary: Apache 2.0
- Commercial tier features (SSO/SAML, Phase 2+ agents, 3D viewer): Proprietary
  — see LICENSE-COMMUNITY and NOTICE for details
- No model weights shipped; user downloads separately from HuggingFace

## [0.1.0] — 2024-08-26 — Phase 1 Scaffold

### Added
- KiCad plugin skeleton (`src/nexus_eda/plugin.py`) — ActionPlugin registration
- `NetlistParser` — S-expression parser for KiCad .net files
- `DesignRuleChecker` — basic DRC rules (net isolation, component pad count)
- `LLMEngine` — llama.cpp wrapper with manifest-driven config
- `NetlistViewer` — dual-stack ImGui reference + HTML preview rendering
- Agent stubs: `analyze_netlist`, `optimize_bom`, `suggest_routing`
- 3 passing netlist tests, 3 agent stub tests
- GitHub Actions CI (lint + test)
