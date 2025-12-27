.PHONY: run install test clean lint format typecheck check-all

# Default target: start the MCP server
run:
	uv run mcp-python-executor

# Install dependencies
install:
	uv sync

# Run tests with coverage
test:
	uv run pytest

# Open coverage report in browser
coverage: test
	open htmlcov/index.html

# Run all quality checks
check-all: lint format typecheck test

# Clean up local environments, virtual env, and coverage files
clean:
	rm -rf .venv
	rm -rf ~/.mcp-python-executor/envs/*
	rm -rf .pytest_cache
	rm -rf .coverage
	rm -rf htmlcov
