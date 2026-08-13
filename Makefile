.PHONY: test test-unit test-all test-ci install run-api coverage

# Run all tests (default)
test: test-all

# Run all unit tests
test-all:
	python -m pytest tests/ -v

# Run unit tests only
test-unit:
	python -m pytest tests/ -v --ignore=tests/test_integration_pipeline.py

# Run tests with coverage report
coverage:
	pip install pytest-cov
	python -m pytest tests/ --cov=agent --cov=api --cov-report=term-missing --cov-report=html

# CI test run (same as test-all, used by GitHub Actions)
test-ci:
	python -m pytest tests/ -v --tb=short

install:
	pip install -r requirements.txt

run-api:
	uvicorn api.main:app --reload --port 8000