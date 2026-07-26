.PHONY: test install run

test:
	python -m pytest tests/ -v

install:
	pip install -r requirements.txt

run-api:
	uvicorn api.main:app --reload --port 8000