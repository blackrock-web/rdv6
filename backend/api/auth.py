"""
ROADAI Auth — JWT login, token verification, user management.
Migration: JSON fallback replaced with MongoDB Atlas persistence.
"""
import os
import time
import random
import logging
from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel
from typing import Optional
from backend.db.database import get_db, doc_to_dict
from backend.core.twilio_sms_service import send_sms_alert

try:
    import jwt
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False

router = APIRouter()

SECRET = os.environ.get("ROADAI_SECRET", "roadai-super-secret-key-change-me")

# Built-in users (Seed data if DB is empty)
_SEED_USERS = [
    {"username": "admin",   "password": "admin123",   "role": "admin",   "name": "System Admin",   "email": "admin@roadai.local"},
    {"username": "analyst", "password": "analyst123", "role": "analyst", "name": "Road Analyst",    "email": "analyst@roadai.local"},
    {"username": "user",    "password": "user123",    "role": "user",    "name": "Field Viewer",   "email": "user@roadai.local"},
]

async def _ensure_seed_users():
    db = await get_db()
    count = await db.users.count_documents({})
    if count == 0:
        await db.users.insert_many(_SEED_USERS)

# ── Token helpers ──────────────────────────────────────────────

def create_token(username: str, role: str) -> str:
    if not JWT_AVAILABLE:
        return f"mock-token-{username}-{role}"
    payload = {
        "sub": username,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + 86400 * 7,  # 7 days
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")

def _decode_token(token: str) -> dict:
    if not JWT_AVAILABLE:
        if token.startswith("mock-token-"):
            parts = token.split("-")
            if len(parts) >= 4:
                return {"sub": parts[2], "role": parts[3], "username": parts[2]}
        raise HTTPException(status_code=401, detail="Invalid token")
    try:
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        payload.setdefault("username", payload.get("sub", ""))
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

def _token_from_header(authorization: Optional[str]) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    return authorization.split(" ", 1)[1]

# ── FastAPI dependency functions ────────────────────────────────

def verify_token(authorization: Optional[str] = Header(None)) -> dict:
    token = _token_from_header(authorization)
    return _decode_token(token)

def require_admin(authorization: Optional[str] = Header(None)) -> dict:
    payload = verify_token(authorization)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return payload

# ── Routes ─────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    name: str = ""
    email: str = ""
    role: str = "user"

@router.post("/login")
async def login(req: LoginRequest):
    await _ensure_seed_users()
    db = await get_db()
    user = await db.users.find_one({"username": req.username})
    
    if not user or user.get("password") != req.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_token(req.username, user["role"])
    return {
        "token": token,
        "username": req.username,
        "role": user["role"],
        "name": user.get("name", req.username),
    }

@router.get("/me")
async def me(payload: dict = Depends(verify_token)):
    username = payload.get("sub") or payload.get("username", "")
    db = await get_db()
    user = await db.users.find_one({"username": username})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    return {
        "username": username,
        "role": payload.get("role", "user"),
        "name": user.get("name", username),
        "email": user.get("email", ""),
    }

@router.get("/users")
async def list_users(_: dict = Depends(require_admin)):
    db = await get_db()
    cursor = db.users.find({})
    users = await cursor.to_list(length=100)
    return [{"username": u["username"], "role": u.get("role"), "name": u.get("name"), "email": u.get("email")} for u in users]

@router.post("/register")
async def register(req: RegisterRequest, _: dict = Depends(require_admin)):
    db = await get_db()
    if await db.users.find_one({"username": req.username}):
        raise HTTPException(status_code=400, detail=f"User '{req.username}' already exists")
    
    await db.users.insert_one({
        "username": req.username,
        "password": req.password,
        "role": req.role,
        "name": req.name or req.username,
        "email": req.email,
    })
    return {"message": f"User '{req.username}' created"}

# ── OTP Logic (SMS) ──────────────────────────────────────

_otp_store = {}

class OTPRequest(BaseModel):
    phone: str

class OTPVerify(BaseModel):
    phone: str
    code: str

@router.post("/request-otp")
async def request_otp(req: OTPRequest):
    code = f"{random.randint(100000, 999999)}"
    _otp_store[req.phone] = code
    
    try:
        msg = f"Your ROADAI code is: {code}"
        if send_sms_alert(msg, override_phone=req.phone):
            return {"success": True, "message": "OTP sent via SMS"}
    except Exception as e:
        logging.warning(f"SMS failed: {e}")
        
    return {"success": True, "message": "OTP generated (Mock)", "dev_otp": code}

@router.post("/verify-otp")
async def verify_otp(req: OTPVerify):
    expected = _otp_store.get(req.phone)
    if not expected or expected != req.code:
        raise HTTPException(status_code=401, detail="Invalid OTP")
        
    del _otp_store[req.phone]
    return {
        "access_token": create_token("admin", "admin"),
        "token_type": "bearer",
        "username": req.phone,
        "role": "admin"
    }
