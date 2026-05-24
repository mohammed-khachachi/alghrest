# ALGHREST Platform Automation Command Hub
# Designed for developer workflows on Windows and Linux

.PHONY: help install docker-up docker-down test format lint clean mock-server dashboard-dev run-cio run-risk run-proposal

help:
	@echo "====================================================================="
	@echo "                   ALGHREST COMMAND HUB"
	@echo "====================================================================="
	@echo "install         - Install project dependencies using Poetry"
	@echo "docker-up       - Spin up multi-agent Docker infrastructure stack"
	@echo "docker-down     - Stop and teardown active infrastructure stack"
	@echo "test            - Run entire pytest regression suite"
	@echo "format          - Format code using black & isort"
	@echo "lint            - Run static analysis via ruff"
	@echo "mock-server     - Run fast FastAPI development mock server on port 8000"
	@echo "dashboard-dev   - Start React development server on http://localhost:5173"
	@echo "clean           - Purge all temporary build/runtime logs and cache files"
	@echo "---------------------------------------------------------------------"
	@echo "run-cio         - Run CIO Executive Agent locally"
	@echo "run-risk        - Run Risk Governor Agent locally"
	@echo "run-proposal    - Run Proposal Approver Agent locally"
	@echo "====================================================================="

install:
	poetry install

docker-up:
	docker compose up -d

docker-down:
	docker compose down

test:
	poetry run pytest -m "unit or integration"

format:
	poetry run black .
	poetry run isort .

lint:
	poetry run ruff check .

mock-server:
	poetry run python api/mock_server.py

dashboard-dev:
	cd dashboard && npm install && npm run dev

run-cio:
	poetry run python run_agent.py agents.tier1_executive.cio_agent CIOAgent

run-risk:
	poetry run python run_agent.py agents.tier1_executive.risk_governor RiskGovernor

run-proposal:
	poetry run python run_agent.py agents.tier1_executive.proposal_approver ProposalApprover

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.log" -delete
