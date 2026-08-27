---
title: "Agents"
weight: 50
---

# Nexus-EDA Agents

Nexus-EDA uses a multi-agent architecture where each agent is a specialized
module that performs a specific PCB design task. All agents follow the
**human-in-the-loop** principle: they never auto-commit changes without
explicit user approval.

## Agent Overview

| Agent             | File                        | Primary Model             |
|-------------------|-----------------------------|----------------------------|
| Netlist Analyzer  | `netlist_analyzer.py`       | DeepSeek-V3-0324 (8B)     |
| BOM Optimizer     | `bom_optimizer.py`          | DeepSeek-V3-0324 (8B)     |
| Routing Agent     | `routing_agent.py`          | DeepSeek-V3-0324 (8B)     |
| DRC Assistant     | `drc_assistant.py`          | Qwen2.5-7B (fallback)     |

## Netlist Analyzer

**File**: `src/nexus_eda/agents/netlist_analyzer.py`

Parses the board's netlist to identify:

- Unrouted connections
- Floating nets (nets with fewer than 2 nodes)
- Components with unusual connection counts
- Placement issues

### Usage (via KiCad UI)

1. Open your PCB in KiCad
2. Go to **Tools → Plugins → Nexus-EDA Copilot → Analyze Netlist**
3. Review the results in the popup dialog

### API

```python
from nexus_eda.agents.netlist_analyzer import analyze_netlist

board = pcbnew.GetBoard()
result = analyze_netlist(board)

# result is a dict:
# {
#   'unrouted_count': 3,
#   'severity': 'warning',
#   'analysis': "..."
# }
```

## BOM Optimizer

**File**: `src/nexus_eda/agents/bom_optimizer.py`

Cross-references your BOM against JLCPCB and LCSC pricing catalogs to find:

- Cheaper alternative components
- Components with better availability
- Suggested substitutions for cost reduction

### Usage

1. Export your BOM from KiCad: **File → Fabrication Outputs → BOM**
2. In KiCad, select **Tools → Plugins → Nexus-EDA Copilot → Optimize BOM**
3. Review the savings report

### API

```python
from nexus_eda.agents.bom_optimizer import optimize_bom

board = pcbnew.GetBoard()
result = optimize_bom(board)

# {
#   'total_savings': 12.50,
#   'alternatives_count': 5,
#   'breakdown': [...]
# }
```

## Routing Agent

**File**: `src/nexus_eda/agents/routing_agent.py`

Provides AI-powered routing suggestions for selected nets:

- Trace path optimization
- Via placement recommendations
- Differential pair routing guidance

### Usage

1. Select a net in pcbnew
2. Select **Tools → Plugins → Nexus-EDA Copilot → Suggest Routing**
3. Review the suggested path before applying

### API

```python
from nexus_eda.agents.routing_agent import suggest_routing

board = pcbnew.GetBoard()
result = suggest_routing(board)

# {
#   'path_description': "Route U1 pin 5 → R3 pad 1...",
#   'via_suggestions': [...],
# }
```

## DRC Assistant (Phase 2)

**File**: `src/nexus_eda/agents/drc_assistant.py`

Runs `pcbnew`'s DRC engine and provides natural-language summaries of
violations. This feature is under active development in Phase 2.

## Confidence Scoring

All agents return a confidence score (0.0–1.0) with their suggestions.
Low-confidence results are highlighted with a ⚠️ warning. The agent never
applies changes automatically — every suggestion requires explicit user
approval.

```python
result = analyze_netlist(board)
print(result['confidence'])  # e.g. 0.92
if result['confidence'] < 0.7:
    print("Low confidence — review carefully!")
```
