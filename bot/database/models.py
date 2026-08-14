import datetime
from typing import List, Optional
from sqlalchemy import BigInteger, String, Integer, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    
    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    phone_number: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    language: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    
    subscriptions: Mapped[List["Subscription"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    payments: Mapped[List["Payment"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

class Subscription(Base):
    __tablename__ = "subscriptions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String)  # "active", "expired"
    tariff_months: Mapped[int] = mapped_column(Integer)  # 1, 3, 6
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    notified_3d: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    notified_1d: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    
    user: Mapped["User"] = relationship(back_populates="subscriptions")

class Payment(Base):
    __tablename__ = "payments"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"))
    amount: Mapped[int] = mapped_column(Integer)
    tariff_months: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)  # "completed", "pending", "failed"
    payment_method: Mapped[str] = mapped_column(String, default="mock_gateway", server_default="mock_gateway")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    
    user: Mapped["User"] = relationship(back_populates="payments")
