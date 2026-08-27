# Nexus-EDA v1.0.0 Release Guide

## Overview

v1.0.0 "Enterprise with Sovereign Data" is the first stable release of the
Nexus-EDA KiCad plugin. It bundles the complete Phase 1 feature set (netlist
analysis, BOM optimization, routing suggestions, DRC assistance) with the
Phase 4 Sovereign Data Boundary — a SABLE-inspired, deny-by-default data
boundary that enforces air-gap isolation, AES-256 encryption, and GDPR/ITAR
compliance.

## Release Checklist

### 1. Pre-release Verification
- [ ] All existing tests pass: `pytest tests/ -v`
- [ ] New sovereign boundary tests pass: `pytest tests/test_sovereign*.py -v`
- [ ] Lint clean: `ruff check src/` and `black --check src/`
- [ ] Version verified: `python -c "import nexus_eda; print(nexus_eda.__version__)"` → `1.0.0`
- [ ] G7 RT-invariant gate passes on all Python paths

### 2. Tagging
```bash
git tag -a v1.0.0 -m "Nexus-EDA v1.0.0 — Enterprise with Sovereign Data"
git push origin v1.0.0
```

### 3. CI Release Workflow
The release workflow (`.github/workflows/release.yml`) is triggered by:
- Push of a `v*.*.*` tag → builds sdist + wheel, runs lint + tests
- Manual `workflow_dispatch` with optional PyPI publish

### 4. Artifacts
- **Package:** `dist/nexus-eda-kicad-plugin-1.0.0.tar.gz` (sdist)
- **Wheel:** `dist/nexus_eda_kicad_plugin-1.0.0-py3-none-any.whl`
- **Docs:** CHANGELOG.md, NOTICE, LICENSE-COMMUNITY
- **Schema:** `schemas/sovereign-boundary.json`

### 5. Post-Release
- [ ] Update README badge to point to v1.0.0 release
- [ ] Announce on r/PCB and X/Twitter
- [ ] Update Kanban: mark T4-W18 complete, T4-W20 (beta onboarding) ready

## Installation

```bash
pip install https://github.com/blockie710/nexus-eda-kicad-plugin/releases/latest/download/nexus-eda-kicad-plugin-1.0.0.tar.gz
```

Or install from source:

```bash
git clone https://github.com/blockie710/nexus-eda-kicad-plugin.git
cd nexus-eda-kicad-plugin
pip install -e .
```

## Commercial Licensing

- **Community Edition:** Apache 2.0 — free for personal, educational, and
  non-commercial use. Includes netlist analysis, BOM optimizer, routing
  suggestions, DRC assistant, and the sovereign data boundary.
- **Pro Tier ($19/month):** Adds commercial-use rights for multi-agent
  orchestration, BOM cloud pricing sync, and advanced routing.
- **Enterprise ($49/month):** Adds SSO/SAML, GDPR data portability API,
  and priority support.
- **Defense (contact sales):** Adds ITAR audit trail, USML category
  compliance reporting, and classified-project mode.

See [LICENSE-COMMUNITY](LICENSE-COMMUNITY) and [NOTICE](NOTICE) for details.
