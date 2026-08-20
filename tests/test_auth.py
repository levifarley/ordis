import pytest
from datetime import timedelta
from fastapi import HTTPException
from jose import jwt

from backend.config import settings
from backend.auth import (
    create_access_token,
    authenticate_user,
    get_current_user,
    User,
    get_password_hash,
    verify_password
)

def test_authenticate_user_success():
    assert authenticate_user("operator", "cephalon") is True

def test_authenticate_user_failure():
    assert authenticate_user("operator", "wrongpassword") is False
    assert authenticate_user("invaliduser", "cephalon") is False

def test_create_access_token():
    token = create_access_token(data={"sub": "operator"})
    assert isinstance(token, str)
    
    payload = jwt.decode(token, settings.OAUTH_SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload.get("sub") == "operator"
    assert "exp" in payload

@pytest.mark.asyncio
async def test_get_current_user_valid_token():
    token = create_access_token(data={"sub": "operator"})
    user = await get_current_user(token=token)
    assert isinstance(user, User)
    assert user.username == "operator"

@pytest.mark.asyncio
async def test_get_current_user_invalid_token():
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token="invalid.jwt.token")
    assert exc_info.value.status_code == 401
