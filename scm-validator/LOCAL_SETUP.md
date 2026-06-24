# 🚀 SCM Validator - Local Development Setup

## ✅ Currently Running

### Backend (FastAPI)
- **URL**: http://localhost:8000
- **Status**: ✅ Running
- **Process ID**: Terminal 9
- **Health**: http://localhost:8000/api/health
- **Logs**: Auto-reload enabled (watches for code changes)

### Frontend (Next.js)
- **URL**: http://localhost:3000
- **Status**: ✅ Running  
- **Process ID**: Terminal 10
- **Environment**: Using `.env.local` (points to localhost:8000)
- **Hot Reload**: ✅ Enabled (Turbopack)

---

## 🎯 Quick Start

### Open the Application
```
http://localhost:3000
```

### Test the Backend
```bash
curl http://localhost:8000/api/health
# Expected: {"status":"ok"}
```

---

## 🔧 Development Commands

### Stop All Services
In the terminal or via commands:
- Frontend: Press Ctrl+C in terminal 10
- Backend: Press Ctrl+C in terminal 9

### Restart Backend
```bash
cd backend
.venv\Scripts\activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Restart Frontend
```bash
cd frontend
npm run dev
```

---

## 📁 Project Structure

```
scm-validator/
├── backend/
│   ├── app/
│   │   ├── api/         # API endpoints
│   │   ├── engine/      # Validation engine
│   │   │   ├── pipeline.py
│   │   │   ├── rule_engine_v2.py
│   │   │   ├── scoring_engine_v2.py
│   │   │   ├── repo_ingestor.py
│   │   │   └── ...
│   │   ├── main.py      # FastAPI app
│   │   └── db.py        # SQLite database
│   ├── storage/         # Uploaded files & workspaces
│   └── requirements.txt
│
└── frontend/
    ├── app/             # Next.js pages
    ├── components/      # React components
    ├── lib/            # API client & types
    └── package.json
```

---

## 🧪 Testing Locally

### 1. Test with GitHub Repository
1. Go to http://localhost:3000
2. Click "New Validation"
3. Enter:
   - Agent Name: "Test Agent"
   - Repo URL: `https://github.com/yourusername/your-repo`
4. Click "Run Validation"
5. Wait for completion (watch backend logs)

### 2. Test with File Upload
1. Go to http://localhost:3000
2. Click "New Validation"
3. Enter Agent Name
4. Upload Python files (.py) or a ZIP file
5. Click "Run Validation"

### 3. View Results
- Trust score
- Demo readiness
- Production readiness
- Detailed findings
- Recommendations

---

## 🔍 Backend API Endpoints

### Health Check
```
GET http://localhost:8000/api/health
```

### Create Validation Run
```
POST http://localhost:8000/api/runs
Content-Type: multipart/form-data

Fields:
- agent_name (required)
- repo_url (optional)
- use_case (optional)
- files (optional - upload)
```

### Get Run Status
```
GET http://localhost:8000/api/runs/{run_id}/status
```

### Get Validation Results
```
GET http://localhost:8000/api/runs/{run_id}/results
```

### List All Runs
```
GET http://localhost:8000/api/runs
```

---

## 🗄️ Database

**Location**: `backend/storage/validator.db`

**Type**: SQLite

**Tables**:
- `runs` - Validation run metadata
- `findings` - Issues detected
- `recommendations` - Fix suggestions
- `evidence` - Code snippets
- `score_breakdown` - Score by dimension
- `positive_signals` - Good patterns found
- `ai_insights` - LLM commentary (if enabled)

### View Database
```bash
cd backend/storage
sqlite3 validator.db
.tables
SELECT * FROM runs;
```

---

## 🛠️ Making Changes

### Backend Changes
1. Edit files in `backend/app/`
2. Save - auto-reload will restart server
3. Check logs for errors
4. Test API endpoint

### Frontend Changes
1. Edit files in `frontend/app/` or `frontend/components/`
2. Save - hot reload will update browser automatically
3. Check browser console for errors

### Rule Engine Changes
Edit `backend/app/engine/rule_engine_v2.py`:
- Add new rules in `run_all_rules()`
- Each rule checks patterns and returns findings
- Rules are deterministic (no randomness)

### Scoring Changes
Edit `backend/app/engine/scoring_engine_v2.py`:
- Modify score calculation logic
- Adjust dimension weights
- Change readiness thresholds

---

## 📊 Monitoring

### Backend Logs (Terminal 9)
- API requests
- Validation progress
- Errors and warnings
- Auto-reload events

### Frontend Logs (Terminal 10)
- Page requests
- API calls
- Build status
- Hot reload events

### Browser Console (F12)
- Network requests
- API responses
- React errors
- Frontend logs

---

## 🐛 Troubleshooting

### Backend Not Starting
```bash
# Check if port 8000 is in use
netstat -ano | findstr :8000

# Kill process if needed
taskkill /PID <PID> /F

# Reinstall dependencies
cd backend
.venv\Scripts\activate
pip install -r requirements.txt
```

### Frontend Not Starting
```bash
# Check if port 3000 is in use
netstat -ano | findstr :3000

# Kill process if needed
taskkill /PID <PID> /F

# Reinstall dependencies
cd frontend
npm install
```

### CORS Errors
Check `backend/app/main.py`:
```python
allow_origins=["http://localhost:3000"]
```

### Database Locked
```bash
# Stop backend
# Delete database (will recreate on startup)
del backend\storage\validator.db
```

---

## 📝 Development Workflow

### 1. Start Services
```bash
# Terminal 1: Backend
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload

# Terminal 2: Frontend
cd frontend
npm run dev
```

### 2. Make Changes
- Edit code
- Save files
- Services auto-reload

### 3. Test Changes
- Frontend: http://localhost:3000
- Backend: http://localhost:8000/api/health
- Run validation to test end-to-end

### 4. Commit Changes
```bash
git add .
git commit -m "Description of changes"
git push origin main
```

### 5. Deploy (Automatic)
- Railway: Auto-deploys from GitHub
- Vercel: Auto-deploys from GitHub
- Check dashboards for deployment status

---

## 🎉 You're All Set!

**Frontend**: http://localhost:3000
**Backend**: http://localhost:8000

Try running a validation to test everything is working!
