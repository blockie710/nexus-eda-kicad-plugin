# Phase 2-5 Roadmap: Nexus-EDA Agentic EDA Platform

**Status:** Planning (Phase 1 Complete)  
**Lead:** blockie  
**Timeline:** 12 months (Phases 2-5)  
**Objective:** Build a comprehensive local AI agentic EDA platform with sovereign data capabilities, following the Phase 1 scaffold (KiCad plugin, netlist parsing, LLM integration, GUI).

---

## Phase Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    NEXUS-EDA AGENTIC EDA                        │
├─────────────────────────────────────────────────────────────────┤
│ Phase 2: Agent Orchestration & Multi-Agent EDA Flow (3 months)  │
│ Phase 3: 3D Viewer + Physics Validation (3 months)              │
│ Phase 4: Sovereign Data Architecture (3 months)                 │
│ Phase 5: SaaS Launch & Market Entry (3 months)                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 2: Agent Orchestration & Multi-Agent EDA Flow
**Timeline:** Months 4-6 | **Goal:** Multi-agent DRC + routing assistant

### Agent Assignments & Model Matrix

| Agent | Specialty | Assigned Model | Rationale |
|-------|-----------|----------------|-----------|
| **nexus-llm** (W2 core) | Primary LLM inference | Qwen3-Coder 32B Q4 (~18GB) | Coding + reasoning on 24GB VRAM |
| **nexus-netlist** (W3) | Netlist parsing & analysis | Qwen2.5-Coder 7B Q4 (~6GB) | Fast, lightweight for repetitive parsing |
| **nexus-drc** | DRC rule validation | Llama-3.1-8B Q4 (~7GB) | Logical reasoning, good for rule evaluation |
| **nexus-router** | Trace routing suggestions | DeepSeek-Coder-V2 23B Q4 (~16GB) | Spatial reasoning, path optimization |
| **nexus-bom** | BOM optimization & sourcing | Qwen2.5-Coder 7B Q4 (~6GB) | Catalog cross-referencing, cost analysis |
| **nexus-gui** (W4) | GUI rendering & interaction | TinyLlama 1.1B (~1GB) | Minimal LLM for UI text/labels |
| **nexus-orchestrator** | Multi-agent coordination | Llama-3.1-8B Q4 (~7GB) | Workflow state management |

### Model Selection (Free/OSS Only)

| Model | Params | VRAM (Q4) | Use Case | License | Source |
|-------|--------|-----------|----------|---------|--------|
| **Qwen3-Coder 32B** | 32B | ~18-20GB | Primary LLM (coding, reasoning) | Qwen2.5 | HuggingFace |
| **Qwen2.5-Coder 7B** | 7B | ~5-6GB | Fast agent tasks (autocomplete, parsing) | Qwen2.5 | HuggingFace |
| **DeepSeek-Coder-V2 23B** | 23B | ~14-16GB | Spatial/reasoning tasks (routing) | MIT | HuggingFace |
| **DeepSeek-R1-Distill 7B** | 7B | ~5-6GB | Math/reasoning (DRC calculations) | MIT | HuggingFace |
| **Qwen2.5-VL 7B** | 7B | ~6-7GB | Vision (3D board analysis) | Qwen2.5 | HuggingFace |
| **Llama 3.1 8B** | 8B | ~6-7GB | Orchestration, guardrail checks | Llama 3.1 | Meta |
| **TinyLlama 1.1B** | 1.1B | ~1GB | GUI labels, minimal tasks | Apache 2.0 | TinyLlama |

### Tasks
- [ ] **T2-W5.1**: Set up AutoGen multi-agent orchestration framework
- [ ] **T2-W5.2**: Create DRC agent — integrate pcbnew DRC API, parse violations
- [ ] **T2-W5.3**: Create routing agent — net topology analysis, trace path suggestions
- [ ] **T2-W6.1**: Create BOM optimizer agent — LCSC/JLCPCB catalog cross-reference
- [ ] **T2-W6.2**: Implement agent confidence scoring (never auto-commit changes)
- [ ] **T2-W6.3**: Human-in-loop approval gates for all agent actions
- [ ] **T2-W7**: Integration testing — full workflow: load board → analyze → suggest → write back
- [ ] **T2-W8**: Publish v0.2.0 to GitHub + announce on r/PCB

---

## Phase 3: 3D Viewer + Physics Validation
**Timeline:** Months 7-9 | **Goal:** Native 3D PCB rendering + SI/PI analysis

### Agent Assignments

| Agent | Specialty | Assigned Model |
|-------|-----------|----------------|
| **nexus-3d-viewer** | DX12/Vulkan rendering | Qwen2.5-VL 7B Q4 (vision for 3D analysis) |
| **nexus-si-pi** | Signal/power integrity | DeepSeek-R1-Distill 7B (math/reasoning) |
| **nexus-thermal** | Thermal analysis | Llama-3.1-8B Q4 (reasoning) |
| **nexus-manufacturing** | DFM/DFA checks | Qwen2.5-Coder 7B Q4 |

### Tasks
- [ ] **T3-W9.1**: 3D PCB viewer — DX12/Vulkan multi-canvas rendering (leveraging NBS experience)
- [ ] **T3-W9.2**: Signal integrity analyzer — impedance matching, crosstalk detection
- [ ] **T3-W10.1**: Power integrity checker — voltage drop, decoupling analysis
- [ ] **T3-W10.2**: Thermal hotspot detector — component power dissipation modeling
- [ ] **T3-W11.1**: Manufacturability checker — JLCPCB/PCBWay DRC compatibility
- [ ] **T3-W11.2**: Zero-copy integration with NBS rendering pipeline
- [ ] **T3-W12**: Integration testing + publish v0.3.0
- [ ] **T3-W13-W14**: Community feedback iteration

