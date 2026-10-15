from __future__ import annotations
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.entities import User

try:
    import bcrypt
except ModuleNotFoundError:  # dev setups without bcrypt fall back to plain text
    bcrypt = None

auth_scheme = HTTPBearer(auto_error=False)

# bcrypt only reads the first 72 bytes of a password.
_BCRYPT_MAX = 72


def verify_password(plain_password: str, hashed_password: str) -> bool:
    # bcrypt hashes are checked with bcrypt; anything else is a plain-text bootstrap/dev password.
    try:
        if hashed_password.startswith("$2") and bcrypt is not None:
            return bcrypt.checkpw(plain_password.encode("utf-8")[:_BCRYPT_MAX], hashed_password.encode("utf-8"))
        return plain_password == hashed_password
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    # Uses the bcrypt package directly. passlib 1.7 breaks with bcrypt >= 4.1 (its self-test
    # raises "password cannot be longer than 72 bytes"), which made every new login fail.
    if bcrypt is None:
        return password
    return bcrypt.hashpw(password.encode("utf-8")[:_BCRYPT_MAX], bcrypt.gensalt()).decode("utf-8")


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode = {"sub": subject, "exp": expire}
    return jwt.encode(to_encode, settings.secret_key, algorithm="HS256")


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(auth_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    try:
        user = db.query(User).filter(User.LoginName == username).first()
    except SQLAlchemyError as exc:
        if str(username).lower() == settings.admin_username.lower():
            # Allow admin bootstrap token even if DB is temporarily unavailable.
            fallback = User()
            fallback.UserId = 0
            fallback.LoginName = settings.admin_username
            fallback.RoleName = "Admin"
            return fallback
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unavailable: {exc.__class__.__name__}",
        ) from exc

    if not user:
        if str(username).lower() == settings.admin_username.lower():
            fallback = User()
            fallback.UserId = 0
            fallback.LoginName = settings.admin_username
            fallback.RoleName = "Admin"
            return fallback
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # A token issued earlier must stop working once the login is blocked or the employee has left.
    from app.services.employee_status import login_block_reason

    reason = login_block_reason(db, user)
    if reason:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)
    return user
