"""Import every model so Alembic discovers the complete schema."""

from app.models.auth import DashboardSession, LoginAttempt
from app.models.zerodha_login import ZerodhaLoginState
from app.models.account import ZerodhaAccount, ZerodhaCredential
from app.models.common import Bucket
from app.models.order import InvestmentTransaction, Order
from app.models.portfolio import Holding, HoldingSnapshot, PortfolioSnapshot
from app.models.target import MonthlyTarget

__all__ = [
    "ZerodhaLoginState", "DashboardSession", "LoginAttempt",
    "Bucket", "Holding", "HoldingSnapshot", "InvestmentTransaction",
    "MonthlyTarget", "Order", "PortfolioSnapshot", "ZerodhaAccount", "ZerodhaCredential",
]
