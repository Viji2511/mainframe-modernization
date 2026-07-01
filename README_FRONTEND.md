# MainframeAI - Setup Guide

This guide details how to install and execute the modernizer web application client (Vite + React) alongside the API service backend (FastAPI).

---

## 1. Running the Backend Server (FastAPI)

1. Activate your Python virtual environment and navigate to the project directory:
   ```bash
   cd mainframe-modernizer
   ```

2. Install the API-specific dependencies:
   ```bash
   pip install -r api/requirements.txt
   ```

3. Start the FastAPI development server with `uvicorn`:
   ```bash
   uvicorn api.main:app --reload --port 8000
   ```
   * The API endpoints will be accessible at: **`http://localhost:8000`**
   * The Swagger interactive docs will be live at: **`http://localhost:8000/docs`**

---

## 2. Running the Frontend Dashboard (React + Vite)

1. Open a new terminal session, navigate to the project directory, and install npm packages:
   ```bash
   cd mainframe-modernizer
   npm install
   ```

2. Launch the Vite development server:
   ```bash
   npm run dev
   ```
   * The application UI will be accessible in your web browser at: **`http://localhost:5173`**

---

## 3. Configuration & Ports Summary

| Component | Tech Stack | Port | Address |
| :--- | :--- | :--- | :--- |
| **Frontend Web App** | React / Vite | `5173` | [http://localhost:5173](http://localhost:5173) |
| **API Backend** | FastAPI / Uvicorn | `8000` | [http://localhost:8000](http://localhost:8000) |

* **Environment Overrides**: If you want to change the target port of the backend server, remember to update the **FastAPI Base URL** in the **Settings** view of the Web Dashboard.
