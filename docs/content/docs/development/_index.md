---
title: "Development"
weight: 70
---

# Development Guide

Contribution guidelines and development setup for Nexus-EDA.

## Development Environment

```bash
# Clone the repo
git clone https://github.com/blockie710/nexus-eda-kicad-plugin.git
cd nexus-eda-kicad-plugin

# Install with Poetry
poetry install
poetry shell

# Run tests
poetry run pytest tests/ -v

# Lint
poetry run ruff check src/
poetry run black --check src/
```

## Testing

```bash
# Run all tests with parallel execution
pytest tests/ -v -n 4

# Run a specific test file
pytest tests/test_netlist.py -v

# Run with coverage
pytest tests/ --cov=nexus_eda --cov-report=html
```

## Code Style

- **Python**: Follow PEP 8 (enforced by `ruff` and `black`)
- **Docstrings**: Use Google-style docstrings
- **Type hints**: Required on all public functions
- **License headers**: Add SPDX-License-Identifier: Apache-2.0 to all files

## Branches

The project uses a worktree-based development model:

| Branch Prefix  | Purpose                          |
|----------------|----------------------------------|
| `master`       | Main branch (stable release)     |
| `wt/T5-W*`     | Weekly feature branches          |
| `wt/T5-Wxx`    | Phase 5 feature work             |

## License Compliance

- **Core engine**: Apache 2.0
- **Pro agent modules**: Proprietary (future)
- **Model weights**: Subject to each model's license (see manifest)
- All code committed to `master` must pass lint and tests in CI
