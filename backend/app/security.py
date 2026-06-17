"""Password hashing + JWT, and FastAPI auth dependencies (incl. paywall gate)."""
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"

# auto_error=False so the public feed works without a token.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def hash_password(p: str) -> str:
    return pwd_context.hash(p)


def verify_password(p: str, hashed: str) -> bool:
    return pwd_context.verify(p, hashed)


def create_access_token(sub: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({"sub": sub, "exp": expire}, settings.secret_key, algorithm=ALGORITHM)


def _user_from_token(token: str | None, db: Session) -> User | None:
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        email = payload.get("sub")
    except JWTError:
        return None
    if not email:
        return None
    return db.query(User).filter(User.email == email).first()


def get_current_user_optional(
    token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User | None:
    """For endpoints open to all; returns None for anonymous visitors."""
    return _user_from_token(token, db)


def get_current_user(
    token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    user = _user_from_token(token, db)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user


def require_paid(user: User = Depends(get_current_user)) -> User:
    """Paywall gate — the AI feasibility engine lives behind this."""
    if user.tier != "paid" and not user.is_admin:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            "This is a premium feature. Upgrade to run acquisition-fit analysis.",
        )
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user
