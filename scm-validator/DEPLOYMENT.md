# SCM Validator Deployment Guide

This guide covers deploying the SCM Validator platform with:
- **Frontend**: Vercel (Next.js)
- **Backend**: Railway, Render, or other Python hosting

---

## Frontend Deployment (Vercel)

### Prerequisites
- GitHub account
- Vercel account (free tier available)

### Steps

1. **Push your code to GitHub**
   ```bash
   cd scm-validator
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin <your-repo-url>
   git push -u origin main
   ```

2. **Deploy to Vercel**
   - Go to [vercel.com](https://vercel.com)
   - Click "Add New Project"
   - Import your GitHub repository
   - Select the `frontend` folder as the root directory
   - Click "Deploy"

3. **Configure Environment Variables** (if needed)
   - In Vercel dashboard, go to Settings > Environment Variables
   - Add: `NEXT_PUBLIC_API_URL=<your-backend-url>`

4. **Your frontend will be live at**: `https://your-app.vercel.app`

---

## Backend Deployment Options

### Option 1: Railway (Recommended)

**Why Railway?**
- Easy Python deployment
- Free tier: 500 hours/month
- Built-in PostgreSQL (better than SQLite for production)
- Persistent storage

**Steps:**

1. **Create Railway Account**
   - Go to [railway.app](https://railway.app)
   - Sign up with GitHub

2. **Deploy Backend**
   ```bash
   # Install Railway CLI
   npm install -g @railway/cli
   
   # Login
   railway login
   
   # Navigate to backend folder
   cd scm-validator/backend
   
   # Initialize Railway project
   railway init
   
   # Deploy
   railway up
   ```

3. **Add PostgreSQL Database** (optional, better than SQLite)
   - In Railway dashboard, click "New"
   - Select "Database" > "PostgreSQL"
   - Railway will automatically set `DATABASE_URL` environment variable

4. **Configure Environment Variables**
   - In Railway dashboard, go to Variables
   - Add any needed variables

5. **Get your backend URL**
   - Railway will provide a URL like: `https://your-app.railway.app`

---

### Option 2: Render

**Why Render?**
- Free tier available
- Automatic deploys from GitHub
- Built-in PostgreSQL

**Steps:**

1. **Create Render Account**
   - Go to [render.com](https://render.com)
   - Sign up with GitHub

2. **Deploy Backend**
   - Click "New" > "Web Service"
   - Connect your GitHub repository
   - Select `backend` folder
   - Configure:
     - **Environment**: Python 3
     - **Build Command**: `pip install -r requirements.txt`
     - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

3. **Add PostgreSQL Database**
   - Click "New" > "PostgreSQL"
   - Name it `scm-validator-db`
   - Link it to your web service

4. **Add Persistent Disk** (for file uploads)
   - In your web service settings
   - Add disk: Mount path `/opt/render/project/src/storage`

---

### Option 3: Fly.io

**Why Fly.io?**
- Global edge deployment
- Persistent volumes
- Good for worldwide access

**Steps:**

1. **Install Fly CLI**
   ```bash
   # Windows
   powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"
   ```

2. **Deploy**
   ```bash
   cd scm-validator/backend
   
   # Login
   fly auth login
   
   # Launch app
   fly launch
   
   # Create volume for storage
   fly volumes create storage_data --size 1
   
   # Deploy
   fly deploy
   ```

---

### Option 4: AWS Lambda + API Gateway (Serverless)

**Why Serverless?**
- Pay per request
- Auto-scaling
- No server management

**Use Mangum adapter for FastAPI:**

```python
# In main.py
from mangum import Mangum

app = FastAPI(title="SCM Agent Validation Platform API")
# ... your existing code ...

handler = Mangum(app)
```

Deploy using AWS SAM or Serverless Framework.

---

## Post-Deployment Configuration

### 1. Update CORS in Backend

Edit `backend/app/main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://your-app.vercel.app",  # Add your Vercel URL
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 2. Update Frontend API URL

Edit `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=https://your-backend.railway.app
```

Or set in Vercel dashboard as environment variable.

### 3. Database Migration (SQLite → PostgreSQL)

If using PostgreSQL on Railway/Render, update `backend/app/db.py`:

```python
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./storage/validator.db")

# For PostgreSQL
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
```

---

## Monitoring & Maintenance

### Railway
- View logs: `railway logs`
- Monitor usage in dashboard

### Render
- Automatic health checks
- View logs in dashboard

### Vercel
- Analytics built-in
- View deployments and logs

---

## Estimated Costs

### Free Tier Limits

| Service | Frontend | Backend | Database | Storage |
|---------|----------|---------|----------|---------|
| **Vercel** | Unlimited | N/A | N/A | N/A |
| **Railway** | N/A | 500hrs/month | 5GB | 1GB |
| **Render** | N/A | 750hrs/month | 1GB | None |
| **Fly.io** | N/A | ~160hrs/month | 3GB | 3GB |

### Recommended Stack for Free
- Frontend: Vercel
- Backend: Railway or Render
- Database: Railway PostgreSQL or Render PostgreSQL

---

## Troubleshooting

### CORS Errors
- Ensure backend CORS allows your Vercel domain
- Check environment variables are set correctly

### Database Connection Issues
- Verify `DATABASE_URL` environment variable
- For PostgreSQL, ensure connection string format is correct

### File Upload Issues
- Ensure persistent storage is configured (Railway/Render disk)
- Check file permissions in storage directories

### Build Failures
- Check Python version (3.11+ recommended)
- Verify all dependencies in `requirements.txt`

---

## Quick Start Commands

```bash
# Deploy Frontend to Vercel
cd frontend
vercel

# Deploy Backend to Railway
cd backend
railway login
railway init
railway up

# View logs
railway logs  # Railway
vercel logs   # Vercel
```

---

## Support

- Railway: [docs.railway.app](https://docs.railway.app)
- Render: [render.com/docs](https://render.com/docs)
- Vercel: [vercel.com/docs](https://vercel.com/docs)
- Fly.io: [fly.io/docs](https://fly.io/docs)
