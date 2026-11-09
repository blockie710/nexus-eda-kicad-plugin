# Nexus Ecosystem — Phase 1 Kanban Task Cards (P0 + Phase 1)

## Project Code Legend
- **NBS** = Nexus Broadcast Studio
- **CSP** = ConsoleStripPro
- **NXIO** = NexusIO Suite
- **DSP** = Hybrid DSP Engine
- **OBS** = nova-obs-fork
- **EDA** = Nexus-EDA KiCad Plugin
- **NEXUS-ST** = Nexus-Studio (DAW)

---

## NBS — Nexus Broadcast Studio

### NBS-P0-01 — Revert Chain Resolution: Re-apply RT-safe LatencyModel / DynamicsProcessor
* **Priority**: P0 (Blocker)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: C++20 Audio Systems Engineer (nemotron-3-super-120b-a12b → granite-34b-code-instruct)
* **Target Window**: Immediate
* **Dependencies**: Commit `3e769c0` (feat audio), commit `32c3788` (revert), commit `8fda757` (reapply) on `nexus-broadcast-studio` branch `ci/repo-audit-hygiene`
* **Description & Scope**: The revert chain at `32c3788` rolled back commit `8fda757` (Reapply). The reapply (`8fda757`) contains 185 insertions into `include/nexus/AudioCore.hpp` adding `LatencyModel` (lines 130–199), `DynamicsProcessor` (lines 208–230), `GainReductionBus` (lines 235–249), `DynamicsBlock` (lines 246–249), and `ProcessAudioStatsAVX2` (lines 268–337). The current HEAD (`7f05cfa`) already contains `8fda757`'s content — verify that the reapply is stable, the G7 gate passes on the audio TUs that include this header, and that `LatencyModel`/`DynamicsProcessor` are wired into `AudioEngine.cpp` and `AudioCore.hpp` correctly.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `python tools/rt_invariant_gate.py .` exits 0 (0 violations across 6+ audio TUs) when run from repo root with HEAD
  - [ ] `git diff 32c3788 8fda757 -- include/nexus/AudioCore.hpp` produces zero conflicts when cherry-picked to current HEAD
  - [ ] `LatencyModel` constructor is invoked in `src/audio/AudioEngine.cpp` (grep for `LatencyModel` in AudioEngine.cpp, min 1 match)
  - [ ] `DynamicsProcessor` is instantiated and `processBlockPeak()` is called on the render path (grep in AudioEngine.cpp, min 1 match)
  - [ ] `GainReductionBus::publish()` / `consume()` pattern is present in AudioEngine render callback (grep, min 2 matches)

---

### NBS-P0-02 — Populate NBS_AUDIT_INTEGRATION.patch
* **Priority**: P0 (Blocker)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: C++ Build Engineer (granite-8b-code-instruct)
* **Target Window**: Immediate
* **Dependencies**: Phase 1 gap analysis report in `_audit_reports/Phase1_GapAnalysis.md`, G7 gate (`tools/rt_invariant_gate.py`)
* **Description & Scope**: The audit report states `NBS_AUDIT_INTEGRATION.patch` is 0 bytes on master — a placeholder never populated. This patch must contain the full Phase 1–3 audit reconciliation: G7 gate results, revert chain resolution summary, RT-safety sign-off for `LatencyModel`/`DynamicsProcessor`, and the updated `ALLOWLIST` entries in `tools/rt_invariant_gate.py`. The patch file must be created at `docs/patches/NBS_AUDIT_INTEGRATION.patch` and referenced from the CMake G7 gate target.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] Patch file `docs/patches/NBS_AUDIT_INTEGRATION.patch` exists and is > 0 bytes (size > 500 bytes)
  - [ ] Patch contains a documented summary of the revert chain: `3e769c0` → `32c3788` (revert) → `8fda757` (reapply), with rationale for each
  - [ ] Patch includes the G7 gate output: `0 violations across audio TUs. PASS`
  - [ ] `tools/rt_invariant_gate.py` ALLOWLIST is updated with any new allowlist entries from the reapply
  - [ ] `CMakeLists.txt` references the patch file path in the `rt_invariant_gate` custom target COMMENT field

---

### NBS-P0-03 — GitLab Package Registry Upload — Provider Credit Fix
* **Priority**: P0 (Blocker)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: DevOps / CI Engineer (nvidia/nemotron-3-super-49b-v1.5)
* **Target Window**: Immediate
* **Dependencies**: GitLab Package Registry CI job in `.gitlab-ci.yml` (`package:windows` job), `CPackRelease.cmake`, `CPackCommercial.cmake`
* **Description & Scope**: Task `t_b62024d8` failed because Ollama Local ran out of credits. The `.gitlab-ci.yml` `package:windows` job (lines 128–152) uses `curl --upload-file` to push to `${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/packages/generic/`. The CI runner needs `CI_JOB_TOKEN` scope access to the Package Registry. The fix is to verify the `PACKAGE_REGISTRY_URL` variable is correctly formed and that the runner has `read_api`/`write_repository` scopes. Switch the provider from `ollama-local` to `nvidia` with model `nvidia/nemotron-3-super-49b-v1.5`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `.gitlab-ci.yml` package:windows job `PACKAGE_REGISTRY_URL` matches the pattern `${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/packages/generic/nexus-broadcast-studio/${CI_COMMIT_TAG}`
  - [ ] `curl --upload-file` command uses `--header "JOB-TOKEN: ${CI_JOB_TOKEN}"` (grep confirms exact string in `.gitlab-ci.yml`)
  - [ ] CI variable `PACKAGE_VERSION` is set to `${CI_COMMIT_TAG}` with `v`-prefix stripped (grep in `.gitlab-ci.yml`)
  - [ ] `CPackRelease.cmake` line 44 `CPACK_INSTALL_CMAKE_PROJECTS` uses `NexusBroadcastStudio` (exact project name from `CMakeLists.txt` `project()` call)
  - [ ] Test upload of an empty dummy file to GitLab Package Registry succeeds (manual `curl` test from runner, exit 0)

---

### NBS-P0-04 — Stray Untracked Files Cleanup (88 files)
* **Priority**: P0 (Blocker)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: Build Hygiene Engineer (granite-8b-code-instruct)
* **Target Window**: Immediate
* **Dependencies**: NBS repo root at `C:\Users\bhogl\Projects\nexus-projects\nexus-broadcast-studio`, `.gitignore`
* **Description & Scope**: The audit identified 88 stray untracked files including `patch.yml`, `nul`, `--scale`, `fix_*.py`, and other build artifacts polluting the working tree. Task `t_35a0beb7` is blocked. The fix is to classify each stray file (build artifact, scratch, legit source), update `.gitignore` to prevent future pollution, and clean the 88 files.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `git status --porcelain --untracked-files=all | wc -l` returns <= 5 untracked items (excluding `.worktrees/`, `build*/` dirs with .gitignore)
  - [ ] `.gitignore` contains entries for: `*.pyc`, `__pycache__/`, `*.tmp`, `nul`, `fix_*.py`, `--*`, `*.bak`, `*.bak2`
  - [ ] No file named `patch.yml` exists in repo root (`ls patch.yml` → not found)
  - [ ] `git status --short` shows no untracked files matching `--scale`, `nul`, or `fix_*.py`
  - [ ] `git clean -nd` (dry-run) shows only expected build dirs (`build/`, `build_clean/`, etc.) as removable

---

### NBS-P0-05 — Fix verification-before-completion Skill Conflict
* **Priority**: P0 (Blocker)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: Hermes Agent Configuration Engineer (granite-8b-code-instruct)
* **Target Window**: Immediate
* **Dependencies**: Forge profile skill directory at `C:\Users\bhogl\AppData\Local\hermes\profiles\forge\skills\`
* **Description & Scope**: 4 tasks (`t_f1ea11ab`, `t_ac3768bb`, `t_ba84f9dd`, `t_35a0beb7`) are blocked because `verification-before-completion` skill is defined in both the global and forge profiles. The forge profile has a duplicate copy at `profiles/forge/skills/verification-before-completion/SKILL.md`. Fix: remove the duplicate from the forge profile to prevent `Error: Unknown skill(s): verification-before-completion`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `profiles/forge/skills/verification-before-completion/SKILL.md` is deleted or renamed
  - [ ] Global `verification-before-completion` skill at `C:\Users\bhogl\AppData\Local\hermes\skills\verification-before-completion/SKILL.md` loads without error
  - [ ] `hermes skills list 2>&1 | grep verification-before-completion` returns exactly one entry
  - [ ] Re-run one blocked task (`t_f1ea11ab`) — it initializes without the "Unknown skill" error

---

### NBS-P0-06 — Fix a2a Toolset in Forge Profile
* **Priority**: P0 (Blocker)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: Hermes Agent Configuration Engineer (granite-8b-code-instruct)
* **Target Window**: Immediate
* **Dependencies**: Forge profile config.yaml, Nexus profile config.yaml
* **Description & Scope**: Forge profile's `platform_toolsets.cli` includes `a2a` which is unrecognized: `Unknown toolsets: a2a`. The forge profile config.yaml at `C:\Users\bhogl\AppData\Local\hermes\profiles\forge\config.yaml` has `platform_toolsets` that must be synchronized with the nexus profile (which already works). The fix is to remove `a2a` from the forge toolset list and ensure it matches nexus.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `profiles/forge/config.yaml` `platform_toolsets.cli` does not contain `a2a` (grep returns 0 matches)
  - [ ] Forge `platform_toolsets` matches nexus profile's toolset list (diff shows no difference)
  - [ ] `hermes agent spawn` on forge profile succeeds with exit code 0 and no "Unknown toolsets" error
  - [ ] Re-run blocked CSP task `t_ac3768bb` — initializes without toolset error

---

### NBS-P1-01 — Generate Unit Tests for AudioEngine
* **Priority**: P1 (High)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: C++ Test Engineer (ibm/granite-34b-code-instruct)
* **Target Window**: Week 1
* **Dependencies**: `src/audio/AudioEngine.cpp`, `include/nexus/AudioEngine.hpp`, G7 gate passing
* **Description & Scope**: Generate CTest-compatible unit tests covering `AudioEngine` class. Tests must validate: LatencyModel integration, DynamicsProcessor instantiation, GainReductionBus publish/consume, and the `ProcessAudioStatsAVX2` AVX2 path. Test file goes to `tests/audio_engine_test.cpp`, registered in `CMakeLists.txt` via `add_executable` + `add_test`. Tests use gtest or assert-based, compiled with `/WX`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `tests/audio_engine_test.cpp` exists with >= 15 test cases
  - [ ] `CMakeLists.txt` registers the test: `add_executable(audio_engine_test tests/audio_engine_test.cpp)` and `add_test(NAME AudioEngineTest COMMAND audio_engine_test)`
  - [ ] `ctest -R AudioEngineTest --output-on-failure` passes (exit 0)
  - [ ] Test coverage of `LatencyModel::getLatencyMs()`, `DynamicsProcessor::processBlockPeak()`, `ProcessAudioStatsAVX2()` — each covered by >= 1 test
  - [ ] G7 RT-invariant gate still passes (0 violations) after test file added

---

### NBS-P1-02 — Generate Unit Tests for AudioRouting
* **Priority**: P1 (High)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: C++ Test Engineer (ibm/granite-34b-code-instruct)
* **Target Window**: Week 1
* **Dependencies**: `src/audio/AudioRouting.cpp`, `include/nexus/AudioRouting.hpp`
* **Description & Scope**: Generate unit tests for `AudioRouting` — the lock-free SPSC ring buffer routing component. Tests must validate: zero-allocation contract on `processAudioBuffer()`, correct signal routing between channels, `std::string` usage only in setup-time `registerSource()` (not on RT path), and thread-safety of the `AudioFrameQueue` lock-free path.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `tests/audio_routing_test.cpp` exists with >= 10 test cases
  - [ ] `CMakeLists.txt` registers the test via `add_test`
  - [ ] `ctest -R AudioRoutingTest --output-on-failure` passes (exit 0)
  - [ ] G7 gate still reports 0 violations after test added
  - [ ] Test asserts that `processAudioBuffer()` does not trigger any `std::string` allocation on the audio-thread path

---

### NBS-P1-03 — Generate Unit Tests for HEAL (HEAL.hpp)
* **Priority**: P1 (High)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: C++ Test Engineer (ibm/granite-34b-code-instruct)
* **Target Window**: Week 1
* **Dependencies**: `include/nexus/HEAL.hpp`, `tools/rt_invariant_gate.py` (HEAL is not in TARGET_FILES but is referenced in the G7 docstring)
* **Description & Scope**: HEAL (Hybrid Encode Accelerated Loop) is the HEAL.cpp fallback encoder mentioned in the commercial audit. Add HEAL to the G7 RT-invariant gate TARGET_FILES list and generate unit tests covering HEAL block processing, zero-copy texture sharing pipeline interaction, and the AV1/HEVC encode path contract.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `tools/rt_invariant_gate.py` TARGET_FILES includes `"src/encoder/HEAL.cpp"` and `"include/nexus/HEAL.hpp"`
  - [ ] `tests/heal_test.cpp` exists with >= 8 test cases
  - [ ] `ctest -R HealTest --output-on-failure` passes (exit 0)
  - [ ] G7 gate scans HEAL.cpp and reports 0 violations
  - [ ] Test validates HEAL encode path does not call `new`/`malloc` on the encode hot path

---

### NBS-P1-04 — Generate Unit Tests for CdnFailoverEngine
* **Priority**: P1 (High)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: C++ Test Engineer (ibm/granite-34b-code-instruct)
* **Target Window**: Week 1
* **Dependencies**: `include/nexus/CdnFailoverEngine.hpp`, `srt_transport_test.cpp`, `wan_failover_test.cpp`
* **Description & Scope**: Generate unit tests for the CdnFailoverEngine — the failover logic that routes SRT/WebRTC/WHIP streams through redundant paths. Tests must cover: failover trigger conditions, path-switching latency (< 50ms), recovery from simulated CDN outage, and zero-allocation contract on the streaming hot path.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `tests/cdn_failover_test.cpp` exists with >= 6 test cases
  - [ ] `CMakeLists.txt` registers the test via `add_test`
  - [ ] `ctest -R CdnFailoverTest --output-on-failure` passes (exit 0)
  - [ ] Test covers failover from primary SRT to backup WebRTC path
  - [ ] Failover latency < 50ms asserted in at least 1 test case

---

### NCS-P1-05 — Update ALLOWLIST in rt_invariant_gate.py for Reapplied AudioCode
* **Priority**: P1 (High)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: RT-Safety Engineer (granite-8b-code-instruct)
* **Target Window**: Week 1
* **Dependencies**: `tools/rt_invariant_gate.py`, `include/nexus/AudioCore.hpp` (after reapply of `8fda757`)
* **Description & Scope**: The reapplied `LatencyModel`/`DynamicsProcessor` code in `AudioCore.hpp` uses `std::array` and `std::atomic` (RT-safe), but the `AdaptiveRateControl.hpp` change in `8fda757` may introduce new tokens. Update the ALLOWLIST and TARGET_FILES to cover any new non-RT usages and ensure the gate does not false-positive on the reapplied code.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `python tools/rt_invariant_gate.py .` exits 0 with HEAD
  - [ ] ALLOWLIST in `rt_invariant_gate.py` includes entries for `AudioCore.hpp` if any allowlisted patterns exist (e.g., `#include <new>`, `= delete`, `new (_p)`)
  - [ ] No false positives on `LatencyModel`, `DynamicsProcessor`, `GainReductionBus`, `ProcessAudioStatsAVX2` methods
  - [ ] G7 gate output: `[G7] RT-invariant gate: 0 violations across audio TUs. PASS`

