.PHONY: dev test backend frontend install-backend

# One command: build + run both services (http://localhost:5173).
dev:
	docker compose up --build

# Run backend tests (expects backend/.venv or system Python with requirements installed).
test:
	cd backend && pytest -q

# --- Non-docker dev (lighter on memory) ---
# Terminal 1:
backend:
	cd backend && uvicorn app.main:app --reload --port 8000

# Terminal 2:
frontend:
	cd frontend && npm install && npm run dev

install-backend:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
