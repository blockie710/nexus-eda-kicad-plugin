# Nexus-EDA KiCad Plugin

> AI-assisted PCB design automation — local-first, air-gapped, open-core.

## Overview

Nexus-EDA is a KiCad plugin that integrates AI agents to automate routine PCB design tasks: netlist analysis, BOM optimization, routing suggestions, and DRC assistance. It runs entirely on-device using quantized open-source LLMs (DeepSeek-V3, Llama-3.1-8B).

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
│  │  DeepSeek-V3-8B-Q4_K_M  (~5GB, RTX 4090 fit)    │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

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
- **Pro agent modules:** Proprietary (Phase 2)
- See [LICENSE](LICENSE) and [LICENSE-COMMUNITY](LICENSE-COMMUNITY)

## Resources

- [Phase 1 Plan](references/eda-phase1-plan.md)
- [Investigation Workflow](references/eda-market-investigation.md)
- [Pitch Deck](references/nexus-eda-pitch-deck.md)
- [Kanban Board](references/kanban-tasks.md)