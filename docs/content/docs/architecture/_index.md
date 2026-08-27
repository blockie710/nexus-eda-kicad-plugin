---
title: "Architecture"
weight: 30
---

# Architecture

Nexus-EDA follows a layered architecture that separates the KiCad plugin UI from
the AI engine and agent layer. This design enables independent development,
testing, and extension of each component.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    KiCad Plugin (wxPython)              │
│  ┌─────────────┐  ┌──────────┐  ┌────────────────┐      │
│  │ Netlist     │  │ BOM      │  │ Routing Agent  │      │
│  │ Analyzer    │  │ Optimizer│  │ Agent          │      │
│  └─────────────┘  └──────────┘  └────────────────┘      │
└────────────────────────┬────────────────────────────────┘
                         │ Python API (pcbnew)
┌─────────────────────────────────────────────────────────┐
│                   AI Engine (llama.cpp)                 │
│  ┌──────────────────────────────────────────────────┐   │
│  │  DeepSeek-V3-0324 (8B, Q4_K_M)                   │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## Components

### 1. Plugin Layer (`src/nexus_eda/plugin.py`)

The entry point for KiCad. It registers the plugin action, builds the menu,
and dispatches commands to the appropriate agent.

- **`NexusEDABar`**: Top-level menu bar extension within KiCad
- **`NexusEDAPlugin`**: The `pcbnew.ActionPlugin` subclass that KiCad loads

### 2. Agent Layer (`src/nexus_eda/agents/`)

Each agent is a focused module that performs a specific PCB design task.
Agents use the LLM engine but include guardrails to prevent auto-applying
changes without approval.

| Agent             | File                        | Responsibility                          |
|-------------------|-----------------------------|-----------------------------------------|
| Netlist Analyzer  | `netlist_analyzer.py`       | Parse netlists, detect unrouted nets    |
| BOM Optimizer     | `bom_optimizer.py`          | Cross-ref BOM vs. JLCPCB/LCSC pricing   |
| Routing Agent     | `routing_agent.py`          | Suggest trace paths for selected nets   |
| DRC Assistant     | `drc_assistant.py`          | Summarize pcbnew DRC violations         |

### 3. LLM Engine (`src/nexus_eda/llm/`)

A thin wrapper around `llama-cpp-python` that loads quantized models and
provides a consistent interface for generation:

- **`LLMConfig`**: Configuration dataclass, loaded from `models/manifest.yaml`
- **`LLMEngine`**: The main engine class with streaming support
- **`load_model()` / `generate()`**: Module-level convenience functions

### 4. Netlist Parser (`src/nexus_eda/netlist/`)

Parses KiCad S-expression netlists into structured data:

- **`NetlistParser`**: Recursive-descent parser for `.net` files
- **`DesignRuleChecker`**: Basic DRC validation rules
- **`NetlistData`**: Dataclass holding parsed components and nets

### 5. Models Manifest (`models/manifest.yaml`)

Central configuration for all AI models used by the project:

| Model               | Params | VRAM (Q4) | Use Case                |
|---------------------|--------|-----------|-------------------------|
| DeepSeek-V3-0324    | 8B     | 6-8 GB    | Primary reasoning       |
| Llama-3.1-8B        | 8B     | 6-8 GB    | Fallback reasoning      |
| Qwen2.5-7B          | 7B     | 5-6 GB    | Lightweight tasks       |
| Qwen2.5-VL-7B       | 7B     | 8-10 GB   | Vision (Phase 1.5+)     |

## Data Flow

1. **User Action**: User selects a menu item in KiCad (e.g., "Analyze Netlist")
2. **Plugin Dispatch**: `NexusEDABar` calls the corresponding agent function
3. **Agent Execution**: The agent queries the KiCad board via `pcbnew`, formats
   a prompt, and calls the LLM engine
4. **LLM Generation**: The engine streams tokens from the local model
5. **Response**: The agent parses the LLM response and returns a structured result
6. **UI Display**: The plugin displays the result in a message dialog or panel

## Design Principles

- **Local-first**: All inference runs on-device. No data leaves the machine.
- **Open-core**: Core engine is Apache 2.0; Pro/Enterprise agents are proprietary.
- **Agentic**: Agents perform tasks autonomously, not just suggestions.
- **Physics-validated**: Future phases include SI/PI and thermal validation.
- **Zero-cloud**: No API keys, no subscriptions, no data exfiltration.