---

## CSP — ConsoleStripPro

### CSP-P0-01 — Add JUCE FetchContent Fallback to CMakeLists.txt
* **Priority**: P0 (Blocker)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: C++ Build Engineer (ibm/granite-34b-code-instruct)
* **Target Window**: Immediate
* **Dependencies**: `CMakeLists.txt` (root), `JUCE/` directory (currently empty)
* **Description & Scope**: The audit states "JUCE vendor directory empty — No git submodule, no FetchContent." The current CMakeLists.txt (lines 13–29) checks `if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/JUCE/CMakeLists.txt")` and falls back to `FetchContent_Declare(juce GIT_REPOSITORY https://github.com/juce-framework/JUCE.git GIT_TAG 8.0.0)`. However, the `JUCE/` directory exists but is empty (no `CMakeLists.txt`), so the `EXISTS` check fails silently and FetchContent must run. Verify that FetchContent actually works in the build (cmake configure resolves JUCE 8.0.0), and pin the exact JUCE commit SHA for reproducibility.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `cmake -B build -S .` exits 0 and successfully resolves JUCE via FetchContent
  - [ ] `.gitmodules` is created or updated with JUCE submodule reference if using submodule fallback
  - [ ] `CMakeLists.txt` line 26 `GIT_TAG 8.0.0` is changed to a pinned commit SHA (e.g., `GIT_TAG <40-char SHA>`)
  - [ ] `cmake -B build -S . 2>&1 | grep "FetchContent.*juce"` shows JUCE downloading
  - [ ] Build completes: `cmake --build build --config Release` exits 0

---

### CSP-P0-02 — Fix Stray Artifact `.gitignore` (88 untracked files)
* **Priority**: P0 (Blocker)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: Build Hygiene Engineer (granite-8b-code-instruct)
* **Target Window**: Week 1
* **Dependencies**: `C:\Users\bhogl\Projects\nexus-projects\ConsoleStripPro\.gitignore`
* **Description & Scope**: 88 stray untracked files including `patch.yml`, `nul`, `--scale`, `fix_*.py`. These pollute the working tree and block task `t_35a0beb7`. Audit each file, classify (build artifact/scratch/important), add `.gitignore` rules, and clean.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `git status --porcelain --untracked-files=all | wc -l` returns <= 3 untracked items
  - [ ] `.gitignore` contains: `*.pyc`, `__pycache__/`, `*.tmp`, `nul`, `--*`, `fix_*.py`, `*.bak`
  - [ ] No file named `patch.yml` in repo root
  - [ ] No files with names starting with `--` in repo root
  - [ ] `git clean -nd` shows only expected build dirs as removable

---

### CSP-P0-03 — Resolve Duplicate verification-before-completion Skill
* **Priority**: P0 (Blocker)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: Hermes Agent Configuration Engineer (granite-8b-code-instruct)
* **Target Window**: Immediate
* **Dependencies**: Forge profile skill directory
* **Description & Scope**: Same as NBS-P0-05 — the `verification-before-completion` skill is duplicated in the forge profile, causing `Error: Unknown skill(s)` on CSP board tasks `t_f1ea11ab`, `t_ac3768bb`, `t_ba84f9dd`, `t_35a0beb7`. Remove the forge-profile duplicate.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] Forge profile `verification-before-completion` skill directory deleted
  - [ ] `hermes skills list | grep verification` returns exactly 1 entry
  - [ ] Blocked CSP task `t_f1ea11ab` initializes without "Unknown skill" error
  - [ ] Blocked CSP task `t_ac3768bb` initializes without "Unknown skill" error

---

### CSP-P0-04 — Fix a2a Toolset in Forge Profile (CSP Impact)
* **Priority**: P0 (Blocker)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: Hermes Agent Configuration Engineer (granite-8b-code-instruct)
* **Target Window**: Immediate
* **Dependencies**: Forge profile config.yaml
* **Description & Scope**: Same as NBS-P0-06 — forge profile has `a2a` in `platform_toolsets.cli`. This blocks CSP tasks at init. Synchronize forge toolset with nexus profile.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] Forge config.yaml `platform_toolsets.cli` has no `a2a` entry
  - [ ] Forge toolset matches nexus profile toolset
  - [ ] CSP task `t_ba84f9dd` initializes without "Unknown toolsets: a2a"
  - [ ] CSP task `t_35a0beb7` initializes without toolset error

---

### CSP-P1-01 — Add RT-Safety Regression Tests for DynamicsStage
* **Priority**: P1 (High)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: C++ RT-Safety Engineer (ibm/granite-34b-code-instruct)
* **Target Window**: Week 1
* **Dependencies**: `Source/DSP/DynamicsStage.h`, `Source/DSP/DynamicsStage.cpp`, `tools/rt_invariant_gate.py` (existing in worktrees but not in main CMakeLists)
* **Description & Scope**: The audit roadmap (Phase 2 release plan B1) specifies: "Verify DynamicsStage.h line 637 has no mutex; Confirm lock-free atomics; Run rt_safety_audit.py." Line 636–637 of `DynamicsStage.h` shows `} // namespace DSP` and `} // namespace ConsoleStripPro` — the closing namespace brackets, meaning the class is properly scoped. But we need regression tests that verify: (1) no `std::mutex`/`std::lock_guard` in DynamicsStage, (2) `std::atomic` usage is correct, (3) the `SidechainFilter`/`EnvelopeFollower`/`GainComputer`/`GainSmoother` chain is lock-free. The `rt_safety_audit.py` exists in worktrees but is not integrated into the main CMakeLists.txt.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `tools/rt_safety_audit.py` is copied from worktree to main repo tools/ directory (or created fresh)
  - [ ] `CMakeLists.txt` adds a `rt_safety_audit` target that runs `python tools/rt_safety_audit.py Source/DSP/DynamicsStage.cpp Source/DSP/DynamicsStage.h`
  - [ ] Audit verifies zero `std::mutex`, `std::lock_guard`, `std::condition_variable` in DynamicsStage (exit 0)
  - [ ] Audit confirms `std::atomic` usage in `ParameterSmoothing` and `LockFreeBridge` classes (at least 2 atomic fields verified)
  - [ ] Test file `tests/dynamics_stage_rt_test.cpp` created with >= 5 assertions on lock-free behavior

---

### CSP-P1-02 — Add Standalone Unit Test Harness (CTest)
* **Priority**: P1 (High)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: C++ Test Engineer (ibm/granite-34b-code-instruct)
* **Target Window**: Week 1
* **Dependencies**: `CMakeLists.txt`, JUCE FetchContent resolution (CSP-P0-01)
* **Description & Scope**: The audit states "ConsoleStripPro: 0 unit test executables. Validation via external pluginval tool." Add a CTest-based unit test harness. JUCE provides `juce_unit_tests` module for test registration. Create at least one test executable that validates the DSP model math (saturation models, crosstalk, DC blocking, anti-aliasing filter) against the JSFX reference values documented in `DSP_AUDIT.md`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `CMakeLists.txt` includes `juce_add_tests(ConsoleStripProTests)` or equivalent `add_executable` + `add_test`
  - [ ] `tests/DSP_AuditTests.cpp` exists with >= 20 test cases covering saturation models, crosstalk, DC blocking, anti-aliasing
  - [ ] `tests/test_main.cpp` contains `TestRunner` instantiation
  - [ ] `ctest --output-on-failure` from build directory runs DSP_AuditTests and passes
  - [ ] At least 3 saturation model tests validate exact float parity against JSFX formulas from DSP_AUDIT.md

---

### CSP-P1-03 — Fix Global Sag Scaling in ConsoleDSP
* **Priority**: P1 (High)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: C++ DSP Engineer (ibm/granite-34b-code-instruct)
* **Target Window**: Week 2
* **Dependencies**: `Source/DSP/ConsoleDSP.h` (`computeRailVoltage`), `Source/PluginProcessor.cpp`
* **Description & Scope**: DSP_AUDIT.md (lines 211–213, 97) identifies a critical bug: JSFX computes `global_project_sag = min(0.30, gmem[0] * sag_active)` where `sag_active = sag_coeff[active_model]`, but C++ uses raw `globalSag` without scaling by `sagCoeff` or clamping to 0.30. Fix in `ConsoleDSP.h` `computeRailVoltage` to multiply `globalSag` by `sagCoeff` and clamp to 0.30f, matching JSFX.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `ConsoleDSP.h` `computeRailVoltage()` multiplies `sharedState.globalSag` by `sagCoeff` and clamps to `0.30f`
  - [ ] Unit test `tests/DSP_AuditTests.cpp` includes `PSUSag_GlobalSagScaling` test that validates `globalSag` is scaled and clamped to 0.30
  - [ ] Test passes: `ctest -R DSP_AuditTests` exits 0
  - [ ] G7 RT-invariant gate still passes (no new alloc/mutex introduced in fix)

---

### CSP-P1-04 — Run pluginval strict-10 Validation
* **Priority**: P1 (High)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: C++ Plugin Validation Engineer (nvidia/nemotron-3-super-120b-a12b)
* **Target Window**: Week 2
* **Dependencies**: Pluginval tool, built VST3 plugin from CSP-P0-01
* **Description & Scope**: The audit roadmap Phase C1 specifies: "Run pluginval strict-10 on VST3." ConsoleStripPro's CMakeLists.txt targets `FORMATS VST3` only. Run pluginval in strict-10 mode against the built `.vst3` to validate crash isolation, state handling, and parameter automation. This is the first time a formal pluginval run is attempted — no prior test executables exist.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] VST3 plugin builds: `cmake --build build --target ConsoleStripPro` exits 0
  - [ ] pluginval strict-10 validation runs on the built `.vst3` bundle
  - [ ] pluginval report saved to `docs/validation/pluginval_strict10_csp_report.txt`
  - [ ] Report shows >= 20/20 strict-10 checks passing (or specific failures documented)
  - [ ] AVX2 vs scalar parity verified (pluginval `AudioProcessor` test passes)

---

### CSP-P1-05 — Merge audit-and-improvement-08222026 Branch
* **Priority**: P1 (High)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: Git Workflow Engineer (nvidia/nemotron-3-super-49b-v1.5)
* **Target Window**: Week 2
* **Dependencies**: `audit-and-improvement-08222026` branch in ConsoleStripPro repo
* **Description & Scope**: The audit roadmap specifies: "Review audit-and-improvement-08222026 branch; Merge to main; Archive branch." This branch contains the RT-safety fixes, DSP audit corrections, and pluginval validation artifacts. Merge via PR with review, then archive.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `git diff audit-and-improvement-08222026 master --stat` shows the files changed (no more than 20 files)
  - [ ] Merge commit exists: `git log master --oneline | grep "Merge.*audit-and-improvement"`
  - [ ] Branch is renamed to `archive/audit-and-improvement-08222026` (git branch -m)
  - [ ] `git branch -a` shows archived branch exists
  - [ ] `DSP_AUDIT.md` CRITICAL FIXES section (lines 209–221) has tracked issues resolved (issues 1–3 marked done)

---

## NXIO — NexusIO Suite

### NXIO-P1-01 — Add RT Gate to .gitlab-ci.yml as rt_gate Stage
* **Priority**: P1 (High)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: DevOps / CI Engineer (nexus/nemotron-3-super-49b-v1.5)
* **Target Window**: Week 1
* **Dependencies**: `nexusio_rt_invariant_gate.py` exists in worktrees, `.gitlab-ci.yml` in main repo
* **Description & Scope**: The audit states "NexusIO: RT gate implemented (mirrors NBS pattern), done as of task t_3f589b3b" but Phase 2 roadmap A5 says: "Add nexusio to .gitlab-ci.yml rt_gate stage." The `nexusio_rt_invariant_gate.py` exists in worktree `t_phase_01` but is not referenced in the main repo's `.gitlab-ci.yml`. Need to add an `rt_gate` stage that runs the gate.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `tools/nexusio_rt_invariant_gate.py` exists in main repo (copied from `t_phase_01` worktree)
  - [ ] `.gitlab-ci.yml` has a `rt_gate` stage definition (grep for `rt_gate`)
  - [ ] A CI job `rt_gate:nexusio` runs `python3 tools/nexusio_rt_invariant_gate.py .` and `allow_failure: false`
  - [ ] Gate scans all `src/audio/*.cpp` and `src/common/*.cpp` TUs (verify TARGET_FILES list)
  - [ ] Local run: `python3 tools/nexusio_rt_invariant_gate.py .` exits 0 on clean main

---

### NXIO-P1-02 — Generate Unit Tests for nexusio_asio.cpp
* **Priority**: P1 (High)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: C++ Test Engineer (ibm/granite-34b-code-instruct)
* **Target Window**: Week 1
* **Dependencies**: `src/audio/nexusio_asio.cpp`, `include/nexusio/` headers
* **Description & Scope**: The audit roadmap A1 specifies generating unit tests for `nexusio_asio.cpp`. This file implements the ASIO COM interface for lock-free audio I/O. Tests must validate: ASIO initialization, buffer size queries, lock-free ring buffer contract on the audio callback path, and zero-allocation on `bufferSwitch()`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `tests/asio_interface_test.cpp` exists with >= 12 test cases
  - [ ] `CMakeLists.txt` registers the test: `add_executable(nexusio_asio_test tests/asio_interface_test.cpp)` + `add_test`
  - [ ] `ctest -R AsioInterfaceTest --output-on-failure` passes (exit 0)
  - [ ] Test validates ASIO `bufferSwitch()` callback does not allocate (mocked ASIO host)
  - [ ] RT gate still passes after test addition (0 violations)

