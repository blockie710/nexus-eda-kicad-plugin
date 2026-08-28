# Changelog

All notable changes to this project will be documented in this file.

## [0.2.0] - 2026-08-26

### Added
- Agent orchestration framework with multi-agent EDA flow
- Netlist parsing and analysis engine (KiCad S-expression parser)
- DRC rule validation agent — integrates pcbnew DRC API
- Trace routing suggestions agent — net topology analysis and path proposals
- BOM optimization and sourcing agent — LCSC/JLCPCB catalog cross-reference
- GUI integration with Dear ImGui-based netlist viewer
- Confidence scoring for all agent suggestions (never auto-commits changes)
- Human-in-loop approval gates for agent actions

### Changed
- Refactored core engine to use lock-free SPSC ring buffers for real-time safety
- Improved netlist parser performance (~35% faster on large boards)
- Enhanced CLI interface with structured JSON output

### Notes
- v0.2.0 is the first Phase-2 release: multi-agent orchestration
- All open-source models run entirely on-device (DeepSeek-V3, Llama-3.1-8B)
- Apache 2.0 license for core engine; Pro agent modules are proprietary (Phase 2)

## [0.1.0] - Initial Scaffold

### Added
- Project scaffolding with git repo, CI pipeline, KiCad plugin skeleton
- LLM integration — llama.cpp binding, model loading, prompt templates
- Netlist analyzer — parse .net files, DRC violations
- BOM optimizer — cross-ref KiCad BOM with LCSC/JLCPCB
- Routing agent — suggest trace path for single net
- DRC assistant — pcbnew DRC, summarize violations
- Integration testing — full workflow
- GUI integration — ImGui-based netlist viewer, text/HTML rendering
