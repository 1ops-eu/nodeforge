.PHONY: venv install install-dev test test-local test-all lint validate-example plan-example docs-example clean

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

# ── Virtualenv ─────────────────────────────────────────────────────────────────

venv:
	python3 -m venv $(VENV)
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

# ── Maintenance ────────────────────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache dist build *.egg-info BOOTSTRAP.md
