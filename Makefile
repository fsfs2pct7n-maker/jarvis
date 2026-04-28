.PHONY: setup run stop clean install

VENV = venv
PYTHON = $(VENV)/bin/python
PIP = $(VENV)/bin/pip

setup:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo "Setup complete. Run 'make run' to start Jarvis."

run:
	@./start.sh

stop:
	@pkill -f "uvicorn main:app" 2>/dev/null || true
	@pkill -f "jarvis" 2>/dev/null || true
	@echo "Jarvis stopped."

install:
	$(PIP) install -r requirements.txt

clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete

logs:
	tail -f logs/jarvis.log

status:
	@curl -s http://localhost:8000/status | python3 -m json.tool 2>/dev/null || echo "Jarvis is not running."
