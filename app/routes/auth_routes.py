from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime, timezone, timedelta
import uuid
import bcrypt
import jwt

from app.core.database import get_db
from app.core.constants import RESTAURANT_ID

router  = APIRouter(prefix="/auth", tags=["Auth"])
security = HTTPBearer()

# ── Config ────────────────────────────────────────────────────────────────────
JWT_SECRET    = "cravecall_jwt_secret_2026"  # move to env in production
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24

COLLECTION = "users"

# ── Schemas ───────────────────────────────────────────────────────────────────

class SignUpRequest(BaseModel):
    firstName:   str   = Field(..., min_length=1)
    lastName:    str   = Field(..., min_length=1)
    email:       str   = Field(..., min_length=5)
    phone:       Optional[str] = None
    password:    str   = Field(..., min_length=8)
    role:        str   = "customer"  # customer / sales_rep / operations_manager / admin

class SignInRequest(BaseModel):
    email:    str
    password: str

class UserResponse(BaseModel):
    userId:    str
    firstName: str
    lastName:  str
    email:     str
    phone:     Optional[str]
    role:      str

# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def _create_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "userId": user_id,
        "email":  email,
        "role":   role,
        "exp":    datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    return _decode_token(credentials.credentials)

# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/signup", status_code=201)
async def signup(data: SignUpRequest):
    db  = get_db()
    now = datetime.now(timezone.utc)

    # check duplicate email
    existing = await db[COLLECTION].find_one({"email": data.email.lower()})
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user_id = f"USR-{uuid.uuid4().hex[:12].upper()}"

    doc = {
        "userId":       user_id,
        "restaurantId": RESTAURANT_ID,
        "firstName":    data.firstName.strip(),
        "lastName":     data.lastName.strip(),
        "email":        data.email.lower().strip(),
        "phone":        data.phone,
        "passwordHash": _hash_password(data.password),
        "role":         data.role,
        "provider":     "email",
        "isActive":     True,
        "createdAt":    now,
        "lastLoginAt":  None,
    }

    await db[COLLECTION].insert_one(doc)
    token = _create_token(user_id, data.email.lower(), data.role)

    return {
        "success": True,
        "token":   token,
        "user": {
            "userId":    user_id,
            "firstName": data.firstName,
            "lastName":  data.lastName,
            "email":     data.email.lower(),
            "phone":     data.phone,
            "role":      data.role,
        }
    }


@router.post("/signin")
async def signin(data: SignInRequest):
    db  = get_db()
    now = datetime.now(timezone.utc)

    user = await db[COLLECTION].find_one({"email": data.email.lower().strip()})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not _verify_password(data.password, user["passwordHash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.get("isActive"):
        raise HTTPException(status_code=403, detail="Account is inactive")

    # update lastLoginAt
    await db[COLLECTION].update_one(
        {"userId": user["userId"]},
        {"$set": {"lastLoginAt": now}}
    )

    token = _create_token(user["userId"], user["email"], user["role"])

    return {
        "success": True,
        "token":   token,
        "user": {
            "userId":    user["userId"],
            "firstName": user["firstName"],
            "lastName":  user["lastName"],
            "email":     user["email"],
            "phone":     user.get("phone"),
            "role":      user["role"],
        }
    }


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    db   = get_db()
    user = await db[COLLECTION].find_one(
        {"userId": current_user["userId"]},
        {"passwordHash": 0, "_id": 0}
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"success": True, "user": user}


@router.post("/signout")
async def signout():
    # JWT is stateless — client clears token
    return {"success": True, "message": "Signed out successfully"}


async def create_indexes():
    db = get_db()
    await db[COLLECTION].create_index([("email", 1)], unique=True, name="idx_email_unique")
    await db[COLLECTION].create_index([("userId", 1)], unique=True, name="idx_userId_unique")
    print(f"Indexes created for {COLLECTION}")
