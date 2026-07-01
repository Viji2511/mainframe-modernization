import os
import sys
import uuid
import json
import shutil
import zipfile
import asyncio
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="MainframeAI API", version="1.0.0")

# Enable CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Support all origins for easy development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Constants
UPLOAD_BASE_DIR = os.path.abspath("uploads")
OUTPUT_BASE_DIR = os.path.abspath("outputs")
JOBS_STATE_FILE = os.path.abspath("jobs_state.json")

# Ensure base directories exist
os.makedirs(UPLOAD_BASE_DIR, exist_ok=True)
os.makedirs(OUTPUT_BASE_DIR, exist_ok=True)

# Helper to read/write jobs state file
def load_jobs_state() -> list:
    if not os.path.exists(JOBS_STATE_FILE):
        return []
    try:
        with open(JOBS_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_jobs_state(jobs: list):
    with open(JOBS_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2)

def update_job_status(job_id: str, status: str, error: Optional[str] = None):
    jobs = load_jobs_state()
    for job in jobs:
        if job["job_id"] == job_id:
            job["status"] = status
            if status in ("done", "error"):
                job["completed_at"] = datetime.utcnow().isoformat() + "Z"
            if error:
                job["error"] = error
            break
    save_jobs_state(jobs)

# Request Models
class RunPipelineRequest(BaseModel):
    job_id: str
    db: str = "postgresql"
    dsn: Optional[str] = None
    list_vsam: bool = False

async def run_pipeline_subprocess(job_id: str, db: str, dsn: Optional[str], list_vsam: bool):
    """
    Spawns main.py in a non-blocking subprocess.
    """
    update_job_status(job_id, "running")
    
    input_dir = os.path.join(UPLOAD_BASE_DIR, job_id)
    output_dir = os.path.join(OUTPUT_BASE_DIR, job_id)
    os.makedirs(output_dir, exist_ok=True)

    # Use the current python executable (sys.executable) to inherit packages/venv
    cmd = [
        sys.executable,
        os.path.abspath("main.py"),
        "--input", input_dir,
        "--db", db,
        "--output", output_dir
    ]
    
    if dsn:
        cmd.extend(["--dsn", dsn])
    if list_vsam:
        cmd.append("--list-vsam")

    try:
        # Spawn async subprocess
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            update_job_status(job_id, "done")
        else:
            error_msg = stderr.decode(errors="replace") or stdout.decode(errors="replace") or "Process failed"
            update_job_status(job_id, "error", error=error_msg[:1000])
    except Exception as e:
        update_job_status(job_id, "error", error=str(e))

# Endpoints
@app.post("/api/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    job_id = str(uuid.uuid4())
    job_dir = os.path.join(UPLOAD_BASE_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    saved_files = []
    
    try:
        for f in files:
            file_path = os.path.join(job_dir, f.filename)
            # Ensure subdirectory paths are created if zip contains subfolders
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(f.file, buffer)
            
            # If it's a zip file, unpack it
            if f.filename.endswith(".zip"):
                with zipfile.ZipFile(file_path, "r") as zip_ref:
                    zip_ref.extractall(job_dir)
                os.remove(file_path)  # Delete original zip to keep folder clean

            saved_files.append({
                "name": f.filename,
                "size": os.path.getsize(file_path) if os.path.exists(file_path) else 0
            })
            
        # Recount actual files in directory
        total_files = 0
        for _, _, filenames in os.walk(job_dir):
            total_files += len(filenames)
            
        return {
            "job_id": job_id,
            "file_count": total_files,
            "files": saved_files
        }
    except Exception as e:
        # Clean up directory on error
        if os.path.exists(job_dir):
            shutil.rmtree(job_dir)
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")

@app.post("/api/run")
async def run_pipeline(payload: RunPipelineRequest, background_tasks: BackgroundTasks):
    job_dir = os.path.join(UPLOAD_BASE_DIR, payload.job_id)
    if not os.path.exists(job_dir):
        raise HTTPException(status_code=404, detail="Uploaded files not found for this Job ID.")

    # Check if job already recorded
    jobs = load_jobs_state()
    job_exists = any(j["job_id"] == payload.job_id for j in jobs)
    
    # Get files count
    files_count = 0
    for _, _, filenames in os.walk(job_dir):
        files_count += len(filenames)

    if not job_exists:
        job_info = {
            "job_id": payload.job_id,
            "status": "queued",
            "db": payload.db,
            "dsn": payload.dsn or "ALL",
            "files_count": files_count,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "completed_at": None,
            "error": None
        }
        jobs.insert(0, job_info)
        save_jobs_state(jobs)

    # Spawn async subprocess run in background
    background_tasks.add_task(
        run_pipeline_subprocess,
        payload.job_id,
        payload.db,
        payload.dsn,
        payload.list_vsam
    )

    return {"job_id": payload.job_id, "status": "queued"}

@app.get("/api/status/{job_id}")
async def get_job_status(job_id: str):
    jobs = load_jobs_state()
    for job in jobs:
        if job["job_id"] == job_id:
            return job
    raise HTTPException(status_code=404, detail="Job record not found.")

@app.get("/api/result/{job_id}")
async def get_job_result(job_id: str):
    # Verify status first
    jobs = load_jobs_state()
    target_job = None
    for job in jobs:
        if job["job_id"] == job_id:
            target_job = job
            break
            
    if not target_job:
        raise HTTPException(status_code=404, detail="Job record not found.")

    if target_job["status"] != "done":
        return {"status": target_job["status"]}

    output_dir = os.path.join(OUTPUT_BASE_DIR, job_id)
    if not os.path.exists(output_dir):
        return []

    # Gather all JSON results
    results = []
    for f in os.listdir(output_dir):
        if f.endswith("_result.json"):
            file_path = os.path.join(output_dir, f)
            try:
                with open(file_path, "r", encoding="utf-8") as file:
                    results.append(json.load(file))
            except Exception as e:
                print(f"Error loading result {f}: {e}")

    # Return list (or single object if only one)
    return results

@app.get("/api/jobs")
async def get_all_jobs():
    return load_jobs_state()

@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    # Remove files
    upload_dir = os.path.join(UPLOAD_BASE_DIR, job_id)
    output_dir = os.path.join(OUTPUT_BASE_DIR, job_id)
    
    if os.path.exists(upload_dir):
        shutil.rmtree(upload_dir)
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)

    # Remove status
    jobs = load_jobs_state()
    updated_jobs = [j for j in jobs if j["job_id"] != job_id]
    save_jobs_state(updated_jobs)

    return {"deleted": True}

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}
