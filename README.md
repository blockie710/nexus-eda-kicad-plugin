# Nexus-EDA KiCad Plugin

> AI-assisted PCB design automation — local-first, air-gapped, open-core.
> **v1.0.0 "Enterprise with Sovereign Data"** — includes SABLE-inspired sovereign data boundary.

## Overview

Nexus-EDA is a KiCad plugin that integrates AI agents to automate routine PCB design tasks: netlist analysis, BOM optimization, routing suggestions, and DRC assistance. It runs entirely on-device using quantized open-source LLMs (Qwen3-Coder 32B, Llama-3.1-8B).

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    KiCad Plugin (wxPython)              │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐ │
│  │ Netlist     │  │ BOM Optimizer│  │ Routing Agent  │ │
│  │ Analyzer    │  │ Agent        │  │ Agent          │ │
│  └─────────────┘  └──────────────┘  └────────────────┘ │
└────────────────────────┬────────────────────────────────┘
                         │ Python API (pcbnew)
┌─────────────────────────────────────────────────────────┐
│                   AI Engine (llama.cpp)                 │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Qwen3-Coder-32B-Q4_K_M  (~18GB, RTX 4090 fit)   │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────┘
                         │ Sovereign Data Boundary (Phase 4)
┌─────────────────────────────────────────────────────────┐
│     AES-256-GCM Encrypted Store + GDPR/ITAR Compliance  │
│   28 Scoped Entry Points (SABLE-inspired, deny-by-def.) │
└─────────────────────────────────────────────────────────┘
```

### Security Boundaries

- **Air-gapped by default:** No network calls in Phase 1
- **Sovereign Data Boundary (Phase 4):** SABLE-inspired 28 scoped entry points with deny-by-default policy; PDK paths, model paths, and project paths are stripped before any data leaves the trusted boundary
- **AES-256-GCM encrypted storage:** All design data encrypted at rest; keys derived via PBKDF2-HMAC-SHA256 (600k iterations), never stored on disk
- **GDPR/ITAR compliance:** Data export/deletion APIs, immutable audit trail with hash-chain signatures, non-training guarantee enforced
- **Model downloaded once** via HuggingFace (verified checksums)
- **No telemetry:** All processing stays on-device
- **File I/O sandboxed:** Plugin only reads/writes .kicad_pcb and .net files in project dir

## Quick Start

### Prerequisites

- KiCad 7.0+ (pcbnew Python API)
- Python 3.11+
- llama-cpp-python (local inference)

```bash
# Install plugin
pip install -e .

# Launch KiCad, go to Tools → Plugins → Nexus-EDA Copilot
```

## License

- **Core engine & plugin:** Apache 2.0
- **Pro agent modules:** Proprietary (Phase 2+) — see [LICENSE-COMMUNITY](LICENSE-COMMUNITY)
- **Sovereign data boundary:** Apache 2.0
- See [LICENSE](LICENSE), [LICENSE-COMMUNITY](LICENSE-COMMUNITY), and [NOTICE](NOTICE)

## Resources

- [Phase 1 Plan](references/eda-phase1-plan.md)
- [Phase 2-5 Roadmap](references/eda-phase2-5-plan.md)
- [Investigation Workflow](references/eda-market-investigation.md)
- [Pitch Deck](references/nexus-eda-pitch-deck.md)
- [CHANGELOG](CHANGELOG.md)
- [Kanban Board](references/kanban-tasks.md)