---

## Phase 4: Sovereign Data Architecture
**Timeline:** Months 10-12 | **Goal:** NDA-safe closed-loop architecture (SABLE-inspired)

### Agent Assignments

| Agent | Specialty | Assigned Model |
|-------|-----------|----------------|
| **nexus-sovereign** | Sovereign data boundary | Llama-3.1-8B Q4 (minimal, trusted) |
| **nexus-scrubber** | PDK/path/data scrubbing | Qwen2.5-Coder 7B Q4 |
| **nexus-encrypt** | Encryption key management | TinyLlama 1.1B (minimal LLM) |
| **nexus-compliance** | GDPR/ITAR/ISO compliance | DeepSeek-R1-Distill 7B |

### Tasks
- [ ] **T4-W15.1**: Implement SABLE-inspired 28 scoped entry points (strip PDK, paths, models)
- [ ] **T4-W15.2**: Build encrypted local storage for design data (AES-256)
- [ ] **T4-W15.3**: Non-training guarantee — audit all data paths for leakage prevention
- [ ] **T4-W16.1**: On-prem deployment package — Docker + local model serving
- [ ] **T4-W16.2**: GDPR compliance module — data export/deletion APIs
- [ ] **T4-W17.1**: SSO/SAML integration (Enterprise tier)
- [ ] **T4-W17.2**: ITAR compliance audit trail (Defense Enterprise tier)
- [ ] **T4-W18**: Publish v1.0.0 — "Nexus-EDA Enterprise" with sovereign data
- [ ] **T4-W19-W20**: Beta enterprise onboarding (3-5 defense/aerospace companies)

---

## Phase 5: SaaS Launch & Market Entry
**Timeline:** Months 13-15 | **Goal:** Revenue-generating product with paid tiers

### Agent Assignments

| Agent | Specialty | Assigned Model |
|-------|-----------|----------------|
| **nexus-marketing** | X/Twitter growth, content | TinyLlama 1.1B (minimal, cost-efficient) |
| **nexus-support** | Customer support automation | Qwen2.5-Coder 7B Q4 |
| **nexus-analytics** | Usage analytics, metrics | Llama-3.1-8B Q4 |
| **nexus-billing** | Stripe integration, billing | TinyLlama 1.1B (minimal, trusted) |

### Tasks
- [ ] **T5-W21.1**: Stripe billing integration — subscription tiers (Free, Maker $19/mo, Pro $49/mo, Enterprise custom)
- [ ] **T5-W21.2**: Customer support automation — ticket routing, FAQ bot
- [ ] **T5-W22.1**: Marketing launch — X/Twitter campaign in buildapc/AI-agents/DSP/audio niche
- [ ] **T5-W22.2**: Documentation site — setup with GitHub Pages / Hugo
- [ ] **T5-W23.1**: YouTube tutorial series — "Building PCBs with AI"
- [ ] **T5-W23.2**: Discord community server setup
- [ ] **T5-W24**: First paid customer acquisition target (3 enterprises + 50 pro subscribers)
- [ ] **T5-W25-W26**: Post-launch stabilization + feedback iteration

---

## Cross-Phase Considerations

### License Compatibility Matrix (Updated)
| Component | License | Commercial Use | Notes |
|-----------|---------|----------------|-------|
| Core engine | Apache 2.0 | ✅ | |
| Qwen3/Qwen2.5 models | Qwen License | ✅ | |
| DeepSeek models | DeepSeek License | ⚠️ | MIT for code, check model weight restrictions |
| Llama 3.1 | Llama 3.1 | ⚠️ | Commercial OK for <1M users |
| SABLE paper | CC BY | ✅ | Reference architecture |
| AutoGen | MIT | ✅ | |
| LangGraph | MIT | ✅ | |
| OpenClaw | Apache 2.0 | ✅ | |

### Performance Targets (Phase 2+)
| Operation | Target | Feasible? |
|-----------|--------|-----------|
| LLM inference (32B Q4) | <500ms/token | ✅ (RTX 4090) |
| Multi-agent DRC (10 rules) | <500ms | ✅ |
| 3D rendering update | <33ms | ✅ (DX12/Vulkan) |
| SI/PI analysis | <2s | ✅ |
| Sovereign data scrub | <100ms | ✅ |
| Cloud sync (encrypted) | <1s/batch | ✅ |

### Risk Assessment (Updated)
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Firecrawl rate limits on research | Medium | Low | Cache all research, use direct API calls |
| Model hallucination in circuit design | High | High | Verification layer, human-in-loop, never auto-commit |
| gemma4:12b unsuitable for agent tasks | High | High | Only use laguna-s-2.1:free for research; gemma4 for light tasks only |
| License conflicts (DeepSeek) | Medium | Medium | Audit before each release; prefer Qwen/MIT licensed models |
| Enterprise sales cycle >6 months | Medium | High | Start with pro/self-serve, add enterprise later |

---

## Next Immediate Actions

1. **Set up agent profiles** in Hermes with optimal free model assignments (this document)
2. **Create Phase 2 kanban tasks** (T2-W5.1 through T2-W8.3)
3. **Dispatch Phase 2 tasks** to appropriate agent profiles using laguna-s-2.1:free
4. **Add CI test pipeline** — ensure Phase 2 code follows W1-W4 testing patterns
5. **Create .hermes/profiles/eda-agents.yaml** — agent profile configuration
