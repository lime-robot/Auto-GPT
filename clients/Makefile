VENV = .venv
PYTHON = $(VENV)/bin/python3
PIP = $(VENV)/bin/pip
UVICORN = $(VENV)/bin/uvicorn

include .env
export

export PYTHONPATH := $(PYTHONPATH):..

app: $(VENV)/bin/activate
	$(UVICORN) app_fastapi:app --reload --port 8000

sdk: $(VENV)/bin/activate
	$(PYTHON) client_sdk.py

wrapper: $(VENV)/bin/activate
	$(PYTHON) auto_gpt_wrapper.py

forem: $(VENV)/bin/activate
	$(PYTHON) forem_post.py
	
$(VENV)/bin/activate: requirements.txt ../requirements.txt
	python3 -m venv $(VENV)
	$(PIP) install -r requirements.txt
	$(PIP) install -r ../requirements.txt


clean:
	rm -rf __pycache__
	rm -rf $(VENV)