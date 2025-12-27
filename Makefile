.PHONY: run install test clean lint format typecheck check-all

# Default target: start the MCP server
run:
	uv run server.py

# Install dependencies
install:
	uv sync

# Run tests
test:
	uv run pytest tests/

# Linting
lint:
	uv run ruff check .

# Formatting
format:
	uv run ruff format .

# Type checking
typecheck:
	uv run ty check

# Run all quality checks
check-all: lint format typecheck test

# Clean up local environments and virtual env
clean:
	rm -rf .venv
	rm -rf ~/.mcp-python-executor/envs/*
