VENV = .venv
PYTHON = $(VENV)/bin/python
PIP = $(VENV)/bin/pip

.PHONY: setup ctfd-up ctfd-down run test lint replay tune

setup:
	python3.11 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo "Installing tool binaries (may require sudo)..."
	@which nmap || (sudo apt-get install -y nmap 2>/dev/null || brew install nmap 2>/dev/null || echo "Install nmap manually")
	@which binwalk || (pip install binwalk 2>/dev/null || echo "Install binwalk manually")
	@which exiftool || (sudo apt-get install -y exiftool 2>/dev/null || brew install exiftool 2>/dev/null || echo "Install exiftool manually")
	@which r2 || echo "Install radare2 manually from https://rada.re/n/"

ctfd-up:
	docker compose -f ctfd/docker-compose.yml up -d

ctfd-down:
	docker compose -f ctfd/docker-compose.yml down

run:
	$(PYTHON) runner.py --challenge $(CHALLENGE)

test:
	$(PYTHON) -m pytest tests/ -v

lint:
	$(PYTHON) -m ruff check .

replay:
	$(PYTHON) scripts/replay_run.py --run $(RUN)

tune:
	$(PYTHON) scripts/tune_thresholds.py
