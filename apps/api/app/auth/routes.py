"""Dashboard login is separate from brokerage login."""
from datetime import datetime
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.orm import Session
from app.auth import service
from app.config import settings
from app.models.auth import DashboardSession

router = APIRouter(prefix='/auth')


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024, repr=False)


class SessionView(BaseModel):
    authenticated: bool
    csrf_token: str | None = None
    expires_at: datetime | None = None


def view(row):
    return SessionView(authenticated=bool(row), csrf_token=service.csrf_token(row) if row else None, expires_at=service.aware(row.expires_at) if row else None)


@router.get('/session', response_model=SessionView)
def session(request: Request, response: Response, db: Session = Depends(service.auth_db)):
    response.headers['Cache-Control'] = 'no-store'
    return view(service.find_session(request, db))


@router.post('/login', response_model=SessionView)
def login(body: LoginBody, request: Request, response: Response, db: Session = Depends(service.auth_db)):
    service.origin_check(request)
    row, cookie = service.login(db, body.username, body.password, request.client.host if request.client else 'unknown')
    # Rotate and revoke a previous valid browser session on login.
    old = service.find_session(request, db)
    if old:
        db.execute(delete(DashboardSession).where(DashboardSession.id == old.id))
        db.commit()
    response.set_cookie(service.cookie_name(), cookie, max_age=settings.SESSION_TTL_SECONDS, **service.cookie_options())
    response.headers['Cache-Control'] = 'no-store'
    return view(row)


@router.post('/logout', response_model=SessionView)
def logout(response: Response, row = Depends(service.require_access), db: Session = Depends(service.auth_db)):
    db.execute(delete(DashboardSession).where(DashboardSession.id == row.id))
    db.commit()
    response.delete_cookie(service.cookie_name(), **service.cookie_options())
    response.headers['Cache-Control'] = 'no-store'
    return view(None)
