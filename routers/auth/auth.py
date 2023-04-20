from fastapi import APIRouter
from fastapi import status
from fastapi import HTTPException
from fastapi.responses import PlainTextResponse
from starlette.responses import RedirectResponse
import jwt

from .db import models
from .db.driver import UsersDriver
from .password_handler import PasswordHandler
from .token_handler import TokenHandler
from .email_handler import EmailHandler
from .email_handler import EmailType

from datetime import datetime

router = APIRouter(
    prefix="/auth",
    tags=["auth"]
)

password_handler = PasswordHandler()
token_handler = TokenHandler()
email_handler = EmailHandler()
db = UsersDriver()


def handle_exists_email(email):
    if db.email_exists(email):
        raise HTTPException(detail={"email already exists"}, status_code=status.HTTP_406_NOT_ACCEPTABLE)


def handle_not_exists_email(email):
    if not db.email_exists(email):
        raise HTTPException(detail={"email not found"}, status_code=status.HTTP_404_NOT_FOUND)


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(user: models.UserInSignup):
    handle_exists_email(user.email)

    token = token_handler.encode_token(user.email)
    email_handler.send_email(user.email, token, EmailType.SIGNUP_VERIFICATION)
    hashed_password = password_handler.get_password_hash(user.password)
    user.password = hashed_password
    db.create_user(**user.dict())
    return PlainTextResponse("please verify your email", status_code=status.HTTP_200_OK)


@router.get("/verify")
async def verify_email(token: str):
    try:
        email, expiration_time = token_handler.decode_token(token)
        if datetime.utcnow() > expiration_time:
            raise HTTPException(detail="token has expired", status_code=status.HTTP_401_UNAUTHORIZED)
        if not db.set_is_verified(email):
            raise HTTPException(detail="can't verify email", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except jwt.exceptions.DecodeError:
        raise HTTPException(detail="invalid token", status_code=status.HTTP_401_UNAUTHORIZED)

    return PlainTextResponse("email verified successfully", status_code=status.HTTP_201_CREATED)


@router.post("/login")
async def login(user: models.UserInLogin) -> models.UserOutLogin:
    handle_not_exists_email(user.email)

    logged_user = db.find_user(user.email)
    if not password_handler.verify_password(user.password, logged_user["password"]):
        raise HTTPException(detail="wrong password", status_code=status.HTTP_401_UNAUTHORIZED)

    encoded_token = token_handler.encode_token(user.email)
    if not logged_user["is_verified"]:
        email_handler.send_email(logged_user["email"], encoded_token, EmailType.SIGNUP_VERIFICATION)
        raise HTTPException(detail="email is not verified", status_code=status.HTTP_401_UNAUTHORIZED)

    return models.UserOutLogin(**logged_user, token=encoded_token)


@router.post("/forgot-password")
async def forgot_password(email):
    handle_not_exists_email(email)

    encoded_token = token_handler.encode_token(email)
    email_handler.send_email(email, encoded_token, EmailType.FORGET_PASSWORD)
    return PlainTextResponse("sent a verification email", status_code=status.HTTP_200_OK)


@router.get("/reset-password")
async def reset_password(token: str):
    try:
        email, expiration_time = token_handler.decode_token(token)
        if datetime.utcnow() > expiration_time:
            raise HTTPException(detail="token has expired", status_code=status.HTTP_401_UNAUTHORIZED)

        handle_not_exists_email(email)

    except jwt.exceptions.DecodeError:
        raise HTTPException(detail="invalid token", status_code=status.HTTP_401_UNAUTHORIZED)

    return RedirectResponse(url=f"/auth/change-password?token={token}")


@router.put("/change-password")
async def change_password(token: str, request: models.UserInForgotPassword):
    try:
        email, expiration_time = token_handler.decode_token(token)
        new_password = password_handler.get_password_hash(request.password)
        db.update_password(email, new_password)
        return PlainTextResponse("password updated successfully", status_code=status.HTTP_200_OK)
    except jwt.exceptions.DecodeError:
        raise HTTPException(detail="change password failed", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@router.post("/check-email")
async def check_email(email):
    handle_not_exists_email(email)

    return PlainTextResponse("email is available", status_code=status.HTTP_200_OK)
