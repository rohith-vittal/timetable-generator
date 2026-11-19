from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
import uuid

from app.schemas import LoginRequest, LoginResponse, UserProfile, RegisterRequest
from app.models import User
from app.auth_deps import get_current_user
from app.storage import db

router = APIRouter(prefix="/api/auth", tags=["Authentication & Access Control"])

@router.post(
    "/register",
    response_model=LoginResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register New Faculty or Admin Account",
    description="Registers a new user in the institutional database and returns their authenticated profile."
)
def register(payload: RegisterRequest):
    try:
        new_user = db.register_user(
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            role=payload.role,
            department_id=payload.department_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    token = f"tok-{new_user.role.lower()}-{uuid.uuid4().hex[:12]}"
    db.active_sessions[token] = new_user
    user_dept_id = payload.department_id or 1
    for d in db.departments.values():
        if d.code == new_user.department_code or d.name == new_user.department:
            user_dept_id = d.id
            break

    return LoginResponse(
        token=token,
        access_token=token,
        user=UserProfile(
            id=new_user.id,
            email=new_user.email,
            full_name=new_user.full_name,
            name=new_user.full_name,
            role=new_user.role,
            department=new_user.department,
            department_code=new_user.department_code,
            department_id=user_dept_id,
        )
    )

@router.post(
    "/login",
    response_model=LoginResponse,
    summary="User Login for Faculty & Admin",
    description="Authenticates faculty or admin with email and password, returning their role and profile."
)
def login(payload: LoginRequest):
    # Find user by email
    clean_email = payload.email.strip().lower()
    matched_user = None
    for u in db.users.values():
        if u.email.strip().lower() == clean_email:
            matched_user = u
            break

    if not matched_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials. No user registered with this email address."
        )

    # Check password with PBKDF2 verification (DEF-005)
    from app.storage import verify_password
    if not verify_password(payload.password, matched_user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password. Please check your credentials."
        )

    token = f"tok-{matched_user.role.lower()}-{uuid.uuid4().hex[:12]}"
    db.active_sessions[token] = matched_user

    user_dept_id = None
    for d in db.departments.values():
        if d.code == matched_user.department_code or d.name == matched_user.department:
            user_dept_id = d.id
            break

    return LoginResponse(
        token=token,
        access_token=token,
        user=UserProfile(
            id=matched_user.id,
            email=matched_user.email,
            full_name=matched_user.full_name,
            name=matched_user.full_name,
            role=matched_user.role,
            department=matched_user.department,
            department_code=matched_user.department_code,
            department_id=user_dept_id,
        )
    )

@router.get(
    "/me",
    response_model=UserProfile,
    summary="Get Current Authenticated User Profile"
)
def get_me(user: User = Depends(get_current_user)):
    user_dept_id = None
    for d in db.departments.values():
        if d.code == user.department_code or d.name == user.department:
            user_dept_id = d.id
            break
    return UserProfile(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        name=user.full_name,
        role=user.role,
        department=user.department,
        department_code=user.department_code,
        department_id=user_dept_id,
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

