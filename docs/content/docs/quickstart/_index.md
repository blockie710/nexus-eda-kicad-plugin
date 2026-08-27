---
title: "Quick Start"
weight: 10
---

# Quick Start Guide

Get the Nexus-EDA Copilot running inside KiCad in under 5 minutes.

## Prerequisites

| Requirement       | Minimum          | Recommended       |
|-------------------|------------------|-------------------|
| KiCad             | 7.0              | 8.0               |
| Python            | 3.11             | 3.12              |
| GPU VRAM          | 12 GB (RTX 3060) | 24 GB (RTX 4090)  |
| Disk space (models)| 15 GB           | 20 GB             |

## Step 1 — Install the Plugin

```bash
# Clone and install from source
git clone https://github.com/blockie710/nexus-eda-kicad-plugin.git
cd nexus-eda-kicad-plugin

# Install with Poetry
poetry install

# Or with pip for KiCad's bundled Python
pip install -e .
```

## Step 2 — Download a Model

```bash
# Create the models directory
mkdir -p models/

# Download DeepSeek-V3-0324 (8B, Q4_K_M) — ~5 GB
huggingface-cli download deepseek-ai/DeepSeek-V3-0324 \
  --filename DeepSeek-V3-0324-Q4_K_M.gguf \
  --local-dir models/
```

Set the model path:

```bash
export NEXUS_LLM_MODEL_PATH="models/DeepSeek-V3-0324-Q4_K_M.gguf"
```

## Step 3 — Launch KiCad

1. Open KiCad
2. Open your PCB project
3. Go to **Tools → Plugins → Nexus-EDA Copilot**
4. Select **Analyze Netlist** to start

## Next Steps

- [Installation Guide](/docs/installation) — detailed setup
- [Architecture](/docs/architecture) — system design
- [AI Engines](/docs/engines) — LLM configuration
- [Agents](/docs/agents) — multi-agent workflow
