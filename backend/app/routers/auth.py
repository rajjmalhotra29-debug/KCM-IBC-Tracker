"""Signup / login / me."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import Token, UserCreate, UserOut
from ..security import (
    create_access_token, get_current_user, hash_password, verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=Token)
def signup(payload: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email already registered")
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        tier="free",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.email)
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # OAuth2 form uses 'username' for the email field.
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    token = create_access_token(user.email)
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
