VENV = .venv
PYTHON = $(VENV)/bin/python
PIP = $(VENV)/bin/pip

.PHONY: setup build up down challenges run run-docker test lint replay tune

# Local dev setup (Linux/Mac or WSL)
setup:
	python3.11 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

# Docker workflow (recommended on Windows)
build:
	docker compose build runner

up:
	docker compose up -d ctfd

down:
	docker compose down

# Push starter challenges to CTFd (requires CTFd running + CTFD_TOKEN in .env)
challenges:
	$(PYTHON) scripts/push_challenges.py

# Run locally (Linux/WSL)
run:
	$(PYTHON) runner.py --challenge $(CHALLENGE)

# Run in Docker (Windows-friendly — no WDAC, tools pre-installed)
run-docker:
	docker compose run --rm runner --challenge $(CHALLENGE)

test:
	$(PYTHON) -m pytest tests/ -v

lint:
	$(PYTHON) -m ruff check .

replay:
	$(PYTHON) scripts/replay_run.py --run $(RUN)

tune:
	$(PYTHON) scripts/tune_thresholds.py
