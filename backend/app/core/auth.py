import secrets
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.core.config import settings

bearer = HTTPBearer(auto_error=False)

def authorize(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    expected = settings.app_access_token.get_secret_value()
    if len(expected) < 32:
        raise HTTPException(503, 'Код доступа не настроен')
    if not credentials or not secrets.compare_digest(credentials.credentials.encode(), expected.encode()):
        raise HTTPException(401, 'Неверный код доступа', headers={'WWW-Authenticate': 'Bearer'})
