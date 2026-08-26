# Nexus-EDA Phase 1 — Kanban Task Reference

Board: `nexus-eda-phase1` (DB: `C:\Users\bhogl\AppData\Local\hermes\kanban\boards\nexus-eda-phase1\kanban.db`)

| Task ID | Week | Title | Status |
|---|---|---|---|
| `t_61889236` | W1 | Project scaffolding — git repo, CI pipeline, KiCad plugin skeleton | ready |
| `t_1092a6ec` | W2 | LLM integration — llama.cpp binding, model loading, basic prompt template | ready |
| `t_cc780309` | W3 | Netlist analyzer — parse .net files, identify unrouted nets/DRC violations | ready |
| `t_bc657aac` | W4 | BOM optimizer — cross-ref KiCad BOM with LCSC/JLCPCB API, flag alternatives | ready |
| `t_f37fd6f8` | W5 | Routing agent — first agent tool call, suggest trace path for single net | ready |
| `t_f3ddd29d` | W6 | DRC assistant — integrate pcbnew DRC, summarize violations in natural language | ready |
| `t_2e1a4d14` | W7 | Integration testing — full workflow: load board → analyze → suggest → write back | ready |
| `t_63401d13` | W8 | Community release — publish to KiCad plugin repo, announce on r/PCB + X/Twitter | ready |
| `t_8bb16712` | W9 | Feedback iteration cycle 1 — collect alpha user feedback | ready |
| `t_d10871a1` | W10 | Feedback iteration cycle 2 — optimize prompts and routing suggestions | ready |
| `t_ab07e1bd` | W11 | Performance optimization — model quant tuning, latency reduction | ready |
| `t_a0342b0b` | W12 | Phase 2 planning — specify cloud collaboration + autonomous routing roadmap | ready |

## Assignment
- **Lead:** blockie
- **W1 (scaffolding):** Assign to Forge (subagent) — complete plugin stub, tests, CI config
- **W2–W5 (agents):** Vantage + custom LangChain agents for AI integration
- **Weekly sync:** Review Kanban board, assign next sprint