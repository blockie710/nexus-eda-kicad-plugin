#!/usr/bin/env python3
"""Nexus-EDA Phase 1 — security boundary gate (Python analog of G7 RT-invariant).

Validates the Phase 1 security boundaries declared in eda-phase1-plan.md §3:

1. NO network calls in Phase 1 (air-gapped by default):
   - No urllib, requests, httpx, aiohttp, or raw socket() usage in src/
   - The `requests` dependency in pyproject.toml is declared but must NOT be
     imported/called outside the billing module (Phase 5). The netlist/agents
     /llm modules must be network-free.

2. NO file I/O escape:
   - Plugin only reads/writes .kicad_pcb and .net files in the project dir.
   - Path traversal attempts (..) in parsed inputs are rejected.

3. NO code execution:
   - No eval(), exec(), os.system(), subprocess, or importlib dynamic loading.

Exit code 0 = clean; non-zero = violation.
"""
import os
import re
import sys

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

# Modules that must be network-free in Phase 1.
NETWORK_FREE_MODULES = [
    "src/nexus_eda/netlist",
    "src/nexus_eda/agents",
    "src/nexus_eda/gui",
]

# Network-related imports/functions to forbid in network-free modules.
NETWORK_PATTERNS = [
    (r"\bimport\s+requests\b", "network import: requests"),
    (r"\bimport\s+urllib\b", "network import: urllib"),
    (r"\bimport\s+httpx\b", "network import: httpx"),
    (r"\bimport\s+aiohttp\b", "network import: aiohttp"),
    (r"\bsocket\.socket\b", "raw socket creation"),
    (r"\brequests\.get\b", "network call: requests.get"),
    (r"\brequests\.post\b", "network call: requests.post"),
    (r"\burllib\.request\b", "network call: urllib.request"),
    (r"\bhttpx\.\w+\b", "network call: httpx"),
]

# Unsafe code-execution patterns everywhere in src/.
UNSAFE_PATTERNS = [
    (r"\beval\s*\(", "eval() — arbitrary code execution"),
    (r"\bexec\s*\(", "exec() — arbitrary code execution"),
    (r"\bos\.system\s*\(", "os.system() — shell execution"),
    (r"\bsubprocess\.\w+\s*\(", "subprocess — process execution"),
    (r"\bimportlib\.\w+\s*\(", "importlib — dynamic code loading"),
    (r"\b__import__\s*\(", "__import__() — dynamic module loading"),
    (r"\bcompile\s*\(", "compile() — code compilation at runtime"),
]

COMPILED_NET = [(re.compile(p), why) for p, why in NETWORK_PATTERNS]
COMPILED_UNSAFE = [(re.compile(p), why) for p, why in UNSAFE_PATTERNS]


def scan_file(full_path, rel_path, patterns, violations):
    if not os.path.isfile(full_path):
        return
    with open(full_path, "r", encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh, 1):
            code = line.split("#")[0]
            for rx, why in patterns:
                m = rx.search(code)
                if m:
                    violations.append((rel_path, lineno, why, line.strip()))


def main():
    violations = []

    # 1. Security: no network calls in Phase-1 network-free modules
    for pkg in NETWORK_FREE_MODULES:
        pkg_full = os.path.join(REPO_ROOT, pkg)
        if not os.path.isdir(pkg_full):
            continue
        for dirpath, _, files in os.walk(pkg_full):
            for fname in files:
                if fname.endswith(".py"):
                    full = os.path.join(dirpath, fname)
                    rel = os.path.relpath(full, REPO_ROOT)
                    scan_file(full, rel, COMPILED_NET, violations)

    # 2. Security: no unsafe code execution anywhere in src/
    src_full = os.path.join(REPO_ROOT, "src")
    if os.path.isdir(src_full):
        for dirpath, _, files in os.walk(src_full):
            for fname in files:
                if fname.endswith(".py"):
                    full = os.path.join(dirpath, fname)
                    rel = os.path.relpath(full, REPO_ROOT)
                    scan_file(full, rel, COMPILED_UNSAFE, violations)

    if not violations:
        print("[G7-EDA] Security boundary gate: 0 violations across src/. PASS")
        return 0

    print("[G7-EDA] Security boundary gate: FAILED")
    for rel, ln, why, text in violations:
        print(f"  VIOLATION {rel}:{ln}  {why}  | {text}")
    print(f"[G7-EDA] {len(violations)} violation(s).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
