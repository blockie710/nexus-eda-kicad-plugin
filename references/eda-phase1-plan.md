# Phase 1 Implementation Plan — Nexus-EDA (KiCad Copilot Plugin)

**Status:** Phase 1 Scaffolding  
**Lead:** blockie / Vantage  
**Timeline:** 3–6 months  
**Objective:** Build an open-source KiCad plugin that provides AI-assisted PCB design automation using locally-run LLMs, validating market demand before committing to full autonomous EDA.

---

## 1. Architecture

### Stack
| Layer | Technology | Rationale |
|---|---|---|
| **Core** | Rust (via KiCad's Python plugin API for initial prototype) | Zero-alloc, performance-critical routing logic |
| **AI Engine** | llama.cpp / Ollama local inference | Local-first, no cloud dependency; supports Q4-int4/Q8 quantization |
| **Model (Phase 1)** | DeepSeek-V3-0324-8K or Llama-3.1-8B (Q4_K_M) | Fits in RTX 4090 24GB VRAM; strong coding + logical reasoning |
| **Agent Framework** | Aider or custom LangChain + KiCad Python API | Tool-use capable; can invoke KiCad APIs (pcbnew, netlist) |
| **UI** | KiCad plugin dialog (wxPython) + optional web preview | Dual-stack: native KiCad integration + progressive web view |
| **Build** | CMake + Python packaging (pip) | Reproducible; integrates with existing KiCad plugin ecosystem |

### Data Flow
```
1. User selects a netlist/schematic in KiCad
2. Copilot plugin extracts netlist → JSON
3. Local LLM agent analyzes → identifies routing bottlenecks, BOM issues
4. Agent generates tool calls → pcbnew API (route traces, place components)
5. Results written back to KiCad PCB file
6. Physics validation layer runs DRC → reports violations
```

### Security Boundaries
- **Air-gapped by default:** No network calls in Phase 1
- **Model downloaded once** via HuggingFace (verified checksums)
- **No telemetry:** All processing stays on-device
- **File I/O sandboxed:** Plugin only reads/writes .kicad_pcb and .net files in project dir

---

## 2. Feature Scope (Phase 1 — MVP)

### Must-Have (Phase 1)
- [ ] **Netlist analysis agent**: Identify unrouted nets, component placement issues
- [ ] **Routing suggestion agent**: Recommend trace paths for low-complexity boards (2-layer, <100 components)
- [ ] **BOM optimization agent**: Detect duplicate/overpriced parts, suggest alternatives from LCSC/JLCPCB catalog
- [ ] **DRC pass assistant**: Run design rule checks, summarize violations in plain English
- [ ] **Local LLM integration**: Auto-detect Ollama/llama.cpp, load quantized model
- [ ] **Open-source license**: Apache 2.0 for core, with clear separation of commercial Pro extensions

### Nice-to-Have (Phase 1.5)
- [ ] **Component placement optimizer**: Use RL to suggest optimal placements
- [ ] **Thermal analysis hints**: Flag potential hotspots based on power dissipation
- [ ] **Manufacturability checker**: Verify design against JLCPCB/PCBWay DRC rules

### Deferred (Phase 2+)
- [ ] **Full autonomous routing** (Quilter/DeepPCB parity)
- [ ] **Physics-validated layout** (circuit-aware SI/PI checks)
- [ ] **Cloud collaboration** (E2EE sync, team workspaces)

---

## 3. Implementation Roadmap

| Week | Milestone | Deliverable |
|---|---|---|
| W1 | Project scaffolding | Git repo, CI pipeline (GitHub Actions), KiCad plugin skeleton |
| W2 | LLM integration | llama.cpp binding, model loading, basic prompt template |
| W3 | Netlist analyzer | Parse .net files, identify unrouted nets / DRC violations |
| W4 | BOM optimizer | Cross-reference KiCad BOM with LCSC/JLCPCB API, flag alternatives |
| W5 | Routing agent | First agent tool call: suggest trace path for single net |
| W6 | DRC assistant | Integrate KiCad's pcbnew DRC, summarize in natural language |
| W7 | Integration testing | Full workflow: load board → analyze → suggest → write back |
| W8 | Community release | Publish to KiCad plugin repository, announce on r/PCB, X/Twitter |
| W9-W12 | Feedback iteration | Collect user feedback, fix bugs, optimize prompts |

---

## 4. Technical Requirements

### Hardware (Development)
- **GPU:** RTX 4090 (24GB) — verified with CUDA 13.3.1
- **CPU:** 16+ cores (parallel batch processing of boards)
- **RAM:** 64 GB system memory
- **Storage:** 1 TB NVMe for model cache (Q4 Llama-3-8B = ~5GB on disk)

### Dependencies
```
kicad-python-scripts>=7.0
llama-cpp-python>=0.2.90  # Q4_K_M quantized inference
openai>=1.40.0           # For structured function calling to KiCad API
networkx>=3.3            # Graph analysis for netlists
pydantic>=2.7            # Structured output validation
```

### Model Selection Criteria (Phase 1)
| Model | Size (Q4) | VRAM | Context | Coding | Logical Reasoning | Verdict |
|---|---|---|---|---|---|---|
| DeepSeek-V3-0324 | ~5.0 GB | ~6-8 GB | 128K | Excellent | Excellent | ✅ Primary |
| Llama-3.1-8B | ~4.5 GB | ~6-8 GB | 128K | Good | Good | ✅ Fallback |
| Qwen2.5-7B | ~4.0 GB | ~6 GB | 128K | Good | Good | ✅ Lightweight |
| Qwen2.5-VL-72B | ~40 GB | ~45 GB | 8K | Excellent | N/A | ❌ Too large |

---

## 5. Success Metrics (Phase 1)
| Metric | Target | Measurement |
|---|---|---|
| GitHub stars | 500 | GitHub repo stars |
| Discord members | 200 | Community Discord |
| X/Twitter engagement | 10K impressions | Analytics |
| User signups (Pro tier) | 50 | Email waitlist |
| Average time savings | 25% reduction in layout time | User survey |

---

## 6. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Models too slow on consumer hardware | Medium | High | Start with 8B models, optimize for RTX 4090 |
| KiCad plugin API limitations | Medium | Medium | Use pcbnew Python API; fallback to .kicad_pcb file parsing |
| Competition from Flux.ai adds local mode | Low | High | Differentiate on sovereign/security + open-core |
| User trust in AI routing suggestions | High | Medium | Show confidence scores + always require user approval |

---

## 7. Next Steps
1. Create repo: `nexus-eda/nexus-eda-kicad-plugin`
2. Bootstrap with `cargo new --lib` or Python KiCad plugin template
3. Set up GitHub Actions CI (lint + test + release)
4. Draft Phase 2 spec (cloud collaboration, autonomous routing)