.PHONY: venv install install-dev test test-local test-all lint validate-example plan-example docs-example test-goss clean

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

# ── Virtualenv ─────────────────────────────────────────────────────────────────

venv:
	virtualenv $(VENV)
	@echo "Virtualenv created. Activate with: source .venv/bin/activate"

# ── Install ────────────────────────────────────────────────────────────────────

install: venv
	$(PIP) install -r requirements.txt

install-dev: venv
	$(PIP) install -r requirements-dev.txt
	$(PIP) install -e .

# ── Tests ──────────────────────────────────────────────────────────────────────

test:
	pytest tests/test_specs/ tests/test_compiler/ tests/test_plan/ tests/test_runtime/ tests/test_cli/ -v

test-local:
	pytest tests/test_local/ -v

test-all:
	pytest tests/ -v

# ── Smoke tests (no remote needed) ────────────────────────────────────────────

validate-example:
	nodeforge validate examples/bootstrap.yaml

plan-example:
	nodeforge plan examples/bootstrap.yaml

docs-example:
	nodeforge docs examples/bootstrap.yaml -o BOOTSTRAP.md
	@echo "Docs written to BOOTSTRAP.md"

# ── Goss integration tests (requires a live Ubuntu server) ────────────────────
# Goss is shipped and run automatically by `nodeforge apply` for bootstrap specs.
# Use this target to manually re-run a static reference spec or the master gossfile.
#
# Usage:
#   make test-goss HOST=203.0.113.10 PORT=2222 USER=admin
#       → runs the master ~/.goss/goss.yaml on the server (all shipped specs)
#
#   make test-goss HOST=203.0.113.10 PORT=2222 USER=admin \
#        SPEC=examples/ubuntu/04-firewall-ssh2222/04-firewall-ssh2222.goss.yaml
#       → copies a specific static reference spec and runs it

SPEC ?=
HOST ?= 203.0.113.10
PORT ?= 22
USER ?= admin

test-goss:
	@if [ -n "$(SPEC)" ]; then \
	  echo ">>> Copying $(SPEC) to $(USER)@$(HOST):~/.goss/ (port $(PORT))"; \
	  ssh -p "$(PORT)" "$(USER)@$(HOST)" "mkdir -p ~/.goss"; \
	  scp -P "$(PORT)" "$(SPEC)" "$(USER)@$(HOST):~/.goss/$$(basename $(SPEC))"; \
	fi
	@echo ">>> Running goss validate on $(HOST)"
	ssh -p "$(PORT)" "$(USER)@$(HOST)" "goss -g ~/.goss/goss.yaml validate"

# ── Maintenance ────────────────────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache dist build *.egg-info BOOTSTRAP.md
