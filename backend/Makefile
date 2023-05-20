VENV = .venv
PYTHON = $(VENV)/bin/python3
PIP = $(VENV)/bin/pip
UVICORN = $(VENV)/bin/uvicorn

include .env
export


app: $(VENV)/bin/activate
	$(UVICORN) app:app --reload --port 1024 

$(VENV)/bin/activate: requirements.txt ../requirements.txt
	python3 -m venv $(VENV)
	$(PIP) install -r requirements.txt
	$(PIP) install -r ../requirements.txt


clean:
	rm -rf __pycache__
	rm -rf $(VENV)