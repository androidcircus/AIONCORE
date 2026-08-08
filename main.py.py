from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import jwt, os, bcrypt, json
from datetime import datetime, timedelta

app = FastAPI(title="AION Core Orchestrator")
security = HTTPBearer()

JWT_SECRET = os.getenv("JWT_SECRET_KEY", "change_me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY = 60 * 60 * 24

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")

class LoginRequest(BaseModel): username: str; password: str
class TokenResponse(BaseModel): access_token: str; token_type: str = "bearer"
class CommandRequest(BaseModel): command: str; params: dict

def verify_password(p, h): return bcrypt.checkpw(p.encode(), h.encode())
def create_jwt(username: str) -> str:
    payload = {"sub": username, "exp": datetime.utcnow() + timedelta(seconds=JWT_EXPIRY)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
def decode_jwt(token: str) -> dict:
    try: return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError: raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/api/login", response_model=TokenResponse)
async def login(data: LoginRequest):
    if data.username != ADMIN_USERNAME or not verify_password(data.password, ADMIN_PASSWORD_HASH):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"access_token": create_jwt(data.username)}

@app.post("/api/command")
async def command(cmd: CommandRequest, cred: HTTPAuthorizationCredentials = Depends(security)):
    decode_jwt(cred.credentials)
    # Dispatch to Celery (implement dispatch logic)
    return {"status": "ok", "result": f"'{cmd.command}' queued"}

@app.get("/metrics")
async def metrics(): return {"status": "ok"}