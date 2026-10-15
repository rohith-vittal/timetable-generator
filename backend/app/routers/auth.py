from fastapi import APIRouter, HTTPException, status
from typing import List
import uuid

from app.schemas import LoginRequest, LoginResponse, UserProfile
from app.storage import db

router = APIRouter(prefix="/api/auth", tags=["Authentication & Access Control"])

@router.post(
    "/login",
    response_model=LoginResponse,
    summary="User Login for Faculty & Admin",
    description="Authenticates faculty or admin with email and password, returning their role and profile."
)
def login(payload: LoginRequest):
    # Find user by email
    matched_user = None
    for u in db.users.values():
        if u.email.lower() == payload.email.lower():
            matched_user = u
            break

    if not matched_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials. No user registered with this email address."
        )

    # Check password
    if matched_user.password != payload.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password. Please check your credentials."
        )

    token = f"tok-{matched_user.role.lower()}-{uuid.uuid4().hex[:12]}"

    return LoginResponse(
        token=token,
        user=UserProfile(
            id=matched_user.id,
            email=matched_user.email,
            full_name=matched_user.full_name,
            role=matched_user.role,
            department=matched_user.department,
            department_code=matched_user.department_code,
        )
    )

@router.get(
    "/demo-accounts",
    summary="List Demo Accounts for Quick Login",
    description="Surfaces pre-configured Admin and Faculty login credentials for instant testing."
)
def list_demo_accounts():
    accounts = []
    for u in db.users.values():
        accounts.append({
            "id": u.id,
            "email": u.email,
            "password": u.password,
            "name": u.full_name,
            "role": u.role,
            "department": u.department,
            "department_code": u.department_code,
        })
    return accounts
