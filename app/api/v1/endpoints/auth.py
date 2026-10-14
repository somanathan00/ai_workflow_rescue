
from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.dependencies import (
    CurrentUser,
    DBSession,
)
from app.schemas.auth import (
    TokenResponse,
    UserCreate,
    UserResponse,
)
from app.services.auth_service import AuthService


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: UserCreate,
    db: DBSession,
):
    return AuthService.register(db, payload)


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    db: DBSession,
    form: OAuth2PasswordRequestForm = Depends(),
):
    token = AuthService.login(
        db,
        form.username,
        form.password,
    )

    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def get_profile(current_user: CurrentUser):
    return current_user
