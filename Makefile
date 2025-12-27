.PHONY: run install test clean

# Default target: start the MCP server
run:
	uv run server.py

# Install dependencies
install:
	uv sync

# Run tests
test:
	uv run python test_server.py

# Clean up local environments and virtual env
clean:
	rm -rf .venv
	rm -rf ~/.mcp-python-executor/envs/*
