# pedal-bench — developer commands
#
# Windows users: run these from git bash. GNU Make ships with Git for Windows.

# Python binary lives at a different path inside .venv depending on OS.
# Windows sets OS=Windows_NT in its environment; everything else uses POSIX.
ifeq ($(OS),Windows_NT)
    PYTHON := .venv/Scripts/python.exe
else
    PYTHON := .venv/bin/python
endif
PIP    := $(PYTHON) -m pip
UVICORN := $(PYTHON) -m uvicorn
PYTEST := $(PYTHON) -m pytest

# Adjust if Node installed somewhere non-default.
NODE_DIR := /c/Program Files/nodejs
export PATH := $(NODE_DIR):$(PATH)

.PHONY: help
help:
	@echo "pedal-bench commands:"
	@echo "  make install        create .venv, install backend + frontend deps"
	@echo "  make dev            run backend + frontend dev servers concurrently"
	@echo "  make backend        run only the FastAPI dev server"
	@echo "  make frontend       run only the Vite dev server"
	@echo "  make test           run the Python test suite"
	@echo "  make typecheck      run mypy-style checks on frontend TS"
	@echo "  make build          production build of the frontend"
	@echo "  make clean          remove .venv, node_modules, dist, pycache"

.PHONY: install
install:
	node scripts/setup-venv.mjs
	$(PIP) install --upgrade pip
	$(PIP) install -e "backend[dev]"
	cd frontend && npm install

.PHONY: dev
dev:
	@echo "Starting backend on http://127.0.0.1:8642 and frontend on http://127.0.0.1:5173"
	@echo "Press Ctrl+C to stop both."
	@( trap 'kill 0' SIGINT; \
	  $(UVICORN) pedal_bench.api.app:app --host 127.0.0.1 --port 8642 --reload --app-dir backend & \
	  ( cd frontend && npm run dev ) & \
	  wait )

.PHONY: backend
backend:
	$(UVICORN) pedal_bench.api.app:app --host 127.0.0.1 --port 8642 --reload --app-dir backend

.PHONY: frontend
frontend:
	cd frontend && npm run dev

.PHONY: test
test:
	$(PYTEST) backend/tests -q

.PHONY: typecheck
typecheck:
	cd frontend && npm run typecheck

.PHONY: build
build:
	cd frontend && npm run build

.PHONY: clean
clean:
	rm -rf .venv frontend/node_modules frontend/dist
	find backend -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find backend -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
