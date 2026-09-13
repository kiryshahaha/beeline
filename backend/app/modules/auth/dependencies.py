"""FastAPI dependencies for JWT authentication and role-based access control."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_session
from app.modules.users import service as users_service
from app.modules.users.enums import UserRole
from app.modules.users.schemas import UserRead

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
DatabaseSession = Annotated[Session, Depends(get_session)]


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: DatabaseSession,
) -> UserRead:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Недействительный или просроченный токен авторизации",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise credentials_exception
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as error:
        raise credentials_exception from error

    try:
        return users_service.get_user(session, user_id)
    except users_service.UserNotFoundError as error:
        raise credentials_exception from error


def require_roles(*allowed_roles: UserRole) -> Callable[[UserRead], UserRead]:
    def check_role(
        current_user: Annotated[UserRead, Depends(get_current_user)],
    ) -> UserRead:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав для выполнения операции",
            )
        return current_user

    return check_role