---

### NXIO-P1-03 — Generate Unit Tests for SpscShmRingBuffer
* **Priority**: P1 (High)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: C++ Test Engineer (ibm/granite-34b-code-instruct)
* **Target Window**: Week 1
* **Dependencies**: `src/common/SpscShmRingBuffer.cpp` or equivalent, `include/nexusio/`
* **Description & Scope**: The audit roadmap A3 specifies generating tests for `SpscShmRingBuffer`. This is the single-producer single-consumer shared-memory ring buffer used for zero-copy audio transport between NBS and NexusIO. Tests must validate: push/pop correctness, wrap-around behavior, full/empty detection, lock-free contract (no `std::mutex`/`std::atomic` flag misuse), and zero-allocation on the hot path.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `tests/spsc_ringbuffer_test.cpp` exists with >= 10 test cases
  - [ ] `CMakeLists.txt` registers the test via `add_test`
  - [ ] `ctest -R SpscRingBufferTest --output-on-failure` passes (exit 0)
  - [ ] Test covers wrap-around at buffer boundary (push past capacity, verify wrap)
  - [ ] Test asserts zero heap allocations in push/pop hot path (using allocation tracker or static analysis)

---

### NXIO-P1-04 — Generate Unit Tests for matrix_router.cpp
* **Priority**: P1 (High)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: C++ Test Engineer (ibm/granite-34b-code-instruct)
* **Target Window**: Week 1
* **Dependencies**: `src/audio/matrix_router.cpp`, `include/nexusio/`
* **Description & Scope**: The audit roadmap A3 specifies generating tests for `matrix_router.cpp`. This implements the SKA (Spatial Keyboard Array) matrix routing with `TelemetryRelay.hpp` (which previously included `<mutex>` but was resolved). Tests must validate: route table correctness, lock-free route switching, and zero-allocation on the signal path.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `tests/matrix_router_test.cpp` exists with >= 8 test cases
  - [ ] `CMakeLists.txt` registers the test via `add_test`
  - [ ] `ctest -R MatrixRouterTest --output-on-failure` passes (exit 0)
  - [ ] Test validates that `TelemetryRelay` does not transitively include `<mutex>` on the RT path (grep check in test or CI)
  - [ ] RT gate scans `matrix_router.cpp` and reports 0 violations

---

### NXIO-P1-05 — Cross-check NexusIO RT Gate with NBS RT Gate
* **Priority**: P1 (High)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: RT-Safety Engineer (nvidia/nemotron-3-super-120b-a12b)
* **Target Window**: Week 2
* **Dependencies**: `tools/nexusio_rt_invariant_gate.py` (NXIO-P1-01), `tools/rt_invariant_gate.py` (NBS)
* **Description & Scope**: The audit roadmap C3 specifies: "Cross-check with NBS RT gate." The NexusIO gate (`nexusio_rt_invariant_gate.py`) was done by task `t_3f589b3b` and is supposed to mirror the NBS G7 pattern. Verify that both gates use the same FORBIDDEN tokens, the same allowlist mechanism, and that the TARGET_FILES coverage is aligned for shared transport components (`NexusIOTransportAdapter.cpp` which NBS scans).
* **Acceptance Criteria (Definition of Done)**:
  - [ ] NexusIO gate FORBIDDEN dict matches NBS gate FORBIDDEN dict exactly (diff of regex patterns)
  - [ ] NexusIO gate TARGET_FILES includes `NexusIOTransportAdapter.cpp` (if it exists in NexusIO or NBS)
  - [ ] NexusIO gate ALLOWLIST uses same (file, substring) allowlist pattern as NBS gate
  - [ ] Both gates exit 0 on their respective repos
  - [ ] Cross-repo integration: NBS RT gate does not flag NexusIO's `nexusio_asio.cpp` when both are built together (integration test)

---

## DSP — Hybrid DSP Engine

### DSP-P1-01 — Implement rt_invariant_gate.py for Hybrid DSP Engine
* **Priority**: P1 (High)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: RT-Safety Engineer (nvidia/nemotron-3-super-49b-v1.5)
* **Target Window**: Week 1
* **Dependencies**: `tools/rt_invariant_gate.py` already exists at `hybrid-dsp-engine/tools/` (117 lines, scanned in NBS format)
* **Description & Scope**: The audit states "HybridDSP: No RT gate yet — needs implementation." However, `tools/rt_invariant_gate.py` already exists (117 lines), scanning 9 TUs: `src/audio/AudioEngine.cpp`, `AudioMixer.cpp`, `AudioGraph.cpp`, `WasapiProbe.cpp`, `Oversampling.cpp`, `WdfDiode.cpp`, and headers `AudioEngine.hpp`, `AudioGraph.hpp`, `AudioConfig.hpp`. The `.gitlab-ci.yml` has a `g7_gate` stage (line 67–72) that runs `python3 tools/rt_invariant_gate.py .` but also calls `tools/build_verify.py --gate-only`. Verify the gate is correctly wired, the TARGET_FILES are complete (add `PluginWrapper.hpp` if it has RT-critical code), and the ALLOWLIST covers placement-new in `AudioGraph.cpp`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `python3 tools/rt_invariant_gate.py .` exits 0 (0 violations) run from `hybrid-dsp-engine/`
  - [ ] `.gitlab-ci.yml` `g7_gate` stage has `allow_failure: false` (verify line 71)
  - [ ] TARGET_FILES in `rt_invariant_gate.py` includes all audio TUs that are on the render path (min 6 .cpp files + 3 headers)
  - [ ] ALLOWLIST covers `#include <new>`, `new (_p)`, `= delete` in AudioGraph.cpp
  - [ ] CI job runs: `python3 tools/rt_invariant_gate.py . && python3 tools/build_verify.py --gate-only` (both exit 0)

---

### DSP-P1-02 — Generate Coverage Tests for Oversampling (oversampling.hpp)
* **Priority**: P1 (High)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: C++ Test Engineer (ibm/granite-34b-code-instruct)
* **Target Window**: Week 1
* **Dependencies**: `include/nexus/AudioConfig.hpp` (oversampling config), `src/audio/Oversampling.cpp`, existing `tests/audio_engine_test.cpp`
* **Description & Scope**: The audit roadmap A2 specifies: "Generate coverage for oversampling." The HybridDSP repo has `src/audio/Oversampling.cpp` and references to `oversampling.hpp` in the rt_invariant_gate.py (line 32). Verify that the `std::vector` replacement was done (audit says "done t_a68b34c7"). Generate tests covering: oversampling ratio selection (2x, 4x, 8x), filter coefficient computation, zero-allocation on `process()` method, and SIMD path selection (AVX2 vs scalar).
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `src/audio/Oversampling.cpp` does not use `std::vector` (grep returns 0 matches)
  - [ ] `tests/oversampling_test.cpp` exists with >= 8 test cases
  - [ ] `CMakeLists.txt` registers the test via `add_test`
  - [ ] `ctest -R OversamplingTest --output-on-failure` passes (exit 0)
  - [ ] G7 gate still passes: `python3 tools/rt_invariant_gate.py .` exits 0

---

### DSP-P1-03 — Generate Coverage Tests for WDF Diode (WdfDiode.cpp)
* **Priority**: P1 (High)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: C++ Test Engineer (ibm/granite-34b-code-instruct)
* **Target Window**: Week 1
* **Dependencies**: `src/audio/WdfDiode.cpp`, `src/audio/AudioEngine.cpp`
* **Description & Scope**: The audit mentions "AVX2-based Newton-Raphson for WDF diodes" as completed. Generate tests covering the WDF diode solver: Newton-Raphson convergence, lookup-table accuracy, SIMD vectorization path, and zero-allocation contract on the solve method.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `tests/wdf_diode_test.cpp` exists with >= 6 test cases
  - [ ] `CMakeLists.txt` registers the test via `add_test`
  - [ ] `ctest -R WdfDiodeTest --output-on-failure` passes (exit 0)
  - [ ] Test validates Newton-Raphson converges within 5 iterations for input range [-1.0, 1.0]
  - [ ] G7 gate scans `WdfDiode.cpp` and reports 0 violations

---

### DSP-P1-04 — Generate Coverage Tests for Plugin Wrapper (CLAP/VST3)
* **Priority**: P1 (High)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: C++ Test Engineer (ibm/granite-34b-code-instruct)
* **Target Window**: Week 2
* **Dependencies**: `src/audio/AudioEngine.cpp` (plugin wrapper), CLAP/VST3 SDK integration
* **Description & Scope**: The audit roadmap A1 says "Review existing tests (dsp_tests, phase4_tests, plugin_tests)." The HybridDSP repo has `tests/audio_engine_test.cpp` and `src/audio/AudioEngine.cpp` which mentions plugin wrapper `new()` annotations. Verify `virtual_ipc.cpp` `std::string` fix was applied (audit says "done"), generate tests for the plugin wrapper interface, and add `PluginWrapper.hpp` to the G7 gate TARGET_FILES if it has RT-critical code.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `src/audio/AudioEngine.cpp` `virtual_ipc.cpp` equivalent does not use `std::string` on RT path (grep or audit confirms)
  - [ ] `tests/plugin_wrapper_test.cpp` exists with >= 5 test cases
  - [ ] `CMakeLists.txt` registers the test via `add_test`
  - [ ] `ctest -R PluginWrapperTest --output-on-failure` passes (exit 0)
  - [ ] G7 gate TARGET_FILES includes `src/audio/PluginWrapper.cpp` if it exists (verify via find)

---

## OBS — nova-obs-fork

### OBS-P0-01 — Commit 8 Modified CMakeLists/cmake Files
* **Priority**: P0 (Blocker)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: Git Workflow Engineer (ibm/granite-8b-code-instruct)
* **Target Window**: Immediate
* **Dependencies**: `nova-obs-fork` repo, 8 modified CMakeLists/cmake files uncommitted
* **Description & Scope**: The audit states "8 modified CMakeLists/cmake files uncommitted — Merge artifacts not committed." Tasks `t_e11bc29e` and `t_54fd5ffd` are blocked. The OBS fork is on branch `root` with worktree branches `wt/t_6659017a` and `wt/t_c728e76b`. Commit the 8 modified cmake files with a descriptive message, and ensure CRLF→LF consistency.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `git status --short` shows 0 modified `.cmake`/`.yml` files (all committed)
  - [ ] Commit message: `fix(build): commit 8 modified CMakeLists + cmake files from merge`
  - [ ] Git log shows commit on `root` branch: `git log root --oneline | head -5`
  - [ ] `git diff HEAD~1 HEAD --name-only` lists exactly 8 `.cmake`/`CMakeLists.txt` files
  - [ ] No `--scale` or `nul` files in repo root

---

### OBS-P0-02 — Merge or Archive Pre-stage Audit Branches
* **Priority**: P0 (Blocker)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: Git Workflow Engineer (nvidia/nemotron-3-super-49b-v1.5)
* **Target Window**: Week 1
* **Dependencies**: OBS fork branches `wt/t_6659017a`, `wt/t_c728e76b`, and 5 local + 2 remote pre-stage audit branches
* **Description & Scope**: The audit states "Pre-stage audit branches (5 local + 2 remote) stale — No merge strategy." Task `t_54fd5ffd` is blocked. Determine a merge strategy: either merge audit work into `root` or archive stale branches as read-only snapshots.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] List of all worktree branches: `git branch -a` run, output captured
  - [ ] Audit branches either merged into `root` or tagged as `archive/wt/<name>-stale`
  - [ ] `t_54fd5ffd` task unblocked (can be re-run without branch conflicts)
  - [ ] Merge strategy documented in `docs/audit-branch-strategy.md`
  - [ ] `git branch -a | wc -l` shows <= 3 active branches (root + 2 worktrees)

---

### OBS-P1-01 — Verify vst3-host.cpp:72 Pre-allocated Context
* **Priority**: P1 (High)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: C++ RT-Safety Engineer (nvidia/nemotron-3-super-120b-a12b)
* **Target Window**: Week 1
* **Dependencies**: `vst3-host.cpp` (referenced in audit roadmap A3), NBS RT gate pattern
* **Description & Scope**: The audit roadmap A3 specifies: "Verify vst3-host.cpp:72 pre-allocated context." The OBS fork integrates VST3 hosting via the `OBS_VST3_SDK_PATH` env var. Line 72 of `vst3-host.cpp` should contain a pre-allocated context buffer (no `new`/`malloc` on the audio callback). Verify the pre-allocation pattern, confirm no heap allocation in `processReplacing()` or equivalent, and add to the RT gate scan if not already present.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `vst3-host.cpp` exists in the OBS fork source tree (find path, grep for context)
  - [ ] Line 72 of `vst3-host.cpp` contains pre-allocated context (e.g., `static`/`std::array`/`aligned_storage`)
  - [ ] No `new`/`malloc`/`std::vector` in `processReplacing()` or audio callback method (grep, 0 matches)
  - [ ] OBS fork has an RT-safety audit script (`tools/rt_safety_obs.py` or equivalent)
  - [ ] Audit script exits 0 on the vst3 host code

---

### OBS-P1-02 — Validate OBS_VST3_SDK_PATH Env Var Detection
* **Priority**: P1 (High)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: C++ Build Engineer (ibm/granite-34b-code-instruct)
* **Target Window**: Week 1
* **Dependencies**: OBS fork `CMakeLists.txt`, `OBS_VST3_SDK_PATH` env var
* **Description & Scope**: The audit roadmap B2 specifies: "Validate OBS_VST3_SDK_PATH env var detection." The OBS fork's CMake must detect the VST3 SDK via the `OBS_VST3_SDK_PATH` environment variable. Test that CMake correctly resolves the SDK path, falls back gracefully if unset, and that the VST3 plugin hosting compiles.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `CMakeLists.txt` references `OBS_VST3_SDK_PATH` (grep, min 1 match)
  - [ ] CMake configure succeeds when `OBS_VST3_SDK_PATH` is set to a valid VST3 SDK path
  - [ ] CMake configure produces a warning (not error) when `OBS_VST3_SDK_PATH` is unset
  - [ ] `cmake -S . -B build_test` exits 0 with `OBS_VST3_SDK_PATH` set
  - [ ] Build completes: `cmake --build build_test --parallel` exits 0

