# Contributing to RAGPilot

Thanks for your interest in improving RAGPilot. This guide covers local setup,
how to run the checks, and how to submit changes.

## Development setup

See [`docs/setup.md`](docs/setup.md) for full backend and frontend setup. In short:

```bash
# Backend
cd backend
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux:        source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend (second terminal)
cd frontend
npm install
npm run dev
```

Copy `.env.example` to `.env` (backend config) and, if needed,
`frontend/.env.example` to `frontend/.env`.

## Running checks

Both run automatically in CI on every pull request. Run them locally first:

```bash
# Backend tests
python -m pytest backend

# Frontend type-check + build
cd frontend
npm run build
```

## Submitting changes

1. Fork the repo and create a branch from `main`.
2. Keep changes focused; one logical change per pull request.
3. Add or update tests in `backend/tests/` when you change backend behavior.
4. Make sure `pytest` and `npm run build` pass.
5. Open a pull request describing what changed and why.

## Reporting bugs

Open an issue with steps to reproduce, the dataset/file type involved, and the
observed vs. expected behavior. Logs from the backend console help a lot.
