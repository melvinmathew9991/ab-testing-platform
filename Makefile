.PHONY: install install-dev test test-fast lint format analysis clean

install:            ## Install the package
	pip install -e .

install-dev:        ## Install with development tooling
	pip install -e ".[dev]"

test:               ## Full suite, including calibration runs
	pytest

test-fast:          ## Skip the slow calibration runs
	pytest -m "not slow"

lint:               ## Static checks
	ruff check src tests analysis

format:             ## Apply formatting
	ruff format src tests analysis

analysis:           ## Rebuild the Cookie Cats report and figures
	python analysis/fetch_data.py
	python analysis/run_cookie_cats.py

clean:              ## Remove caches and build artefacts
	rm -rf .pytest_cache .ruff_cache **/__pycache__ *.egg-info build dist