---

## EDA — Nexus-EDA KiCad Plugin

### EDA-P1-01 — Create Phase 2 Kanban Tasks (T2-W5.1 through T2-W8)
* **Priority**: P1 (High)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: Technical Program Manager (blockie)
* **Target Window**: Week 1
* **Dependencies**: `references/kanban-tasks.md` (Phase 2 section), `references/eda-phase2-5-plan.md`
* **Description & Scope**: The Phase 2 roadmap in `eda-phase2-5-plan.md` defines 8 tasks (T2-W5.1 through T2-W8) for Agent Orchestration & Multi-Agent EDA Flow. These need to be created as granular Kanban task cards with explicit file references, acceptance criteria, and NIM model assignments per the `Phase2_NIM_AssignmentMatrix.md`. Each task must be ≤ 3 days, single-engineer, with testable AC.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] 8 task cards created in `references/kanban-tasks.md` under "Phase 2 (Kanban Tasks)" section
  - [ ] Each card has: Priority, Phase, Assignee Role, Target Window, Dependencies, Description, Acceptance Criteria
  - [ ] Each card references the NIM model assignment from Phase2b matrix (e.g., `ibm/granite-34b-code-instruct`)
  - [ ] Each card references Nous Portal free model fallback (e.g., `poolside/laguna-s-2.1:free`, `deepseek/deepseek-r1:free`, `meta/llama-4-sonic:free`) per Nous Portal free tier
  - [ ] Each card references specific files: `eda_agents/orchestrator.py`, `src/nexus_eda/drc_agent.py`, `src/nexus_eda/routing_agent.py`, etc.
  - [ ] Each card has ≥ 3 testable acceptance criteria with checkbox format

---

### EDA-P1-02 — Create Phase 3 Kanban Tasks (T3-W9.1 through T3-W14)
* **Priority**: P1 (High)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: Technical Program Manager (blockie)
* **Target Window**: Week 1
* **Dependencies**: `references/kanban-tasks.md` (Phase 3 section), `eda-phase2-5-plan.md` Phase 3
* **Description & Scope**: Create Kanban task cards for the 7 Phase 3 tasks (T3-W9.1 through T3-W14) covering 3D PCB viewer, signal/power/thermal integrity, manufacturability checker, and NBS zero-copy integration. Each references the NIM/Vision/Spatial/Mat model assignments from the Phase 2 matrix.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] 7 task cards created in `references/kanban-tasks.md` under "Phase 3 (Kanban Tasks)" section
  - [ ] Each card has Priority, Phase, Assignee Role, Target Window, Dependencies, Description, AC
  - [ ] Each card references assigned model (e.g., `Qwen2.5-VL 7B Q4`, `DeepSeek-R1-Distill 7B`)
  - [ ] Each card references Nous Portal free model fallback (e.g., `poolside/laguna-s-2.1:free`, `deepseek/deepseek-r1:free`, `meta/llama-4-sonic:free`)
  - [ ] Each card references specific files: `src/nexus_eda/viewer_3d.py`, `src/nexus_eda/si_pi_analyzer.py`, etc.
  - [ ] Each card has ≥ 3 testable acceptance criteria

---

### EDA-P1-03 — Create Phase 4 Kanban Tasks (T4-W15.1 through T4-W20)
* **Priority**: P1 (High)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: Technical Program Manager (blockie)
* **Target Window**: Week 1
* **Dependencies**: `references/kanban-tasks.md` (Phase 4 section), `eda-phase2-5-plan.md` Phase 4
* **Description & Scope**: Create Kanban task cards for the 8 Phase 4 tasks (T4-W15.1 through T4-W20) covering Sovereign Data Architecture (SABLE-inspired 28 scoped entry points), encrypted local storage, non-training guarantee, on-prem Docker deployment, GDPR/ITAR compliance, and enterprise beta onboarding. Each references the minimal/trusted model assignments.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] 8 task cards created in `references/kanban-tasks.md` under "Phase 4 (Kanban Tasks)" section
  - [ ] Each card has Priority, Phase, Assignee Role, Target Window, Dependencies, Description, AC
  - [ ] Each card references assigned model (e.g., `TinyLlama 1.1B`, `Llama 3.1 8B Q4`)
  - [ ] Each card references Nous Portal free model fallback (`poolside/laguna-s-2.1:free`, `deepseek/deepseek-r1:free`, `microsoft/phi-3-medium-128k-instruct:free`)
  - [ ] Each card references specific files or security boundaries
  - [ ] Each card has ≥ 3 testable acceptance criteria

---

### EDA-P1-04 — Create Phase 5 Kanban Tasks (T5-W21.1 through T5-W26)
* **Priority**: P1 (High)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: Technical Program Manager (blockie)
* **Target Window**: Week 1
* **Dependencies**: `references/kanban-tasks.md` (Phase 5 section), `eda-phase2-5-plan.md` Phase 5
* **Description & Scope**: Create Kanban task cards for the 7 Phase 5 tasks (T5-W21.1 through T5-W26) covering SaaS Launch & Market Entry: Stripe billing, customer support automation, X/Twitter marketing campaign, documentation site (Hugo/GitHub Pages), YouTube tutorial series, Discord server, and first paid customer acquisition.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] 7 task cards created in `references/kanban-tasks.md` under "Phase 5 (Kanban Tasks)" section
  - [ ] Each card has Priority, Phase, Assignee Role, Target Window, Dependencies, Description, AC
  - [ ] Each card references assigned model (e.g., `TinyLlama 1.1B`, `Qwen2.5-Coder 7B Q4`)
  - [ ] Each card references Nous Portal free model fallback (`poolside/laguna-s-2.1:free`, `deepseek/deepseek-r1:free`, `microsoft/phi-3-medium-128k-instruct:free`)
  - [ ] Each card references specific deliverables (Stripe tier config, Hugo site repo, YouTube script template)
  - [ ] Each card has ≥ 3 testable acceptance criteria

---

## NEXUS-ST — Nexus-Studio (DAW)

### NEXUS-ST-P1-01 — Initialize Root CMakeLists.txt + CI Template
* **Priority**: P1 (High)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: C++ Build Engineer (nvidia/nemotron-3-super-49b-v1.5)
* **Target Window**: Week 1
* **Dependencies**: `C:\Users\bhogl\Projects\nexus-projects\nexus-studio` (scaffold only), Phase 1 complete
* **Description & Scope**: The audit states "Nexus-Studio: Only documentation + vendor scaffolding. No source code yet (Phase 1 complete)." The Phase 3 roadmap A5–A7 specifies: "Initialize root CMakeLists.txt; Set up zero-alloc lock-free C++20 baseline; Configure CI template." This project needs to mirror the NBS CMakeLists.txt pattern (MSVC `/arch:AVX2 /W4 /WX`, NEXUS_ZERO_ALLOC define, G7 gate integration, CommercialSanitizer, FetchContent for CLAP/VST3 SDKs).
* **Acceptance Criteria (Definition of Done)**:
  - [ ] Root `CMakeLists.txt` exists with `project(NexusStudio VERSION 0.1.0 LANGUAGES CXX)`
  - [ ] MSVC flags configured: `/std:c++20 /permissive- /Zc:preprocessor /W4 /WX /arch:AVX2`
  - [ ] `add_compile_definitions(NEXUS_ZERO_ALLOC=1)` present
  - [ ] `CommercialSanitizer.cmake` included with `NEXUS_COMMERCIAL_CLEAN_BUILD` option
  - [ ] `tools/rt_invariant_gate.py` copied from NBS and G7 gate target registered in CMake
  - [ ] `enable_testing()` present and `.github/workflows/beta-ci.yml` scaffolded (copied from NBS template)

---

### NEXUS-ST-P1-02 — Review REFERENCE_ENGINES.md + License Clean-Room Report
* **Priority**: P1 (High)
* **Phase**: Phase 1: Hardening
* **Assignee Role**: Commercial License Compliance Officer (mistralai/mistral-large-2-instruct)
* **Target Window**: Week 1
* **Dependencies**: `docs/REFERENCE_ENGINES.md`, `docs/LicenseCleanRoom.md`, `COMMERCIAL_LICENSE_AUDIT.md`
* **Description & Scope**: The Phase 3 roadmap A2–A3 specifies reviewing the reference engine documentation and the commercial license clean-room report before writing any DAW source code. This is the critical gate before any C++ is written — the design must be provably separable from JUCE/AAX/VST3 reference implementations to avoid license contamination.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `docs/REFERENCE_ENGINES.md` exists and lists all reference engines inspected (JUCE, AAX, VST3, CLAP, LV2, ARA) with their license tier (Red/Yellow/Green)
  - [ ] `docs/LicenseCleanRoom.md` exists with a clean-room declaration: no code copied from proprietary SDKs, only API contracts referenced via header-only glue
  - [ ] `COMMERCIAL_LICENSE_AUDIT.md` is updated with Nexus-Studio DAW-specific obligations (CLAP dynamic linking, no GPL transitive deps)
  - [ ] At least 2 reference engines are classified as "Green" (permissive) and used as primary reference
  - [ ] Clean-room sign-off: `docs/LicenseCleanRoom.md` contains a dated signature block

---

## Phase 2 (Kanban Tasks) — Detailed Task Cards

### EDA-T2-W5.1 — Set Up AutoGen Multi-Agent Orchestration Framework
* **Priority**: P2 (Medium)
* **Phase**: Phase 2: Agent Orchestration & Multi-Agent EDA Flow
* **Assignee Role**: AI Orchestration Engineer (Qwen3-Coder 32B Q4 / `poolside/laguna-s-2.1:free` fallback)
* **Target Window**: Week 5 (Month 4)
* **Dependencies**: Phase 1 complete, `eda_agents/` directory scaffolded, `requirements.txt` for AutoGen
* **Description & Scope**: Set up the AutoGen multi-agent orchestration framework for the EDA plugin. This framework coordinates the `nexus-drc`, `nexus-router`, `nexus-bom`, and `nexus-orchestrator` agents. Install AutoGen (`pip install autogen-agentchat`), create `eda_agents/orchestrator.py` with a `GroupChatManager` that routes tasks between specialist agents, and configure the `nexus-llm` agent as the primary LLM inference backend using Qwen3-Coder 32B Q4 on the RTX 4090. The orchestration layer must support confidence scoring and human-in-loop approval gates before any pcbnew API write calls.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `pip install autogen-agentchat numpy` succeeds (exit 0) in `eda_agents/` venv
  - [ ] `eda_agents/orchestrator.py` exists with `GroupChatManager` class managing >= 4 agent roles (drc, router, bom, orchestrator)
  - [ ] `eda_agents/agents/nexus_llm.py` configured with Qwen3-Coder 32B Q4 model path (verify `model_path` field set to `./models/qwen3-coder-32b`)
  - [ ] `eda_agents/agents/nexus_llm.py` has fallback to `poolside/laguna-s-2.1:free` via Nous Portal API when local VRAM < 18GB
  - [ ] Orchestration test: `python eda_agents/orchestrator.py --dry-run --board test_data/simple_board.kicad_pcb` exits 0 and prints agent routing log without errors

---

### EDA-T2-W5.2 — Create DRC Agent — Integrate pcbnew DRC API
* **Priority**: P2 (Medium)
* **Phase**: Phase 2: Agent Orchestration & Multi-Agent EDA Flow
* **Assignee Role**: C++/Python EDA Engineer (Qwen2.5-Coder 7B Q4 / `deepseek/deepseek-r1:free` fallback)
* **Target Window**: Week 5 (Month 4)
* **Dependencies**: EDA-T2-W5.1 (orchestration framework), pcbnew Python API access, `src/nexus_eda/drc_agent.py`
* **Description & Scope**: Create the `nexus-drc` agent that integrates the KiCad pcbnew Python API to parse DRC violations. The agent reads pcbnew's `GetBoard()` → `GetDesignRulesCheck()` → violation list, categorizes them (copper clearance, track width, via coverage, unrouted nets), and reports via a structured JSON schema. File: `src/nexus_eda/drc_agent.py`. Uses Qwen2.5-Coder 7B Q4 for rule reasoning on violations; falls back to `deepseek/deepseek-r1:free` for math-heavy DRC calculations (e.g., impedance mismatch). Must achieve <500ms for 10-rule batch.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `src/nexus_eda/drc_agent.py` exists with `DRCAgent` class subclassing `eda_agents/orchestrator.py:BaseAgent`
  - [ ] `DRCAgent.parse_violations(board)` returns a JSON-serializable list with fields: `rule`, `layer`, `net`, `x`, `y`, `severity`
  - [ ] `tests/drc_agent_test.py` has >= 10 test cases covering clearance, width, via, unrouted violations
  - [ ] `pytest tests/drc_agent_test.py -x -q` passes (exit 0, all 10 tests)
  - [ ] DRC batch of 10 rules completes in < 500ms (assert in test: `time.time() < 0.5`)

---

### EDA-T2-W5.3 — Create Routing Agent — Net Topology + Trace Path Suggestions
* **Priority**: P2 (Medium)
* **Phase**: Phase 2: Agent Orchestration & Multi-Agent EDA Flow
* **Assignee Role**: C++/Python EDA + Spatial Reasoning Engineer (DeepSeek-Coder-V2 23B Q4 / `poolside/laguna-s-2.1:free` fallback)
* **Target Window**: Week 5 (Month 4)
* **Dependencies**: EDA-T2-W5.2 (DRC agent for constraint context), `src/nexus_eda/routing_agent.py`
* **Description & Scope**: Create the `nexus-router` agent that analyzes net topology and suggests trace paths. Uses DeepSeek-Coder-V2 23B Q4 for spatial reasoning (path optimization, obstacle avoidance, via placement). Falls back to `poolside/laguna-s-2.1:free` via Nous Portal when VRAM is constrained. The agent computes optimal routing paths using A* or Lee algorithm, respects DRC rules (trace width, clearance, via Dia/Drill), and outputs KiCad-compatible `wxPoint` coordinate lists. File: `src/nexus_eda/routing_agent.py`. Must achieve <500ms for routing a 20-net board.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `src/nexus_eda/routing_agent.py` exists with `RoutingAgent` class
  - [ ] `RoutingAgent.suggest_routes(net_name, start, end, obstacles)` returns a list of `(x, y, via)` waypoints
  - [ ] `tests/routing_agent_test.py` has >= 8 test cases covering A* pathfinding, obstacle avoidance, via insertion, DRC compliance
  - [ ] `pytest tests/routing_agent_test.py -x -q` passes (exit 0, all 8 tests)
  - [ ] Routing a 20-net board completes in < 500ms (assert in test suite)

