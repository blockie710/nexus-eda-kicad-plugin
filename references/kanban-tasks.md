# Nexus-EDA — Kanban Task Reference

Board: `nexus-eda-phase1`
DB: `C:\Users\bhogl\AppData\Local\hermes\kanban\boards\nexus-eda-phase1\kanban.db`

## Phase 1 (Completed — Months 1-3)
| Task ID | Week | Title | Status |
|---------|------|-------|--------|
| t_61889236 | W1 | Project scaffolding — git repo, CI pipeline, KiCad plugin skeleton | ✅ completed |
| t_1092a6ec | W2 | LLM integration — llama.cpp binding, model loading, prompt templates | ✅ completed |
| t_cc780309 | W3 | Netlist analyzer — parse .net files, DRC violations | ✅ completed |
| t_bc657aac | W4 | BOM optimizer — cross-ref KiCad BOM with LCSC/JLCPCB | ✅ completed |
| t_f37fd6f8 | W5 | Routing agent — suggest trace path for single net | ✅ completed |
| t_f3ddd29d | W6 | DRC assistant — pcbnew DRC, summarize violations | ✅ completed |
| t_2e1a4d14 | W7 | Integration testing — full workflow | ✅ completed |
| t_63401d13 | W8 | Community release — publish to KiCad plugin repo | ✅ completed |
| t_8bb16712 | W9 | Feedback iteration cycle 1 | ✅ completed |
| t_d10871a1 | W10 | Feedback iteration cycle 2 | ✅ completed |
| t_ab07e1bd | W11 | Performance optimization | ✅ completed |
| t_a0342b0b | W12 | Phase 2 planning — cloud collaboration + autonomous routing spec | ✅ completed |

## Phase 2 (Ready — Months 4-6)
| Task ID | Week | Title | Agent Profile | Model |
|---------|------|-------|---------------|-------|
| T2-W5.1 | W5 | Set up AutoGen multi-agent orchestration framework | nexus-llm | Qwen3-Coder 32B |
| T2-W5.2 | W5 | Create DRC agent — pcbnew DRC API, parse violations | nexus-llm | Qwen3-Coder 32B |
| T2-W5.3 | W5 | Create routing agent — net topology, trace path suggestions | nexus-spatial | DeepSeek-Coder-V2 23B |
| T2-W6.1 | W6 | Create BOM optimizer agent — LCSC/JLCPCB catalog cross-reference | nexus-fast | Qwen2.5-Coder 7B |
| T2-W6.2 | W6 | Implement agent confidence scoring — never auto-commit | nexus-llm | Qwen3-Coder 32B |
| T2-W6.3 | W6 | Human-in-loop approval gates for all agent actions | nexus-orchestrator | Llama 3.1 8B |
| T2-W7 | W7 | Integration testing — full workflow | nexus-llm | Qwen3-Coder 32B |
| T2-W8 | W8 | Publish v0.2.0 to GitHub + announce on r/PCB | nexus-fast | Qwen2.5-Coder 7B |

## Phase 3 (Ready — Months 7-9)
| Task ID | Week | Title | Agent Profile | Model |
|---------|------|-------|---------------|-------|
| T3-W9.1 | W9 | 3D PCB viewer — DX12/Vulkan rendering | nexus-vision | Qwen2.5-VL 7B |
| T3-W9.2 | W9 | Signal integrity analyzer — impedance, crosstalk | nexus-math | DeepSeek-R1-Distill 7B |
| T3-W10.1 | W10 | Power integrity checker — voltage drop, decoupling | nexus-math | DeepSeek-R1-Distill 7B |
| T3-W10.2 | W10 | Thermal hotspot detector — power dissipation modeling | nexus-math | DeepSeek-R1-Distill 7B |
| T3-W11.1 | W11 | Manufacturability checker — JLCPCB/PCBWay DRC | nexus-fast | Qwen2.5-Coder 7B |
| T3-W11.2 | W11 | Zero-copy integration with NBS rendering | nexus-spatial | DeepSeek-Coder-V2 23B |
| T3-W12 | W12 | Integration testing + publish v0.3.0 | nexus-llm | Qwen3-Coder 32B |
| T3-W14 | W14 | Community feedback iteration | nexus-fast | Qwen2.5-Coder 7B |

