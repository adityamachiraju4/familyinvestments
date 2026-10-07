"""Authenticated read-only planning. No ingestion/trading routes."""
from decimal import Decimal
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.integrations.zerodha.routes import integration_db
from app.investments import service
from app.investments.calculations import validate_rate

router = APIRouter(prefix='/investments')

@router.get('/sips')
def sips(db: Session = Depends(integration_db)):
    return service.serialize(service.sip_views(db))

@router.get('/mutual-funds/summary')
def summary(db: Session = Depends(integration_db)):
    return service.serialize(service.summary(db))

@router.get('/sips/projections')
def projections(annual_return: Decimal = Query(default=Decimal(10), ge=0, le=30), db: Session = Depends(integration_db)):
    try:
        validate_rate(annual_return)
        return service.serialize(service.projections(db,annual_return))
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