---

### EDA-T2-W6.1 — Create BOM Optimizer Agent — LCSC/JLCPCB Cross-reference
* **Priority**: P2 (Medium)
* **Phase**: Phase 2
* **Assignee Role**: Python + Data Engineer (Qwen2.5-Coder 7B Q4 / `deepseek/deepseek-r1:free` fallback)
* **Target Window**: Week 6 (Month 5)
* **Dependencies**: EDA-T2-W5.1 (orchestration), LCSC API integration, `src/nexus_eda/bom_agent.py`
* **Description & Scope**: Create the `nexus-bom` agent that cross-references the PCB BOM against LCSC and JLCPCB catalogs for cost optimization. Uses Qwen2.5-Coder 7B Q4 for catalog parsing and cost analysis. Falls back to `deepseek/deepseek-r1:free` for price comparison math. The agent reads `BillOfMaterials` from pcbnew, queries LCSC/JLCPCB APIs for equivalent components, and suggests lowest-cost alternatives that maintain or improve specifications. Must respect MOQ constraints and avoid substitute components in restricted categories. File: `src/nexus_eda/bom_agent.py`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `src/nexus_eda/bom_agent.py` exists with `BOMOptimizerAgent` class
  - [ ] `BOMOptimizerAgent.optimize_bom(bom_items)` returns a list of `{part_number, lcsc_id, jlcpcb_id, cost, savings, substitute}` dicts
  - [ ] `tests/bom_agent_test.py` has >= 8 test cases covering cost comparison, MOQ enforcement, substitute filtering, spec matching
  - [ ] `pytest tests/bom_agent_test.py -x -q` passes (exit 0, all 8 tests)
  - [ ] BOM optimization for a 50-component board completes in < 2s (assert in test)

---

### EDA-T2-W6.2 — Implement Agent Confidence Scoring
* **Priority**: P2 (Medium)
* **Phase**: Phase 2
* **Assignee Role**: AI Confidence Engineering (Llama-3.1 8B Q4 / `deepseek/deepseek-r1:free` fallback)
* **Target Window**: Week 6 (Month 5)
* **Dependencies**: EDA-T2-W5.2 (DRC agent), EDA-T2-W5.3 (routing agent), EDA-T2-W6.1 (BOM agent)
* **Description & Scope**: Implement a confidence scoring system across all agent suggestions. Per the audit risk assessment, "Model hallucination in circuit design" is High likelihood / High impact, with mitigation: "Verification layer, human-in-loop, never auto-commit changes." Each agent must output a confidence score (0.0–1.0) for every suggestion, based on: (1) source data reliability, (2) DRC compliance, (3) model self-assessment token. The `human-in-loop` approval gate reads this score and blocks auto-commit if < 0.85. Uses Llama-3.1 8B Q4 for verification scoring; falls back to `poolside/laguna-s-2.1:free` via Nous Portal. File: `eda_agents/confidence.py`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `eda_agents/confidence.py` exists with `ConfidenceScorer` class
  - [ ] `ConfidenceScorer.score_suggestion(suggestion, context)` returns a float in range [0.0, 1.0]
  - [ ] `human_in_loop.approve_or_reject(suggestion, confidence)` function exists — returns `True` (approve) if confidence >= 0.85 OR user explicitly approves
  - [ ] `tests/confidence_test.py` has >= 5 test cases covering score ranges, threshold gating, user override
  - [ ] No agent can auto-commit changes — `human_in_loop` gate is enforced in `eda_agents/orchestrator.py` (grep confirms `assert not auto_commit`)

---

### EDA-T2-W6.3 — Human-in-Loop Approval Gates for All Agent Actions
* **Priority**: P2 (Medium)
* **Phase**: Phase 2
* **Assignee Role**: UX + Safety Engineer (TinyLlama 1.1B / `deepseek/deepseek-r1:free` fallback)
* **Target Window**: Week 6 (Month 5)
* **Dependencies**: EDA-T2-W6.2 (confidence scoring), KiCad pcbnew Python plugin API
* **Description & Scope**: Implement the human-in-loop approval gate that intercepts every write operation before it reaches pcbnew. Per the audit's non-training guarantee, agents must NEVER modify the board without explicit user approval. The gate shows a CLI prompt with the suggested change, confidence score, and diff, then waits for user input (`y`/`n`/abort). Uses TinyLlama 1.1B for minimal prompt rendering; falls back to `poolside/laguna-s-2.1:free` for complex change summaries. File: `src/nexus_eda/approval_gate.py`. Integrates with the KiCad plugin's `OnPluginCommandClick` entry point.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `src/nexus_eda/approval_gate.py` exists with `ApprovalGate` class
  - [ ] `ApprovalGate.request_approval(change_description, confidence_score)` returns `True`/`False`/`Abort`
  - [ ] `tests/approval_gate_test.py` has >= 6 test cases covering approve, reject, abort, confidence threshold
  - [ ] `pytest tests/approval_gate_test.py -x -q` passes (exit 0, all 6 tests)
  - [ ] `src/nexus_eda/__init__.py` or plugin entry point calls `ApprovalGate.request_approval()` before any `board.Save()` call (grep confirms >= 1 usage)

---

### EDA-T2-W7 — Integration Testing — Full Workflow
* **Priority**: P2 (Medium)
* **Phase**: Phase 2
* **Assignee Role**: QA Automation Engineer (Qwen2.5-Coder 7B Q4 / `poolside/laguna-s-2.1:free` fallback)
* **Target Window**: Week 7 (Month 6)
* **Dependencies**: EDA-T2-W5.1 through EDA-T2-W6.3 all complete, test board fixture
* **Description & Scope**: Integration testing of the full EDA agent workflow: load board → analyze DRC → suggest routing → optimize BOM → approval gate → write back. Run on `test_data/simple_board.kicad_pcb` (100+ components, 20 nets). Uses Qwen2.5-Coder 7B Q4 for test orchestration. Falls back to `deepseek/deepseek-r1:free` if local OOM. Must achieve: full workflow completes in < 5s, G7-style RT gate for non-audio (nexus-eda-rt-gate.py) passes with 0 violations, zero auto-commits. File: `tests/integration_workflow_test.py`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `tests/integration_workflow_test.py` exists with `test_full_workflow()` function
  - [ ] Full workflow on `test_data/simple_board.kicad_pcb` completes in < 5s (assert `time < 5.0`)
  - [ ] `tools/nexus_eda_rt_gate.py` exists and scans all `src/nexus_eda/*.py` for forbidden patterns (`os.system`, `eval`, `exec`, `subprocess.call`) — exits 0
  - [ ] Integration test passes: `pytest tests/integration_workflow_test.py -x -q` exit 0
  - [ ] No board file is modified without approval — test verifies `board_hash_before == board_hash_after` when approval gate rejects

---

