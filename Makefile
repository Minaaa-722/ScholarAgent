.PHONY: test test-unit test-all test-ci install run-api coverage docker-build docker-run docker-push

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

# Docker build — multi-stage, tags as scholaragent:latest
docker-build:
	docker build -t scholaragent:latest .

# Docker build (no-cache)
docker-build-clean:
	docker build --no-cache -t scholaragent:latest .

# Docker run — maps port 8000, loads .env for API keys
docker-run:
	docker run -p 8000:8000 --env-file .env scholaragent:latest

# Docker run (detached)
docker-run-d:
	docker run -d -p 8000:8000 --name scholaragent --env-file .env scholaragent:latest

# Docker push (tag as registry image first)
docker-push:
	@echo "Usage: docker tag scholaragent:latest your-registry/scholaragent:latest"
	@echo "       docker push your-registry/scholaragent:latest"