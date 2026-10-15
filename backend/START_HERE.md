# Start the Aveon Backend (fix "Backend is not reachable")

The login page needs the **API server** running on **http://localhost:8000**. If you see "Backend is not reachable" or "localhost refused to connect", start the backend as below.

## Option 1: Double-click (Windows)

1. Open folder: **`d:\ESSL\ESSL_SW\Aveon\backend`**
2. Double-click **`run.bat`**
3. A terminal window will open. Wait until you see:
   ```text
   Uvicorn running on http://0.0.0.0:8000
   ```
4. In the browser open **http://localhost:8000/health** — you should see `{"status":"ok"}`.
5. Refresh the **login page** (http://localhost:5173/login) and log in.

If the window closes immediately or shows an error, use Option 2 so you can see the message.

---

## Option 2: Terminal (recommended if Option 1 fails)

1. Open **PowerShell** or **Command Prompt**.
2. Go to the backend folder:
   ```powershell
   cd d:\ESSL\ESSL_SW\Aveon\backend
   ```
3. Activate the virtual environment (if you have one):
   - **PowerShell:**  
     `.\.venv\Scripts\Activate.ps1`  
     (If you get "script execution disabled", run once as Admin:  
     `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`)
   - **Command Prompt:**  
     `.venv\Scripts\activate.bat`
4. Start the server:
   ```powershell
   python -m uvicorn app.main:app --reload --port 8000
   ```
5. Leave this window open. When you see `Uvicorn running on http://0.0.0.0:8000`, the backend is ready.
6. Test: open **http://localhost:8000/health** in the browser → `{"status":"ok"}`.
7. Refresh the login page and log in with **admin** / **admin123**.

---

## Common errors

| Error | What to do |
|-------|------------|
| **"python" is not recognized** | Install Python 3.10+ from python.org. Add Python to PATH. Then in `Aveon/backend`: `python -m venv .venv` and `.venv\Scripts\pip install -r requirements.txt`. |
| **No module named 'uvicorn'** or **'app'** | From `Aveon/backend` run: `.venv\Scripts\pip install -r requirements.txt` (with venv activated). |
| **Address already in use** / **Port 8000** | Another app is using port 8000. Close it or use a different port: `python -m uvicorn app.main:app --reload --port 8001` and set in frontend `.env`: `VITE_API_BASE_URL=http://localhost:8001/api/v1`. |
| **ODBC / SQL Server** errors when opening other pages | Database is not running or connection in `.env` is wrong. The server and login still work; fix `.env` (or start SQL Server) for full features. |

---

## Quick check

- Backend running: **http://localhost:8000/health** → `{"status":"ok"}`
- API docs: **http://localhost:8000/docs**
- Frontend: **http://localhost:5173/login** (start frontend from `Aveon/frontend` with `npm run dev` if needed).
