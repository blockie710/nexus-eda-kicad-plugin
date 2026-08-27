---
title: "Installation"
weight: 20
---

# Installation Guide

Detailed instructions for installing Nexus-EDA Copilot on different platforms.

## System Requirements

### Hardware Requirements

| Component        | Minimum              | Recommended            |
|------------------|----------------------|------------------------|
| CPU              | x86-64, 4 cores      | x86-64, 8+ cores       |
| GPU              | RTX 3060 (12 GB)     | RTX 4090 (24 GB)       |
| System RAM       | 16 GB                | 32 GB                  |
| Disk Space       | 15 GB                | 25 GB (models + tools) |
| CUDA             | 12.6+                | 13.3+                  |

### Software Requirements

- **Operating Systems**: Windows 11, Linux (Ubuntu 22.04+)
- **KiCad**: 7.0 or 8.0
- **Python**: 3.11 or 3.12
- **Poetry**: 1.8+ (recommended) or pip

## Linux Installation

### Install KiCad

```bash
# Ubuntu 22.04+
sudo apt update
sudo apt install -y kiCad kiCad-packages3D

# Or via their PPA for latest version
sudo add-apt-repository ppa:kicad/kicad-8.0-releases -y
sudo apt update
sudo apt install -y KiCad
```

### Install Poetry

```bash
curl -sSL https://install.python-poetry.org | python3 -
```

### Install Nexus-EDA

```bash
git clone https://github.com/blockie710/nexus-eda-kicad-plugin.git
cd nexus-eda-kicad-plugin
poetry install
poetry shell
```

## Windows Installation

### Install KiCad

1. Download KiCad 8.0 from [kicad.org](https://www.kicad.org/download/windows)
2. Run the installer with default settings

### Install Nexus-EDA

```powershell
git clone https://github.com/blockie710/nexus-eda-kicad-plugin.git
cd nexus-eda-kicad-plugin
pip install -e .
```

> **Note**: On Windows, install into the **same Python environment** that KiCad uses
> (usually `C:\Program Files\KiCad\bin\python.exe`).

## Model Setup

After installing the plugin, download at least one quantized model:

```bash
# Create models directory
mkdir -p models/

# DeepSeek-V3-0324 (8B, Q4_K_M) — primary recommendation
huggingface-cli download deepseek-ai/DeepSeek-V3-0324 \
  --filename DeepSeek-V3-0324-Q4_K_M.gguf \
  --local-dir models/

# Llama-3.1-8B (fallback)
huggingface-cli download meta-llama/Llama-3.1-8B-Instruct-GGUF \
  --filename Llama-3.1-8B-Instruct-Q4_K_M.gguf \
  --local-dir models/
```

Set the environment variable:

```bash
# Linux / macOS
export NEXUS_LLM_MODEL_PATH="$PWD/models/DeepSeek-V3-0324-Q4_K_M.gguf"

# Windows (PowerShell)
$env:NEXUS_LLM_MODEL_PATH = "models\DeepSeek-V3-0324-Q4_K_M.gguf"
```

## Verifying the Installation

Launch KiCad and check the plugin loads:

```bash
kicad --scripting-resume-extensions
```

Then open a project and navigate to **Tools → Plugins → Nexus-EDA Copilot**.

## Troubleshooting

### Plugin doesn't appear in KiCad

Ensure you installed into the correct Python environment:

```bash
# Inside KiCad's Python environment
pip show nexus-eda-kicad-plugin
```

### Model loading fails

Check that the `NEXUS_LLM_MODEL_PATH` environment variable points to a valid `.gguf` file and that the `llama-cpp-python` package is installed:

```bash
pip install llama-cpp-python --force-reinstall
```
