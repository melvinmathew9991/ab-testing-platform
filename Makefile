.PHONY: install install-dev test test-fast lint format analysis api ui stack docker-api clean

install:            ## Install the package
	pip install -e .

install-dev:        ## Install with development tooling
	pip install -e ".[dev]"

test:               ## Full suite, including calibration runs
	pytest

test-fast:          ## Skip the slow calibration runs
	pytest -m "not slow"

lint:               ## Static checks
	ruff check src tests analysis services

format:             ## Apply formatting
	ruff format src tests analysis services

analysis:           ## Rebuild the Cookie Cats report and figures
	python analysis/fetch_data.py
	python analysis/run_cookie_cats.py

api:                ## Run the API locally on :8000
	cd services/api && uvicorn app.main:app --reload --port 8000

ui:                 ## Run the interface locally on :8501 (needs the API)
	cd services/ui && streamlit run ui/main.py --server.port 8501

stack:              ## Build and run both services in containers
	docker compose up --build

docker-api:         ## Build and run the API container on :8000
	docker build -f services/api/Dockerfile -t ab-api:local .
	docker run --rm -p 8000:8080 ab-api:local

clean:              ## Remove caches and build artefacts
	rm -rf .pytest_cache .ruff_cache **/__pycache__ *.egg-info build dist
