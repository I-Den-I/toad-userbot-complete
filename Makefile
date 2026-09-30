.DEFAULT_GOAL := help
UV ?= uv
GIT_COMMIT ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo unknown)
export GIT_COMMIT

.PHONY: help install lint format typecheck test check run login docker-build up down logs

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

install: ## Install dependencies and git hooks
	$(UV) sync
	$(UV) run pre-commit install

lint: ## Lint and check formatting
	$(UV) run ruff check .
	$(UV) run ruff format --check .

format: ## Apply formatting and safe lint fixes
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

typecheck: ## Static type checking (strict)
	$(UV) run mypy

test: ## Run tests with coverage
	$(UV) run pytest --cov --cov-report=term

check: lint typecheck test ## Everything CI runs

run: ## Run locally (needs .env and a session)
	$(UV) run toad-userbot run

login: ## Create the Telegram session interactively
	$(UV) run toad-userbot login

docker-build: ## Build the Docker image
	docker compose build

up: ## Start the container in the background
	docker compose up -d --build

down: ## Stop the container
	docker compose down

logs: ## Follow container logs
	docker compose logs -f --tail=100