### EDA-T2-W8 — Publish v0.2.0 + Announce on r/PCB
* **Priority**: P2 (Medium)
* **Phase**: Phase 2
* **Assignee Role**: Release Engineer + Community Manager (Qwen2.5-Coder 7B Q4 / `deepseek/deepseek-r1:free` fallback)
* **Target Window**: Week 8 (Month 6)
* **Dependencies**: EDA-T2-W7 (integration testing), GitHub release workflow, r/PCB submission
* **Description & Scope**: Publish v0.2.0 to GitHub as a release (KiCad plugin zip, auto-extracted by KiCad's plugin manager). Create GitHub release with changelog from git history. Announce on r/PCB with a text post describing the multi-agent DRC + routing assistant, include screenshot from `poolside/laguna-s-2.1:free` rendering, and link to the GitHub release. Uses Qwen2.5-Coder 7B Q4 for changelog generation and r/PCB post drafting. Fallback: `deepseek/deepseek-r1:free` for longer-form community copy. Files: `.github/workflows/release.yml`, `__openerp__.py` plugin manifest.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `git tag v0.2.0 && git push origin v0.2.0` succeeds (exit 0, tag exists on remote)
  - [ ] GitHub Release page shows v0.2.0 with `CHANGE.md` changelog (CHANGELOG.md has >= 5 entries from Phase 2)
  - [ ] KiCad plugin zip `nexus_eda_v0.2.0.zip` builds with `__openerp__.py` version = `0.2.0`
  - [ ] r/PCB announcement drafted with title, body (min 300 words), and GitHub release link — saved to `docs/community/r_pcb_announcement_v0.2.0.md`
  - [ ] Plugin version check: `python -c "import nexus_eda; print(nexus_eda.__version__)"` outputs `0.2.0`

---

## Phase 3 (Kanban Tasks) — Detailed Task Cards

### EDA-T3-W9.1 — 3D PCB Viewer — DX12/Vulkan Multi-Canvas Rendering
* **Priority**: P2 (Medium)
* **Phase**: Phase 3: 3D Viewer + Physics Validation
* **Assignee Role**: Graphics Engineer (Qwen2.5-VL 7B Q4 / `poolside/laguna-s-2.1:free` fallback)
* **Target Window**: Week 9 (Month 7)
* **Dependencies**: Phase 2 complete, NBS DX12/Vulkan multi-canvas experience, `src/nexus_eda/viewer_3d.py`
* **Description & Scope**: Build a native 3D PCB viewer leveraging the NBS DX12/Vulkan multi-canvas architecture. The viewer renders KiCad PCB layers (copper, silkscreen, solder mask, drill) as a 3D mesh with transparency controls, component models, and track visualization. Uses Qwen2.5-VL 7B Q4 for vision-based 3D analysis (component placement validation, design rule visualization); falls back to `poolside/laguna-s-2.1:free` via Nous Portal. Reuses NBS's ImGui frontend pattern for the UI overlay. Target: < 33ms render update for 500-component board. File: `src/nexus_eda/viewer_3d.py`, `src/nexus_eda/viewer_3d_renderer.cpp`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `src/nexus_eda/viewer_3d.py` exists with `PCBViewer3D` class wrapping DX12/Vulkan renderer
  - [ ] `src/nexus_eda/viewer_3d_renderer.cpp` renders >= 6 PCB layers with transparency controls
  - [ ] Rendering a 500-component board updates in < 33ms (assert in performance test)
  - [ ] `tests/viewer_3d_test.py` has >= 5 test cases covering mesh generation, layer compositing, component placement
  - [ ] `poolside/laguna-s-2.1:free` is configured as the Nous Portal fallback in `eda_agents/profiles/viewer_agent.yaml`

---

### EDA-T3-W9.2 — Signal Integrity Analyzer — Impedance + Crosstalk
* **Priority**: P2 (Medium)
* **Phase**: Phase 3
* **Assignee Role**: SI/PI Engineer (DeepSeek-R1-Distill 7B / `deepseek/deepseek-r1:free` fallback)
* **Target Window**: Week 9 (Month 7)
* **Dependencies**: EDA-T3-W9.1 (3D viewer for visualization), `src/nexus_eda/si_analyzer.py`
* **Description & Scope**: Create the SI (Signal Integrity) analyzer that computes characteristic impedance, detects crosstalk coupling, and validates trace geometry against target impedance (50Ω single-ended, 100Ω differential). Uses DeepSeek-R1-Distill 7B for math/reasoning (impedance calculations, field solver approximations). Falls back to `deepseek/deepseek-r1:free` via Nous Portal when local VRAM is constrained. Implements a simplified field solver using the Hammerstadt-Jensen model for microstrip and the Huray model for stripline. File: `src/nexus_eda/si_analyzer.py`. Target: < 2s for full-board SI analysis.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `src/nexus_eda/si_analyzer.py` exists with `SIAnalyzer` class
  - [ ] `SIAnalyzer.analyze_impedance(trace_width, trace_thickness, dielectric_height, er)` returns `impedance_ohms` (float)
  - [ ] `SIAnalyzer.detect_crosstalk(nets, separation, length)` returns a list of crosstalk violations
  - [ ] `tests/si_analyzer_test.py` has >= 8 test cases validating impedance computation against known values (±5% tolerance)
  - [ ] Full-board SI analysis completes in < 2s (assert in test)

---

### EDA-T3-W10.1 — Power Integrity Checker — Voltage Drop + Decoupling
* **Priority**: P2 (Medium)
* **Phase**: Phase 3
* **Assignee Role**: Power Electronics Engineer (DeepSeek-R1-Distill 7B / `deepseek/deepseek-r1:free` fallback)
* **Target Window**: Week 10 (Month 7)
* **Dependencies**: EDA-T3-W9.2 (SI analyzer), `src/nexus_eda/pi_checker.py`
* **Description & Scope**: Create the PI (Power Integrity) checker that analyzes voltage drop across the power distribution network (PDN), validates decoupling capacitor placement, and identifies noise coupling paths. Uses DeepSeek-R1-Distill 7B for power mesh analysis and Ohm's law calculations. Falls back to `deepseek/deepseek-r1:free` via Nous Portal. Implements a simplified PDN analysis using Kirchhoff's laws and capacitor impedance curves. File: `src/nexus_eda/pi_checker.py`. Target: < 2s for 100-capacitor PDN analysis.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `src/nexus_eda/pi_checker.py` exists with `PIChecker` class
  - [ ] `PIChecker.analyze_voltage_drop(net_name, currents, resistances)` returns `voltage_droop` in volts
  - [ ] `PIChecker.validate_decoupling(capacitors, frequencies)` returns list of inadequate caps
  - [ ] `tests/pi_checker_test.py` has >= 6 test cases validating voltage drop computation (±5% tolerance)
  - [ ] PDN analysis for 100 capacitors completes in < 2s (assert in test)

---

### EDA-T3-W10.2 — Thermal Hotspot Detector — Power Dissipation Modeling
* **Priority**: P2 (Medium)
* **Phase**: Phase 3
* **Assignee Role**: Thermal Analyst (Llama-3.1 8B Q4 / `poolside/laguna-s-2.1:free` fallback)
* **Target Window**: Week 10 (Month 8)
* **Dependencies**: EDA-T3-W10.1 (PI checker for power data), `src/nexus_eda/thermal.py`
* **Description & Scope**: Create the thermal hotspot detector that models component power dissipation and identifies thermal hotspots on the PCB. Uses Llama-3.1 8B Q4 for component thermal model reasoning. Falls back to `poolside/laguna-s-2.1:free` via Nous Portal. Implements a simplified thermal model: `T_component = T_ambient + P_dissipated * R_th`, where R_th is computed from component package thermal resistance and PCB copper area. File: `src/nexus_eda/thermal.py`. Target: < 1s for 200-component thermal scan.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `src/nexus_eda/thermal.py` exists with `ThermalAnalyzer` class
  - [ ] `ThermalAnalyzer.compute_hotspots(components, ambient_temp)` returns list of `{component, temperature, is_hotspot}` dicts
  - [ ] `ThermalAnalyzer.is_hotspot(temperature)` returns `True` if `temperature > 85.0` (default threshold)
  - [ ] `tests/thermal_test.py` has >= 5 test cases validating temperature computation (±2°C tolerance)
  - [ ] Thermal scan for 200 components completes in < 1s (assert in test)

---

### EDA-T3-W11.1 — Manufacturability Checker — JLCPCB/PCBWay DRC Compatibility
* **Priority**: P2 (Medium)
* **Phase**: Phase 3
* **Assignee Role**: Manufacturing Engineer (Qwen2.5-Coder 7B Q4 / `deepseek/deepseek-r1:free` fallback)
* **Target Window**: Week 11 (Month 8)
* **Dependencies**: EDA-T3-W9.2 (SI analyzer for trace constraints), `src/nexus_eda/dfm_checker.py`
* **Description & Scope**: Create the DFM (Design for Manufacturing) checker that validates PCB designs against JLCPCB and PCBWay manufacturing capabilities. Uses Qwen2.5-Coder 7B Q4 for manufacturer rule parsing. Falls back to `deepseek/deepseek-r1:free` via Nous Portal. Checks: minimum trace width (JLCPCB: 0.15mm, PCBWay: 0.1mm), minimum clearance (JLCPCB: 0.15mm, PCBWay: 0.1mm), via drill (JLCPCB: 0.2mm, PCBWay: 0.15mm), silkscreen over mask (0.07mm). File: `src/nexus_eda/dfm_checker.py`. Target: < 500ms for full-board DFM check.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `src/nexus_eda/dfm_checker.py` exists with `DFMChecker` class
  - [ ] `DFMChecker.check_manufacturability(board, fab) ` returns list of `{rule, violation, severity}` where fab ∈ `{"jlcpcb", "pcbway"}`
  - [ ] `DFMChecker.JLCPCB_RULES` dict contains `min_trace_width=0.15`, `min_clearance=0.15`, `min_via_drill=0.2`
  - [ ] `tests/dfm_checker_test.py` has >= 7 test cases covering trace width, clearance, via drill, silkscreen rules
  - [ ] Full-board DFM check completes in < 500ms (assert in test)

---

### EDA-T3-W11.2 — Zero-Copy Integration with NBS Rendering Pipeline
* **Priority**: P2 (Medium)
* **Phase**: Phase 3
* **Assignee Role**: Graphics Integration Engineer (Qwen2.5-VL 7B Q4 / `poolside/laguna-s-2.1:free` fallback)
* **Target Window**: Week 11 (Month 8)
* **Dependencies**: EDA-T3-W9.1 (3D viewer), NBS zero-copy HEAL (NVENC/AMF/QSV) architecture
* **Description & Scope**: Integrate the 3D PCB viewer with the NBS zero-copy rendering pipeline. This leverages NBS's existing zero-copy texture sharing between ImGui and HEAL backends (NVENC/AMF/QSV). The 3D mesh data from KiCad is uploaded as a zero-copy DX12/Vulkan buffer that NBS can consume directly for video capture and streaming. Uses Qwen2.5-VL 7B Q4 for texture format validation. Falls back to `poolside/laguna-s-2.1:free` via Nous Portal. File: `src/nexus_eda/viewer_3d_zero_copy.cpp`, `plugins/nbs_bridge.py`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `src/nexus_eda/viewer_3d_zero_copy.cpp` exists with `ZeroCopyMeshBuffer` class
  - [ ] `ZeroCopyMeshBuffer.upload_to_gpu(mesh_data)` returns a DX12/Vulkan `GpuResourceHandle` (no CPU→GPU copy)
  - [ ] `plugins/nbs_bridge.py` registers with NBS via `nexusio://` IPC protocol (grep confirms IPC registration)
  - [ ] Buffer round-trip test: `ZeroCopyMeshBuffer` upload → render → readback completes with 0 memcpy operations
  - [ ] Integration test with NBS: 3D PCB render appears in NBS studio canvas within 2 render frames (< 33ms)

---

### EDA-T3-W12 — Integration Testing + Publish v0.3.0
* **Priority**: P2 (Medium)
* **Phase**: Phase 3
* **Assignee Role**: QA + Release Engineer (Qwen2.5-Coder 7B Q4 / `deepseek/deepseek-r1:free` fallback)
* **Target Window**: Week 12 (Month 9)
* **Dependencies**: EDA-T3-W9.1 through EDA-T3-W11.2 all complete
* **Description & Scope**: Full integration testing of 3D viewer + SI/PI analysis + thermal + DFM + zero-copy NBS bridge. Run on `test_data/complex_board.kicad_pcb` (500+ components, 8 layers). Publish v0.3.0 to GitHub with changelog. Uses Qwen2.5-Coder 7B Q4 for test orchestration. Falls back to `deepseek/deepseek-r1:free` via Nous Portal. File: `tests/integration_phase3_test.py`, `.github/workflows/release_v0.3.0.yml`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `tests/integration_phase3_test.py` exists with >= 5 integration tests
  - [ ] Full workflow (3D render + SI + PI + thermal + DFM + NBS bridge) completes in < 10s on complex_board.kicad_pcb
  - [ ] `git tag v0.3.0 && git push origin v0.3.0` succeeds (exit 0)
  - [ ] GitHub Release page shows v0.3.0 with changelog (>= 8 entries from Phase 3)
  - [ ] `CHANGELOG.md` includes sections: 3D Viewer, SI Analyzer, PI Checker, Thermal, DFM, NBS Bridge

---

### EDA-T3-W13W14 — Community Feedback Iteration
* **Priority**: P2 (Medium)
* **Phase**: Phase 3
* **Assignee Role**: Community Manager (TinyLlama 1.1B / `deepseek/deepseek-r1:free` fallback)
* **Target Window**: Weeks 13–14 (Month 9)
* **Dependencies**: EDA-T3-W12 (v0.3.0 published), GitHub issues, Discord server
* **Description & Scope**: Collect and process community feedback from GitHub issues, r/PCB, and the Discord server. Uses TinyLlama 1.1B for issue triage and categorization (bug report, feature request, question). Falls back to `poolside/laguna-s-2.1:free` for complex feedback summarization. Triage all issues filed during the 2-week feedback window, categorize by severity, and produce a prioritized backlog for Phase 4. File: `docs/community/feedback_triage_w13-14.md`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `docs/community/feedback_triage_w13-14.md` exists with categorized feedback table (>= 10 issues processed)
  - [ ] Bug reports: >= 3 classified as P0/Critical (must fix before v1.0)
  - [ ] Feature requests: >= 5 classified as P1/High priority
  - [ ] All feedback items have a corresponding GitHub issue reference (URL or issue #)
  - [ ] Feedback summary emailed/drafted to blockie for review (saved to `docs/community/executive_summary_w13-14.md`)

---

## Phase 4 (Kanban Tasks) — Detailed Task Cards

### EDA-T4-W15.1 — Implement SABLE-Inspired 28 Scoped Entry Points
* **Priority**: P2 (Medium)
* **Phase**: Phase 4: Sovereign Data Architecture
* **Assignee Role**: Security Architect (DeepSeek-R1-Distill 7B / `deepseek/deepseek-r1:free` fallback)
* **Target Window**: Week 15 (Month 10)
* **Dependencies**: EDA-T3-W12 (v0.3.0), SABLE paper reference, `src/nexus_eda/sovereign_boundary.py`
* **Description & Scope**: Implement the SABLE-inspired 28 scoped entry points that strip PDK (Process Design Kit), file paths, and model identifiers before any data leaves the local machine. Uses DeepSeek-R1-Distill 7B for scope analysis and data path audit. Falls back to `deepseek/deepseek-r1:free` via Nous Portal. Each of the 28 entry points (API calls, IPC channels, file exports, network sync) must pass through a scope filter that removes sensitive identifiers. File: `src/nexus_eda/sovereign_boundary.py`, `src/nexus_eda/scoped_entry.py`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `src/nexus_eda/sovereign_boundary.py` exists with `SovereignBoundary` class
  - [ ] `SovereignBoundary.SCOPE_COUNT` == 28 (exactly 28 entry points registered)
  - [ ] `src/nexus_eda/scoped_entry.py` has `ScopedEntry` base class with `enter_scope()` and `exit_scope()` methods
  - [ ] `tests/sovereign_boundary_test.py` has >= 10 test cases verifying PDK/path/model stripping at each entry point
  - [ ] `pytest tests/sovereign_boundary_test.py -x -q` passes (exit 0)

---

### EDA-T4-W15.2 — Build Encrypted Local Storage (AES-256)
* **Priority**: P2 (Medium)
* **Phase**: Phase 4
* **Assignee Role**: Cryptography Engineer (TinyLlama 1.1B / `poolside/laguna-s-2.1:free` fallback)
* **Target Window**: Week 15 (Month 10)
* **Dependencies**: EDA-T4-W15.1 (sovereign boundary), SQLCipher or cryptography library
* **Description & Scope**: Build encrypted local storage for all design data using AES-256. Uses TinyLlama 1.1B for minimal key management logic. Falls back to `poolside/laguna-s-2.1:free` for key derivation complexity. All KiCad project files, component libraries, routing suggestions, and agent session logs are stored encrypted on disk. The encryption key is derived from a user-provided passphrase via PBKDF2-HMAC-SHA256 with 100,000 iterations. Auto-unlock via OS keychain (Windows DPAPI) is optional. File: `src/nexus_eda/secure_storage.py`, `src/nexus_eda/encryption_key.py`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `src/nexus_eda/secure_storage.py` exists with `SecureStorage` class
  - [ ] `SecureStorage.store(key, data)` encrypts with AES-256-GCM and writes to `vault/` directory
  - [ ] `SecureStorage.retrieve(key)` decrypts and returns original data
  - [ ] `src/nexus_eda/encryption_key.py` `derive_key(passphrase, salt)` uses PBKDF2 with 100,000 iterations
  - [ ] `tests/secure_storage_test.py` verifies encryption/decryption round-trip and that plaintext is not found in stored files

---

### EDA-T4-W15.3 — Non-Training Guarantee — Data Path Leakage Audit
* **Priority**: P0 (Blocker)
* **Phase**: Phase 4
* **Assignee Role**: Security Auditor (DeepSeek-R1-Distill 7B / `deepseek/deepseek-r1:free` fallback)
* **Target Window**: Week 15 (Month 10)
* **Dependencies**: EDA-T4-W15.1 (28 scoped entry points), `src/nexus_eda/data_flow_audit.py`
* **Description & Scope**: Audit all data paths in the Nexus-EDA codebase to ensure no user design data leaves the machine without explicit consent and encryption. This is the "non-training guarantee" risk from the audit — the highest priority item in Phase 4. Uses DeepSeek-R1-Distill 7B for data flow analysis. Falls back to `deepseek/deepseek-r1:free` via Nous Portal. Scans all Python files for: `requests.post/get`, `urllib`, `socket`, `ftplib`, `paramiko`, subprocess calls to external tools, and environment variable exfiltration. File: `src/nexus_eda/data_flow_audit.py`, `tools/sovereign_data_scrub.py`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `src/nexus_eda/data_flow_audit.py` exists and scans `src/nexus_eda/` for forbidden patterns (`requests.`, `urllib`, `socket.connect`, `subprocess.run` with external commands)
  - [ ] Audit finds 0 unconsented network calls in `src/nexus_eda/` (grep returns nothing without `--allow-list`)
  - [ ] `tools/sovereign_data_scrub.py` exists and passes: `python tools/sovereign_data_scrub.py --scan src/nexus_eda/` outputs `0 violations found`
  - [ ] All 28 scoped entry points have explicit `--allow-upload` flags (grep `allow_upload` in `sovereign_boundary.py`, >= 28 matches)
  - [ ] Data scrub performance: `python tools/sovereign_data_scrub.py --scan src/nexus_eda/` completes in < 100ms (assert in CI)

---

### EDA-T4-W16.1 — On-Prem Deployment Package — Docker + Local Model Serving
* **Priority**: P2 (Medium)
* **Phase**: Phase 4
* **Assignee Role**: DevOps / Containerization Engineer (Qwen2.5-Coder 7B Q4 / `deepseek/deepseek-r1:free` fallback)
* **Target Window**: Week 16 (Month 10)
* **Dependencies**: EDA-T4-W15.1 through EDA-T4-W15.3 complete, Docker, local model serving
* **Description & Scope**: Create an on-prem Docker deployment package that includes all LLM models locally (no cloud calls). The Docker image bundles Qwen3-Coder 32B Q4, Qwen2.5-Coder 7B Q4, DeepSeek-R1-Distill 7B, Llama-3.1 8B Q4, and TinyLlama 1.1B. Includes a local model serving API (`nexus-llm-local`) that the EDA plugin connects to via `localhost:8000`. Falls back to `deepseek/deepseek-r1:free` via Nous Portal if any model fails to load. File: `Dockerfile.enterprise`, `docker-compose.enterprise.yml`, `src/nexus_eda/local_llm_serve.py`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `Dockerfile.enterprise` builds with `docker build -t nexus-eda-enterprise .` exit 0
  - [ ] Image contains all 5 models in `/models/` directory (verify via `docker run --rm -it ... ls /models/`)
  - [ ] `docker-compose.enterprise.yml` starts local LLM server on port 8000 (health check `curl localhost:8000/health` returns 200)
  - [ ] `src/nexus_eda/local_llm_serve.py` serves Qwen3-Coder 32B via `nexus-llm-local` API endpoint
  - [ ] EDA plugin connects to `localhost:8000` and receives LLM responses in < 500ms/token

---

### EDA-T4-W16.2 — GDPR Compliance Module — Data Export/Deletion APIs
* **Priority**: P2 (Medium)
* **Phase**: Phase 4
* **Assignee Role**: Compliance Engineer (Llama-3.1 8B Q4 / `deepseek/deepseek-r1:free` fallback)
* **Target Window**: Week 16 (Month 10)
* **Dependencies**: EDA-T4-W15.2 (encrypted storage), `src/nexus_eda/gdpr_compliance.py`
* **Description & Scope**: Implement GDPR compliance APIs for data export (Article 15 — right of access) and data deletion (Article 17 — right to erasure). The module allows users to export all their stored data in JSON format and permanently delete all data including encrypted vaults, agent session logs, and cached component libraries. Uses Llama-3.1 8B Q4 for compliance checklist verification. Falls back to `poolside/laguna-s-2.1:free` via Nous Portal. File: `src/nexus_eda/gdpr_compliance.py`, `plugins/gdpr_export_plugin.py`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `src/nexus_eda/gdpr_compliance.py` exists with `GDPRCompliance` class
  - [ ] `GDPRCompliance.export_all_data(user_id)` returns a JSON dict with all user data (vault contents, session logs, preferences)
  - [ ] `GDPRCompliance.permanently_delete(user_id)` removes all data and verifies deletion (returns `True` if no files remain)
  - [ ] `tests/gdpr_test.py` has >= 6 test cases covering export, delete, re-export-after-delete, audit log, consent withdrawal
  - [ ] `pytest tests/gdpr_test.py -x -q` passes (exit 0)

---

### EDA-T4-W17.1 — SSO/SAML Integration (Enterprise Tier)
* **Priority**: P2 (Medium)
* **Phase**: Phase 4
* **Assignee Role**: Identity & Access Management Engineer (Qwen2.5-Coder 7B Q4 / `deepseek/deepseek-r1:free` fallback)
* **Target Window**: Week 17 (Month 11)
* **Dependencies**: EDA-T4-W16.2 (GDPR compliance), Authlib or python-saml library
* **Description & Scope**: Implement SSO/SAML 2.0 integration for enterprise customers. Integrates with Azure AD, Okta, and Google Workspace via SAML 2.0. Provides SP-initiated and IDP-initiated SSO flows. Falls back to `deepseek/deepseek-r1:free` via Nous Portal for SAML XML metadata parsing. File: `src/nexus_eda/sso_saml.py`, `plugins/auth_saml_plugin.py`, `templates/saml_config.yaml`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `src/nexus_eda/sso_saml.py` exists with `SamlSSO` class
  - [ ] `SamlSSO.initiate_login()` returns a redirect URL to the configured IDP
  - [ ] `SamlSSO.process_response(saml_response)` validates the SAML assertion and returns `{user_id, email, name}`
  - [ ] `tests/sso_saml_test.py` has >= 6 test cases covering SP-initiated flow, IDP-initiated flow, assertion validation, session management
  - [ ] `pytest tests/sso_saml_test.py -x -q` passes (exit 0)

---

### EDA-T4-W17.2 — ITAR Compliance Audit Trail
* **Priority**: P0 (Blocker)
* **Phase**: Phase 4
* **Assignee Role**: Compliance Auditor (DeepSeek-R1-Distill 7B / `deepseek/deepseek-r1:free` fallback)
* **Target Window**: Week 17 (Month 11)
* **Dependencies**: EDA-T4-W15.3 (data path audit), `src/nexus_eda/itar_audit.py`
* **Description & Scope**: ITAR (International Traffic in Arms Regulations) compliance audit trail for defense enterprise tier. Every board file access, export, agent action, and data transfer must be logged with timestamp, user ID, action type, and data hash. Logs must be tamper-evident (hash-chained). Uses DeepSeek-R1-Distill 7B for audit log analysis. Falls back to `poolside/laguna-s-2.1:free` via Nous Portal. File: `src/nexus_eda/itar_audit.py`, `tools/itar_audit_report.py`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `src/nexus_eda/itar_audit.py` exists with `ITARAuditTrail` class
  - [ ] `ITARAuditTrail.log_action(user_id, action, data_hash, timestamp)` appends to tamper-evident log file `logs/itar_audit.log`
  - [ ] Each log entry includes a SHA-256 hash chain to the previous entry (verify: `hash_chain` field present)
  - [ ] `tools/itar_audit_report.py --user <id> --date <YYYY-MM-DD>` generates an audit report (exit 0)
  - [ ] `tests/itar_audit_test.py` has >= 5 test cases covering log append, hash chain integrity, tamper detection, report generation

---

### EDA-T4-W18 — Publish v1.0.0 — "Nexus-EDA Enterprise"
* **Priority**: P2 (Medium)
* **Phase**: Phase 4
* **Assignee Role**: Product Manager + Release Engineer (Qwen2.5-Coder 7B Q4 / `deepseek/deepseek-r1:free` fallback)
* **Target Window**: Week 18 (Month 12)
* **Dependencies**: EDA-T4-W16.1 through EDA-T4-W17.2 all complete, GitHub release workflow
* **Description & Scope**: Publish v1.0.0 "Nexus-EDA Enterprise" with full sovereign data architecture. Includes: AES-256 encrypted storage, 28 scoped entry points, SSO/SAML, ITAR audit trail, GDPR compliance exports, and local Docker deployment with bundled models. Create GitHub release with binary assets, update KiCad Plugin Manager listing, and announce on r/PCB + LinkedIn. Uses Qwen2.5-Coder 7B Q4 for changelog and release notes. Falls back to `deepseek/deepseek-r1:free` for long-form announcement copy. File: `CHANGELOG.md`, `.github/workflows/release_enterprise.yml`, `docs/release/enterprise_v1.0.0_notes.md`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `git tag v1.0.0 && git push origin v1.0.0` succeeds (exit 0, tag exists on remote)
  - [ ] GitHub Release page shows v1.0.0 "Nexus-EDA Enterprise" with binary assets (KiCad plugin zip, Docker image tarball)
  - [ ] `CHANGELOG.md` has >= 30 entries across all 4 phases (Phase 2: 8, Phase 3: 8, Phase 4: 7 + Enterprise summary)
  - [ ] `docs/release/enterprise_v1.0.0_notes.md` exists with feature summary, installation guide, and known issues (>= 500 words)
  - [ ] r/PCB announcement saved to `docs/community/r_pcb_announcement_v1.0.0.md` (title, body >= 400 words, release link)

---

### EDA-T4-W19W20 — Beta Enterprise Onboarding (3–5 Defense/Aerospace Companies)
* **Priority**: P2 (Medium)
* **Phase**: Phase 4
* **Assignee Role**: Enterprise Account Manager (TinyLlama 1.1B / `deepseek/deepseek-r1:free` fallback)
* **Target Window**: Weeks 19–20 (Month 12)
* **Dependencies**: EDA-T4-W18 (v1.0.0 published)
* **Description & Scope**: Onboard 3–5 defense/aerospace companies as beta enterprise customers. Uses TinyLlama 1.1B for minimal customer communication (email templates, onboarding checklist). Falls back to `poolside/laguna-s-2.1:free` for complex enterprise requirement gathering. Deliverables: onboarding checklist template, enterprise license agreement template, SSO configuration guide, ITAR compliance documentation, and first-customer success report. File: `docs/enterprise/onboarding_checklist.md`, `docs/enterprise/ELA_template.md`, `docs/enterprise/success_report_template.md`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `docs/enterprise/onboarding_checklist.md` exists with >= 15 checklist items (SSO setup, ITAR audit, data export, training, support)
  - [ ] `docs/enterprise/ELA_template.md` exists with legal sections: data rights, liability cap, support SLA, ITAR compliance clause
  - [ ] `docs/enterprise/success_report_template.md` exists with metrics template: boards designed, agent hours saved, DRC time reduction, user satisfaction
  - [ ] At least 1 enterprise customer successfully onboarded (onboarding completion documented in `docs/enterprise/customer_<name>_onboarding.md`)
  - [ ] Enterprise onboarding email template saved to `docs/community/corporate_outreach_template.md`

---

## Phase 5 (Kanban Tasks) — Detailed Task Cards

### EDA-T5-W21.1 — Stripe Billing Integration — Subscription Tiers
* **Priority**: P2 (Medium)
* **Phase**: Phase 5: SaaS Launch & Market Entry
* **Assignee Role**: Backend / Billing Engineer (TinyLlama 1.1B / `poolside/laguna-s-2.1:free` fallback)
* **Target Window**: Week 21 (Month 13)
* **Dependencies**: Phase 4 complete, Stripe account, `src/nexus_eda/billing.py`
* **Description & Scope**: Implement Stripe billing integration for 4 subscription tiers: Free (7B model, 5 boards/day), Maker ($19/mo, 2B+7B models, unlimited boards), Pro ($49/mo, all local models, SSO/SAML), Enterprise (custom, on-prem Docker, ITAR). Uses TinyLlama 1.1B for billing rule logic. Falls back to `deepseek/deepseek-r1:free` for complex pricing calculations. Files: `src/nexus_eda/billing.py`, `plugins/stripe_webhook.py`, `docs/billing/pricing_tiers.md`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `src/nexus_eda/billing.py` exists with `Billing` class
  - [ ] `Billing.TIERS` dict has 4 tiers: `free` ($0), `maker` ($19), `pro` ($49), `enterprise` (custom)
  - [ ] `Billing.create_checkout_session(tier, user_id)` returns a valid Stripe `sessionId` (test with Stripe test keys)
  - [ ] `plugins/stripe_webhook.py` handles `checkout.session.completed` and `customer.subscription.updated` events
  - [ ] `docs/billing/pricing_tiers.md` lists all 4 tiers with features, limits, and model access

---

### EDA-T5-W21.2 — Customer Support Automation — Ticket Routing + FAQ Bot
* **Priority**: P2 (Medium)
* **Phase**: Phase 5
* **Assignee Role**: Customer Success Engineer (Qwen2.5-Coder 7B Q4 / `deepseek/deepseek-r1:free` fallback)
* **Target Window**: Week 21 (Month 13)
* **Dependencies**: EDA-T5-W21.1 (Stripe billing), `src/nexus_eda/support_bot.py`
* **Description & Scope**: Implement customer support automation: ticket routing system that categorize support requests (billing, technical, feature request), FAQ bot that answers common questions about installation, licensing, and usage. Uses Qwen2.5-Coder 7B Q4 for intent classification and FAQ retrieval. Falls back to `deepseek/deepseek-r1:free` via Nous Portal for complex troubleshooting. Integrates with GitHub Issues as the ticket backend. File: `src/nexus_eda/support_bot.py`, `plugins/support_webhook.py`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `src/nexus_eda/support_bot.py` exists with `SupportBot` class
  - [ ] `SupportBot.classify_intent(message)` returns one of: `billing`, `technical`, `feature_request`, `general`
  - [ ] `SupportBot.answer_faq(question)` returns a response with >= 50 words from a local FAQ knowledge base
  - [ ] `tests/support_bot_test.py` has >= 10 test cases covering intent classification accuracy (> 85%), FAQ answers for top 5 questions
  - [ ] GitHub Issue #1 created automatically when SupportBot cannot resolve (integration test with `--dry-run`)

---

### EDA-T5-W22.1 — Marketing Launch — X/Twitter Campaign
* **Priority**: P2 (Medium)
* **Phase**: Phase 5
* **Assignee Role**: Growth Marketer (TinyLlama 1.1B / `poolside/laguna-s-2.1:free` fallback)
* **Target Window**: Week 22 (Month 14)
* **Dependencies**: EDA-T5-W21.1 (billing), blockie's X/Twitter account (buildapc/AI-agents/DSP/audio niche)
* **Description & Scope**: Launch an X/Twitter campaign targeting the buildapc/AI-agents/DSP/audio niche (matching blockie's existing audience). Uses TinyLlama 1.1B for tweet generation and scheduling. Falls back to `poolside/laguna-s-2.1:free` via Nous Portal for longer technical threads. The campaign: 10 tweets over 2 weeks, 3 technical deep-dive threads, X/Twitter Spaces announcement, and 5 pinned reply engagements. Requires X/Twitter Basic API tier (~$100/mo, Read+Write+DM) with keys at `C:\Users\bhogl\Projects\a2a-wallets\x_credentials.json`. File: `docs/marketing/x_campaign_script.md`, `docs/marketing/tweet_templates.json`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `docs/marketing/x_campaign_script.md` exists with 10 tweets + 3 thread outlines (>= 300 words each)
  - [ ] `docs/marketing/tweet_templates.json` has >= 15 tweet templates with variables for version, features, links
  - [ ] X/Twitter credentials verified at `C:\Users\bhogl\Projects\a2a-wallets\x_credentials.json` (key present, not blank)
  - [ ] Test tweet scheduled via API: `python -c "from src.nexus_eda.twitter_client import post_tweet; post_tweet('test', dry_run=True"` returns success
  - [ ] Campaign calendar: 2-week schedule with specific dates, times, and content types

---

### EDA-T5-W22.2 — Documentation Site — Hugo + GitHub Pages
* **Priority**: P2 (Medium)
* **Phase**: Phase 5
* **Assignee Role**: Documentation Engineer (Qwen2.5-Coder 7B Q4 / `deepseek/deepseek-r1:free` fallback)
* **Target Window**: Week 22 (Month 14)
* **Dependencies**: EDA-T4-W18 (v1.0.0 released), Hugo, GitHub Pages, `docs/` directory
* **Description & Scope**: Set up a Hugo documentation site hosted on GitHub Pages. Converts existing `docs/` markdown into a searchable, themable documentation site. Uses Qwen2.5-Coder 7B Q4 for content organization and Hugo template creation. Falls back to `deepseek/deepseek-r1:free` for long-form documentation. Includes: API reference, installation guide, tutorial videos (embedded), FAQ, and contributor guide. File: `hugo-site/config.toml`, `hugo-site/content/_index.md`, `hugo-site/layouts/`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `hugo-site/config.toml` exists with `baseURL`, `title = "Nexus-EDA Documentation"`, and theme config
  - [ ] `hugo-site/content/_index.md` has homepage with >= 300 words, hero section, and quick-start link
  - [ ] `hugo-site/content/installation/` has >= 3 pages (local install, Docker, enterprise)
  - [ ] `hugo-site/content/api/` has >= 5 API endpoint reference pages
  - [ ] `hugo server` builds successfully (exit 0) and site is live at `https://nexus-eda.github.io/` (GitHub Pages auto-deploy configured in `.github/workflows/docs.yml`)

---

### EDA-T5-W23.1 — YouTube Tutorial Series — "Building PCBs with AI"
* **Priority**: P2 (Medium)
* **Phase**: Phase 5
* **Assignee Role**: Content Creator (TinyLlama 1.1B / `poolside/laguna-s-2.1:free` fallback)
* **Target Window**: Week 23 (Month 14)
* **Dependencies**: EDA-T5-W22.2 (docs site), YouTube channel, OBS recording setup
* **Description & Scope**: Create a 5-episode YouTube tutorial series: "Building PCBs with AI — A Nexus-EDA Walkthrough." Episodes: (1) Installation & Setup, (2) Loading Your First KiCad Project, (3) DRC Agent Analysis, (4) AI Routing Agent, (5) Manufacturing Export. Uses TinyLlama 1.1B for script generation. Falls back to `poolside/laguna-s-2.1:free` for longer narrative content. Includes screen recordings, captions, and downloadable project files. File: `docs/youtube/scripts/episode_1_through_5.md`, `docs/youtube/thumbnails/`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `docs/youtube/scripts/` has 5 episode scripts (>= 800 words each, with timestamps)
  - [ ] `docs/youtube/thumbnails/` has 5 thumbnail designs (1280x720px, title + episode number)
  - [ ] Episode 1 video script includes exact OBS recording settings (1080p, 30fps, audio from NBS HEAL)
  - [ ] Downloadable project files for each episode saved in `docs/youtube/project_files/`
  - [ ] YouTube upload schedule: 1 episode/week for 5 weeks, with titles and descriptions drafted

---

### EDA-T5-W23.2 — Discord Community Server Setup
* **Priority**: P2 (Medium)
* **Phase**: Phase 5
* **Assignee Role**: Community Manager (TinyLlama 1.1B / `poolside/laguna-s-2.1:free` fallback)
* **Target Window**: Week 23 (Month 14)
* **Dependencies**: EDA-T5-W23.1 (YouTube series), Discord server creation
* **Description & Scope**: Set up a Discord community server for Nexus-EDA users. Channels: #announcements, #support, #feature-requests, #showcase, #development, #random. Uses TinyLlama 1.1B for bot command logic. Falls back to `poolside/laguna-s-2.1:free` for welcome message and moderation assistance. File: `docs/community/discord_server_setup_guide.md`, `plugins/discord_bot.py`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `docs/community/discord_server_setup_guide.md` exists with channel list, roles, and bot setup instructions
  - [ ] `plugins/discord_bot.py` exists with bot token config and >= 5 commands (`/help`, `/faq`, `/support`, `/changelog`, `/feedback`)
  - [ ] Discord server created with >= 6 text channels and 2 voice channels
  - [ ] Welcome bot posts a message to new members with rules and resource links
  - [ ] Server invite link saved to `docs/community/discord_invite.txt`

---

### EDA-T5-W24 — First Paid Customer Acquisition (3 Enterprises + 50 Pro)
* **Priority**: P0 (Blocker)
* **Phase**: Phase 5
* **Assignee Role**: Sales Development Representative (Qwen2.5-Coder 7B Q4 / `deepseek/deepseek-r1:free` fallback)
* **Target Window**: Week 24 (Month 15)
* **Dependencies**: EDA-T5-W21.1 (Stripe billing), EDA-T5-W22.1 (X/Twitter campaign), EDA-T4-W19W20 (enterprise onboarding)
* **Description & Scope**: Acquire the first paid customers: 3 enterprise accounts + 50 Pro tier subscribers. Uses Qwen2.5-Coder 7B Q4 for customer outreach email drafting and lead qualification. Falls back to `deepseek/deepseek-r1:free` via Nous Portal for longer sales copy. Outreach channels: r/PCB announcement (from EDA-T2-W8), X/Twitter campaign (from EDA-T5-W22.1), GitHub sponsor, direct email to EDA professionals. File: `docs/sales/outreach_template.md`, `docs/sales/customer_acquisition_tracker.md`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `docs/sales/outreach_template.md` exists with email template (>= 200 words) and DM template for X/Twitter
  - [ ] `docs/sales/customer_acquisition_tracker.md` exists with a table: customer name, tier, acquisition date, source channel, status
  - [ ] At least 3 enterprise leads contacted (email or DM sent, tracked in acquisition tracker)
  - [ ] Landing page with Stripe checkout created at `https://nexus-eda.github.io/checkout`
  - [ ] First paying customer acquired (Stripe subscription created, status = `active`)

---

### EDA-T5-W25W26 — Post-Launch Stabilization + Feedback Iteration
* **Priority**: P2 (Medium)
* **Phase**: Phase 5
* **Assignee Role**: SRE + Product Manager (Qwen2.5-Coder 7B Q4 / `deepseek/deepseek-r1:free` fallback)
* **Target Window**: Weeks 25–26 (Month 15)
* **Dependencies**: EDA-T5-W24 (first customer acquisition)
* **Description & Scope**: Post-launch stabilization and feedback iteration cycle. Monitor: crash reports, user feedback from Discord/GitHub, billing churn, and feature requests. Uses Qwen2.5-Coder 7B Q4 for log analysis and issue triage. Falls back to `deepseek/deepseek-r1:free` via Nous Portal for crash report analysis. Weekly retrospective meetings documented. File: `docs/community/feedback_iteration_w25-26.md`, `tools/crash_report_analyzer.py`.
* **Acceptance Criteria (Definition of Done)**:
  - [ ] `docs/community/feedback_iteration_w25-26.md` exists with weekly retrospective summary (4 weeks, min 200 words/week)
  - [ ] `tools/crash_report_analyzer.py` exists and runs: `python tools/crash_report_analyzer.py --logs logs/crash_reports/` outputs summary with crash counts by type
  - [ ] >= 5 crash reports analyzed and categorized (crash type, frequency, severity)
  - [ ] >= 3 feature requests prioritized into Phase 6 backlog (documented in `docs/roadmap/phase6_backlog.md`)
  - [ ] Monthly active users (MAU) tracked: >= 100 unique users in weeks 25–26 combined

---

## Consolidated Model Assignment Matrix (All Phases)

| Task ID | Local Model | Nous Portal Free Fallback | Rationale |
|--------|------------|----------------|-----------|
| EDA-T2-W5.1 | Qwen3-Coder 32B Q4 (~18GB) | `poolside/laguna-s-2.1:free` | Primary orchestration, high VRAM OK |
| EDA-T2-W5.2 | Qwen2.5-Coder 7B Q4 (~6GB) | `deepseek/deepseek-r1:free` | DRC rule parsing, math-heavy |
| EDA-T2-W5.3 | DeepSeek-Coder-V2 23B Q4 (~16GB) | `poolside/laguna-s-2.1:free` | Spatial reasoning for routing |
| EDA-T2-W6.1 | Qwen2.5-Coder 7B Q4 (~6GB) | `deepseek/deepseek-r1:free` | Catalog parsing, cost comparison |
| EDA-T2-W6.2 | Llama-3.1 8B Q4 (~7GB) | `deepseek/deepseek-r1:free` | Confidence scoring, verification |
| EDA-T2-W6.3 | TinyLlama 1.1B (~1GB) | `deepseek/deepseek-r1:free` | Minimal approval gate UI |
| EDA-T2-W7 | Qwen2.5-Coder 7B Q4 (~6GB) | `poolside/laguna-s-2.1:free` | Test orchestration |
| EDA-T2-W8 | Qwen2.5-Coder 7B Q4 (~6GB) | `deepseek/deepseek-r1:free` | Changelog + community copy |
| EDA-T3-W9.1 | Qwen2.5-VL 7B Q4 (~7GB) | `poolside/laguna-s-2.1:free` | Vision for 3D analysis |
| EDA-T3-W9.2 | DeepSeek-R1-Distill 7B (~6GB) | `deepseek/deepseek-r1:free` | Math/reasoning for SI |
| EDA-T3-W10.1 | DeepSeek-R1-Distill 7B (~6GB) | `deepseek/deepseek-r1:free` | Power mesh math |
| EDA-T3-W10.2 | Llama-3.1 8B Q4 (~7GB) | `poolside/laguna-s-2.1:free` | Thermal reasoning |
| EDA-T3-W11.1 | Qwen2.5-Coder 7B Q4 (~6GB) | `deepseek/deepseek-r1:free` | DFM rule parsing |
| EDA-T3-W11.2 | Qwen2.5-VL 7B Q4 (~7GB) | `poolside/laguna-s-2.1:free` | Texture format validation |
| EDA-T3-W12 | Qwen2.5-Coder 7B Q4 (~6GB) | `deepseek/deepseek-r1:free` | Integration test orchestration |
| EDA-T3-W13W14 | TinyLlama 1.1B (~1GB) | `poolside/laguna-s-2.1:free` | Issue triage, feedback |
| EDA-T4-W15.1 | DeepSeek-R1-Distill 7B (~6GB) | `deepseek/deepseek-r1:free` | Scope analysis, data audit |
| EDA-T4-W15.2 | TinyLlama 1.1B (~1GB) | `poolside/laguna-s-2.1:free` | Minimal key management |
| EDA-T4-W15.3 | DeepSeek-R1-Distill 7B (~6GB) | `deepseek/deepseek-r1:free` | Data flow analysis (P0!) |
| EDA-T4-W16.1 | Qwen2.5-Coder 7B Q4 (~6GB) | `deepseek/deepseek-r1:free` | Docker + LLM serving |
| EDA-T4-W16.2 | Llama-3.1 8B Q4 (~7GB) | `deepseek/deepseek-r1:free` | GDPR compliance reasoning |
| EDA-T4-W17.1 | Qwen2.5-Coder 7B Q4 (~6GB) | `deepseek/deepseek-r1:free` | SAML XML parsing |
| EDA-T4-W17.2 | DeepSeek-R1-Distill 7B (~6GB) | `deepseek/deepseek-r1:free` | Audit log analysis (P0!) |
| EDA-T4-W18 | Qwen2.5-Coder 7B Q4 (~6GB) | `deepseek/deepseek-r1:free` | Changelog + release notes |
| EDA-T4-W19W20 | TinyLlama 1.1B (~1GB) | `deepseek/deepseek-r1:free` | Customer communication |
| EDA-T5-W21.1 | TinyLlama 1.1B (~1GB) | `poolside/laguna-s-2.1:free` | Billing logic |
| EDA-T5-W21.2 | Qwen2.5-Coder 7B Q4 (~6GB) | `deepseek/deepseek-r1:free` | Intent classification |
| EDA-T5-W22.1 | TinyLlama 1.1B (~1GB) | `poolside/laguna-s-2.1:free` | Tweet generation |
| EDA-T5-W22.2 | Qwen2.5-Coder 7B Q4 (~6GB) | `deepseek/deepseek-r1:free` | Documentation content |
| EDA-T5-W23.1 | TinyLlama 1.1B (~1GB) | `poolside/laguna-s-2.1:free` | Script generation |
| EDA-T5-W23.2 | TinyLlama 1.1B (~1GB) | `poolside/laguna-s-2.1:free` | Bot commands |
| EDA-T5-W24 | Qwen2.5-Coder 7B Q4 (~6GB) | `deepseek/deepseek-r1:free` | Sales outreach |
| EDA-T5-W25W26 | Qwen2.5-Coder 7B Q4 (~6GB) | `deepseek/deepseek-r1:free` | Crash log analysis |

---

## Task Card Summary

| Phase | Total Cards | P0 Blockers | P1 High | P2 Medium |
|-------|-------------|-------------|---------|-----------|
| **NBS** | 7 (2 P0 + 5 P1) | NBS-P0-01 to NBS-P0-06 | NBS-P1-01 to NBS-P1-05 | 0 |
| **CSP** | 7 (4 P0 + 3 P1 + 1 P2*) | CSP-P0-01 to CSP-P0-04 | CSP-P1-01 to CSP-P1-05 | 0 |
| **NXIO** | 5 (0 P0 + 5 P1) | — | NXIO-P1-01 to NXIO-P1-05 | 0 |
| **DSP** | 4 (0 P0 + 4 P1) | — | DSP-P1-01 to DSP-P1-04 | 0 |
| **OBS** | 4 (2 P0 + 2 P1) | OBS-P0-01, OBS-P0-02 | OBS-P1-01, OBS-P1-02 | 0 |
| **EDA P2** | 8 (0 P0 + 0 P1 + 8 P2) | — | — | EDA-T2-W5.1 through EDA-T2-W8 |
| **EDA P3** | 8 (0 P0 + 0 P1 + 7 P2 + 1 P0 in P4) | — | — | EDA-T3-W9.1 through EDA-T3-W13W14 |
| **EDA P4** | 8 (2 P0 + 0 P1 + 6 P2) | EDA-T4-W15.3, EDA-T4-W17.2 | — | EDA-T4-W16.1 through EDA-T4-W19W20 |
| **EDA P5** | 7 (1 P0 + 0 P1 + 6 P2) | EDA-T5-W24 | — | EDA-T5-W21.1 through EDA-T5-W25W26 |
| **NEXUS-ST** | 2 (0 P0 + 2 P1) | — | NEXUS-ST-P1-01, NEXUS-ST-P1-02 | 0 |
| **TOTAL** | 56 cards | 8 P0 blockers | 23 P1 high | 25 P2 medium |

> **Note**: CSP-P1-04 (pluginval) is marked as P2-level effort despite P1 priority because it requires external tool installation. The 18 P0/P1 cards are the Phase 1 output. The 25 Phase 2–5 cards (38 total) are the P2 roadmap. This document contains all 56 cards.

---

## Model Fallback Strategy

| Scenario | Primary | Fallback 1 | Fallback 2 |
|----------|---------|------------|------------|
| **Deep reasoning / architecture** | `nvidia/nemotron-3-super-120b-a12b` | `misralai/mistral-large-2-instruct` | `poolside/laguna-s-2.1:free` |
| **C++ code generation** | `ibm/granite-34b-code-instruct` | `qwen3-coder-32b-q4` (local) | `deepseek/deepseek-r1:free` |
| **Fast triage / dispatch** | `meta/llama-3.1-8b-instruct` | `qwen2.5-coder-7b-q4` (local) | `deepseek/deepseek-r1:free` |
| **Vision tasks** | `meta/llama-3.2-90b-vision-instruct` | `qwen2.5-vl-7b-q4` (local) | `poolside/laguna-s-2.1:free` |
| **Research / general QA** | `poolside/laguna-s-2.1:free` | `deepseek/deepseek-r1:free` | `meta/llama-4-sonic:free` |
| **Local VRAM constrained** | N/A | `gemma4:12b` (light only) | `qwen3:8b` (minimal) |


---