## Phase 4 (Ready — Months 10-12)
| Task ID | Week | Title | Agent Profile | Model |
|---------|------|-------|---------------|-------|
| T4-W15.1 | W15 | SABLE-inspired 28 scoped entry points (strip PDK/paths) | nexus-minimal | TinyLlama 1.1B |
| T4-W15.2 | W15 | Encrypted local storage (AES-256) | nexus-minimal | TinyLlama 1.1B |
| T4-W15.3 | W15 | Non-training guarantee — audit data paths | nexus-minimal | TinyLlama 1.1B |
| T4-W16.1 | W16 | On-prem deployment (Docker + local serving) | nexus-orchestrator | Llama 3.1 8B |
| T4-W16.2 | W16 | GDPR compliance module — data export/deletion | nexus-math | DeepSeek-R1-Distill 7B |
| T4-W17.1 | W17 | SSO/SAML integration (Enterprise tier) | nexus-llm | Qwen3-Coder 32B |
| T4-W17.2 | W17 | ITAR compliance audit trail (Defense tier) | nexus-math | DeepSeek-R1-Distill 7B |
| T4-W18 | W18 | Publish v1.0.0 — Enterprise with sovereign data | nexus-llm | Qwen3-Coder 32B |
| T4-W20 | W20 | Beta enterprise onboarding (3-5 companies) | nexus-fast | Qwen2.5-Coder 7B |

## Phase 5 (Ready — Months 13-15)
| Task ID | Week | Title | Agent Profile | Model |
|---------|------|-------|---------------|-------|
| T5-W21.1 | W21 | Stripe billing — tiers (Free, $19, $49, Enterprise) | nexus-minimal | TinyLlama 1.1B |
| T5-W21.2 | W21 | Customer support automation — ticket routing, FAQ | nexus-fast | Qwen2.5-Coder 7B |
| T5-W22.1 | W22 | Marketing launch — X/Twitter campaign | nexus-minimal | TinyLlama 1.1B |
| T5-W22.2 | W22 | Documentation site — GitHub Pages + Hugo | nexus-fast | Qwen2.5-Coder 7B |
| T5-W23.1 | W23 | YouTube tutorial series — Building PCBs with AI | nexus-minimal | TinyLlama 1.1B |
| T5-W23.2 | W23 | Discord community server setup | nexus-fast | Qwen2.5-Coder 7B |
| T5-W24 | W24 | First paid customers — 3 enterprise + 50 pro | nexus-orchestrator | Llama 3.1 8B |
| T5-W26 | W26 | Post-launch stabilization + feedback | nexus-llm | Qwen3-Coder 32B |

## Agent Profile Model Matrix
| Profile | Model | VRAM | License | Use Case |
|---------|-------|------|---------|----------|
| nexus-llm | Qwen3-Coder 32B | ~18GB | Qwen2.5 | Primary (coding, reasoning, DRC) |
| nexus-fast | Qwen2.5-Coder 7B | ~6GB | Qwen2.5 | Fast tasks (parsing, BOM, marketing) |
| nexus-spatial | DeepSeek-Coder-V2 23B | ~16GB | MIT | Spatial (routing, 3D placement) |
| nexus-math | DeepSeek-R1-Distill 7B | ~6GB | MIT | Math (SI/PI, thermal, compliance) |
| nexus-vision | Qwen2.5-VL 7B | ~7GB | Qwen2.5 | Vision (3D board inspection) |
| nexus-orchestrator | Llama 3.1 8B | ~7GB | Llama 3.1 | Orchestration (workflow, SaaS) |
| nexus-minimal | TinyLlama 1.1B | ~1GB | Apache 2.0 | Minimal (GUI, billing, trusted ops) |

## Dispatch Notes
- Research tasks: use `poolside/laguna-s-2.1:free` (NOT gemma4:12b — produces poor output)
- Never use parallel subagents with web_search (Firecrawl MCP rate limit ~20 req/min)
- For research: direct httpx API calls to Firecrawl with 8s delays, or HF tools
- Phase 2-5 tasks ready for dispatch as Phase 1 is complete
