.PHONY: install install-backend install-frontend backend frontend dev clean

PY := backend/.venv/bin/python
BACKEND_ENV := MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen PYTHONPATH=.

install: install-backend install-frontend

install-backend:
	python3 -m venv backend/.venv
	backend/.venv/bin/pip install --upgrade pip
	backend/.venv/bin/pip install -r backend/requirements.txt

install-frontend:
	cd frontend && pnpm install

# Run the API (http://localhost:8000)
backend:
	cd backend && $(BACKEND_ENV) .venv/bin/python -m uvicorn app.main:app --reload --port 8000

# Run the web UI (http://localhost:5173, proxies /api to the backend)
frontend:
	cd frontend && pnpm dev

# Run both: backend in the background, frontend in the foreground.
dev:
	cd backend && $(BACKEND_ENV) .venv/bin/python -m uvicorn app.main:app --port 8000 & echo $$! > /tmp/kin_backend.pid
	cd frontend && pnpm dev; kill `cat /tmp/kin_backend.pid` 2>/dev/null

test-backend:
	cd backend && PYTHONPATH=. .venv/bin/python -m pytest -q

clean:
	rm -rf backend/data/projects/* frontend/dist
