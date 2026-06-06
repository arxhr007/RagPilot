# Setup

## Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:OPENAI_API_KEY="your_key_here"
uvicorn app.main:app --reload
```

Backend API: `http://127.0.0.1:8000`

## Frontend

```powershell
cd frontend
npm install
npm run dev
```

Frontend app: `http://127.0.0.1:5173`

## Optional Playwright

Website ingestion uses requests/BeautifulSoup by default. For JS-heavy sites:

```powershell
pip install playwright
playwright install chromium
```

Then call `/api/ingest/url` with `use_playwright: true`.
