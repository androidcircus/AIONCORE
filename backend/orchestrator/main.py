"""
AION Core - Orchestrator
FastAPI service that receives commands, manages auth, and dispatches
Celery tasks to the worker pool.
"""
import os
import json
import uuid
import time
import redis
import bcrypt
import jwt
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
JWT_SECRET = os.getenv("JWT_SECRET_KEY", "change-me")
JWT_ALG = "HS256"
JWT_EXP_HOURS = int(os.getenv("JWT_EXP_HOURS", "24"))

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASS_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------
r = redis.Redis.from_url(REDIS_URL, decode_responses=True)

# ---------------------------------------------------------------------------
# FastAPI
# ---------------------------------------------------------------------------
app = FastAPI(title="AION Core Orchestrator", version="1.0.0")
security = HTTPBearer()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str
    password: str


class CommandRequest(BaseModel):
    command: str
    params: dict = {}


class CloneSpec(BaseModel):
    name: str
    description: str = ""
    prompt: str = ""
    link: str = "#"
    vcpus: int = 2
    memory_mb: int = 2048
    disk_gb: int = 10


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def create_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXP_HOURS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALG])
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok", "service": "orchestrator"}


@app.post("/api/login")
def login(req: LoginRequest):
    if req.username != ADMIN_USERNAME:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not ADMIN_PASS_HASH:
        raise HTTPException(status_code=500, detail="Admin password not configured")
    if not bcrypt.checkpw(req.password.encode(), ADMIN_PASS_HASH.encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(req.username)
    return {"access_token": token, "token_type": "bearer"}


@app.get("/api/clones")
def list_clones(user: str = Depends(verify_token)):
    """Return all clone statuses from Redis."""
    keys = r.keys("clone:*")
    clones = []
    for key in sorted(keys):
        data = r.hgetall(key)
        data["clone_id"] = key.split(":", 1)[1]
        clones.append(data)
    return clones


@app.get("/api/clones/{clone_id}")
def get_clone(clone_id: str, user: str = Depends(verify_token)):
    data = r.hgetall(f"clone:{clone_id}")
    if not data:
        raise HTTPException(status_code=404, detail="Clone not found")
    data["clone_id"] = clone_id
    return data


@app.post("/api/command")
def handle_command(req: CommandRequest, user: str = Depends(verify_token)):
    """Dispatch a command to the worker pool."""
    if req.command == "deploy_clone":
        clone_id = f"clone-{uuid.uuid4().hex[:8]}"
        spec = req.params
        # Store spec in Redis
        spec_flat = {}
        for k, v in spec.items():
            spec_flat[k] = str(v) if not isinstance(v, str) else v
        r.hset(f"clone:{clone_id}", mapping=spec_flat)

        # Dispatch the full chain via Celery
        from celery import Celery
        worker = Celery("aion_tasks", broker=REDIS_URL)
        worker.send_task(
            "tasks.full_clone_deployment",
            args=[clone_id, spec],
        )
        return {"clone_id": clone_id, "status": "dispatched"}

    elif req.command == "upgrade_clone":
        clone_id = req.params.get("clone_id")
        vcpus = req.params.get("vcpus")
        memory_mb = req.params.get("memory_mb")
        disk_gb = req.params.get("disk_gb")
        from celery import Celery
        worker = Celery("aion_tasks", broker=REDIS_URL)
        worker.send_task(
            "tasks.upgrade_vm",
            args=[clone_id],
            kwargs={"vcpus": vcpus, "memory_mb": memory_mb, "disk_gb": disk_gb},
        )
        return {"clone_id": clone_id, "status": "upgrade_dispatched"}

    elif req.command == "destroy_clone":
        clone_id = req.params.get("clone_id")
        from celery import Celery
        worker = Celery("aion_tasks", broker=REDIS_URL)
        worker.send_task("tasks.destroy_vm", args=[clone_id])
        return {"clone_id": clone_id, "status": "destroy_dispatched"}

    else:
        raise HTTPException(status_code=400, detail=f"Unknown command: {req.command}")


@app.get("/api/stats")
def get_stats(user: str = Depends(verify_token)):
    """Aggregate statistics about deployed clones."""
    keys = r.keys("clone:*")
    statuses = {}
    for key in keys:
        status_val = r.hget(key, "status") or "unknown"
        statuses[status_val] = statuses.get(status_val, 0) + 1
    return {
        "total_clones": len(keys),
        "by_status": statuses,
        "timestamp": datetime.utcnow().isoformat(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
