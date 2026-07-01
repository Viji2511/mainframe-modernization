# MainframeAI Deployment Guide (Free Tier)

This guide walks you through deploying the MainframeAI application (FastAPI backend + React frontend + PostgreSQL database) using the best and most reliable free-tier hosting services available.

---

## 1. Database Setup (Neon PostgreSQL)
**Neon.tech** offers a fully-managed serverless PostgreSQL database on a generous free tier (0.5 GiB storage, auto-suspend when inactive).

1. Sign up at [Neon.tech](https://neon.tech/).
2. Create a new project (name it `mainframe-db` or similar).
3. Under the dashboard, copy the connection string. It will look like:
   ```connection
   postgresql://[user]:[password]@[host]/neondb?sslmode=require
   ```
4. Keep this string handy. We will inject it as an environment variable in the backend service.

---

## 2. Backend Deployment (Render)
**Render.com** is a cloud hosting provider with a free tier for Web Services running Python/FastAPI.

1. Sign up or log in to [Render.com](https://render.com/).
2. Connect your GitHub repository containing the modernization codebase.
3. Create a new **Web Service** with the following configurations:
   * **Language**: `Python`
   * **Build Command**: `pip install -r requirements.txt && pip install -r api/requirements.txt`
   * **Start Command**: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
4. Add the following **Environment Variables** in the Render settings panel:
   * `GROQ_API_KEY` = *your_groq_api_key*
   * `TARGET_DB` = `postgresql` (or connection details)
   * `PYTHONUNBUFFERED` = `1`
5. Click **Deploy Web Service**. Render will build and deploy the backend container.
6. Copy the deployed service URL (e.g. `https://mainframe-api.onrender.com`).

---

## 3. Frontend Deployment (Vercel)
**Vercel** provides the fastest, most reliable free hosting for React/Vite applications.

1. Sign up or log in to [Vercel](https://vercel.com/).
2. Click **Add New > Project** and import your GitHub repository.
3. Configure the Vite build parameters:
   * **Framework Preset**: `Vite`
   * **Root Directory**: `./` (Project root)
   * **Build Command**: `npm run build`
   * **Output Directory**: `dist`
4. Deploy the application.
5. Once deployed, open the browser to your live dashboard.
6. Navigate to the **Settings** tab in the dashboard and input your Render backend API URL (e.g., `https://mainframe-api.onrender.com`) under the **FastAPI Base URL** input field, and click **Save Changes**.

---

## Technical Summary of Free Tier Hosts

| Layer | Host | Free Limit details |
| :--- | :--- | :--- |
| **Frontend UI** | Vercel | Unlimited bandwidth, SSL, and custom domains |
| **API Backend Broker** | Render | 500 free build minutes/month, auto-sleeps after 15m inactivity |
| **PostgreSQL Database** | Neon.tech | 0.5 GiB storage, branch supports, serverless scaling |
