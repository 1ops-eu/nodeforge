.PHONY: help venv install dev test test-local test-all lint fmt \
        validate-example plan-example docs-example smoke \
        build-binary build-agent-binary build-docker test-goss clean

VENV      := .venv
PYTHON    := $(VENV)/bin/python
PIP       := $(VENV)/bin/pip
APP_NAME  := loft-cli
IMAGE_NAME ?= ghcr.io/1ops-eu/loft-cli
VERSION   ?= $(shell python -c "import tomllib; print(tomllib.load(open('packages/core/pyproject.toml','rb'))['project']['version'])" 2>/dev/null || python -c "import tomli; print(tomli.load(open('packages/core/pyproject.toml','rb'))['project']['version'])" 2>/dev/null || grep '^version' packages/core/pyproject.toml | head -1 | cut -d'"' -f2)

# ── Help ───────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "loft-cli — available targets"
	@echo ""
	@echo "  Setup"
	@echo "    make venv            Create .venv virtualenv"
	@echo "    make install         Install all packages (runtime deps)"
	@echo "    make dev             Install all packages + dev deps (editable)"
	@echo ""
	@echo "  Testing"
	@echo "    make test            Run unit/integration tests (no live host needed)"
	@echo "    make test-local      Run tests requiring sqlcipher3 locally"
	@echo "    make test-all        Run all tests"
	@echo ""
	@echo "  Code quality"
	@echo "    make lint            Run ruff + black --check"
	@echo "    make fmt             Auto-format with black"
	@echo ""
	@echo "  Smoke tests (no remote host needed)"
	@echo "    make validate-example   Validate all example specs"
	@echo "    make plan-example       Plan all example specs"
	@echo "    make docs-example       Generate docs for all example specs"
	@echo "    make smoke              Run all smoke tests"
	@echo ""
	@echo "  Distribution"
	@echo "    make build-binary         Build standalone CLI binary via PyInstaller"
	@echo "    make build-agent-binary   Build standalone agent binary via PyInstaller"
	@echo "    make build-docker         Build Docker image ($(IMAGE_NAME):$(VERSION))"
	@echo ""
	@echo "  Goss integration tests (requires a live Ubuntu server)"
	@echo "    make test-goss HOST=<ip> PORT=<port> USER=<user>"
	@echo ""
	@echo "  Maintenance"
	@echo "    make clean           Remove all build artifacts"
	@echo ""

# ── Virtualenv ─────────────────────────────────────────────────────────────────

venv:
	@if [ ! -f "$(VENV)/bin/activate" ]; then \
		echo "Creating virtual environment..."; \
		if ! command -v virtualenv >/dev/null 2>&1; then \
			echo "virtualenv not found, installing via pip..."; \
			pip install --user virtualenv || { echo "Failed to install virtualenv"; exit 1; }; \
		fi; \
		virtualenv $(VENV) || { echo "Failed to create virtualenv"; exit 1; }; \
	else \
		echo "Virtual environment already exists. Skipping..."; \
	fi

# ── Install ────────────────────────────────────────────────────────────────────

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install packages/core packages/client packages/agent

dev: venv
	$(PIP) install --upgrade pip
	$(PIP) install -e packages/core -e packages/client -e packages/agent -e ".[dev]"

# ── Tests ──────────────────────────────────────────────────────────────────────

test:
	pytest tests/test_specs/ tests/test_compiler/ tests/test_plan/ tests/test_runtime/ tests/test_cli/ tests/test_agent/ -v

test-local:
	pytest tests/test_local/ -v

test-all:
	pytest tests/ -v

# ── Code quality ───────────────────────────────────────────────────────────────

lint:
	ruff check .
	black --check .

fmt:
	black .

# ── Smoke tests (no remote needed) ────────────────────────────────────────────

validate-example:
	@failed=0; \
	for spec in $$(find examples -name '*.yaml' ! -name '*.goss.yaml' ! -name 'policy.yaml' | sort); do \
	  name=$$(basename "$$spec"); \
	  case "$$name" in \
	    bootstrap-env-vars.yaml|bootstrap-password-login.yaml) flags="--passthrough" ;; \
	    *) flags="" ;; \
	  esac; \
	  echo ">>> Validating $$spec"; \
	  loft-cli validate "$$spec" $$flags || failed=1; \
	done; \
	[ "$$failed" -eq 0 ]

plan-example:
	@failed=0; \
	for spec in $$(find examples -name '*.yaml' ! -name '*.goss.yaml' ! -name 'policy.yaml' | sort); do \
	  name=$$(basename "$$spec"); \
	  case "$$name" in \
	    bootstrap-env-vars.yaml|bootstrap-password-login.yaml) flags="--passthrough" ;; \
	    *) flags="" ;; \
	  esac; \
	  echo ">>> Planning $$spec"; \
	  loft-cli plan "$$spec" $$flags || failed=1; \
	done; \
	[ "$$failed" -eq 0 ]

docs-example:
	@failed=0; \
	for spec in $$(find examples -name '*.yaml' ! -name '*.goss.yaml' ! -name 'policy.yaml' | sort); do \
	  name=$$(basename "$$spec"); \
	  case "$$name" in \
	    bootstrap-env-vars.yaml|bootstrap-password-login.yaml) flags="--passthrough" ;; \
	    *) flags="" ;; \
	  esac; \
	  echo ">>> Generating docs for $$spec"; \
	  loft-cli docs "$$spec" $$flags || failed=1; \
	done; \
	[ "$$failed" -eq 0 ]

smoke: validate-example plan-example docs-example
	@echo "All smoke tests passed."

# ── Distribution ──────────────────────────────────────────────────────────────

build-binary:
	python scripts/build_binary.py

build-agent-binary:
	python scripts/build_agent_binary.py

build-docker:
	docker build \
	  -t $(IMAGE_NAME):$(VERSION) \
	  -t $(IMAGE_NAME):latest \
	  .
	@echo "Built $(IMAGE_NAME):$(VERSION) and $(IMAGE_NAME):latest"

# ── Goss integration tests (requires a live Ubuntu server) ────────────────────

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
	rm -rf .pytest_cache .ruff_cache dist build release *.egg-info *.spec BOOTSTRAP.md
