# Makefile for koji-adjutant
#
# Common targets:
#   make build    - Build wheel distribution
#   make install  - Install package locally
#   make test     - Run test suite
#   make lint     - Run code quality checks
#   make clean    - Remove build artifacts
#   make dev      - Install in development mode

.PHONY: help build install test lint clean dev coverage dist

# Default target
help:
	@echo "Koji-Adjutant Makefile"
	@echo ""
	@echo "Available targets:"
	@echo "  make build      - Build wheel distribution via tox"
	@echo "  make dist       - Build wheel and source distribution"
	@echo "  make install    - Install package locally"
	@echo "  make dev        - Install in editable/development mode"
	@echo "  make test       - Run test suite via tox"
	@echo "  make lint       - Run code quality checks (flake8, mypy, etc.)"
	@echo "  make coverage   - Generate test coverage report"
	@echo "  make clean      - Remove build artifacts and cache files"
	@echo "  make help       - Show this help message"
	@echo ""

# Build wheel distribution
build:
	@echo "Building wheel distribution via tox..."
	tox -e build
	@echo ""
	@echo "Build complete! Wheel available in dist/"
	@ls -lh dist/*.whl 2>/dev/null || echo "No wheels found"

# Build both wheel and source distribution
dist:
	@echo "Building distributions..."
	python3 -m build
	@echo ""
	@echo "Distributions built:"
	@ls -lh dist/

# Install package locally
install:
	@echo "Installing koji-adjutant..."
	python3 -m pip install .
	@echo ""
	@echo "Installation complete. Try: kojid --help"

# Install in development mode (editable)
dev:
	@echo "Installing koji-adjutant in editable mode..."
	python3 -m pip install -e .[dev]
	@echo ""
	@echo "Development installation complete."
	@echo "Changes to source files will be reflected immediately."

# Run tests
test:
	@echo "Running test suite via tox..."
	tox -e py3

# Run linting
lint:
	@echo "Running code quality checks..."
	tox -e lint

# Generate coverage report
coverage:
	@echo "Generating coverage report..."
	tox -e coverage
	@echo ""
	@echo "Coverage report generated in htmlcov/"
	@echo "Open htmlcov/index.html in browser to view"

# Clean build artifacts
clean:
	@echo "Cleaning build artifacts..."
	rm -rf build/ dist/ *.egg-info htmlcov/ .coverage .pytest_cache .tox
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
	find . -type f -name '*.pyo' -delete
	@echo "Clean complete."

# Run all quality checks
check: lint test
	@echo "All quality checks passed!"

# The end.
