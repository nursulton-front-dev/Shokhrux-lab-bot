import datetime
from typing import List, Optional
from sqlalchemy import BigInteger, String, Integer, DateTime, Boolean, ForeignKey, Float
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
    balance: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    referred_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    photo_file_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    subscriptions: Mapped[List["Subscription"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    payments: Mapped[List["Payment"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    tickets: Mapped[List["Ticket"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    cashback_transactions: Mapped[List["CashbackTransaction"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    calorie_logs: Mapped[List["CalorieLog"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    weight_logs: Mapped[List["WeightLog"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    fitness_profile: Mapped[Optional["UserFitnessProfile"]] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
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
    invite_link: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    vip_invite_link: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    user: Mapped["User"] = relationship(back_populates="subscriptions")

class Payment(Base):
    __tablename__ = "payments"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"))
    amount: Mapped[int] = mapped_column(Integer)
    tariff_months: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)  # "completed", "pending", "failed"
    payment_method: Mapped[str] = mapped_column(String, default="mock_gateway", server_default="mock_gateway")
    cashback_applied: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    request_key: Mapped[Optional[str]] = mapped_column(String(160), unique=True, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    
    user: Mapped["User"] = relationship(back_populates="payments")


class PaymentDelivery(Base):
    """Durable work committed atomically with the financial transaction."""

    __tablename__ = "payment_deliveries"

    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id", ondelete="CASCADE"), primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id", ondelete="CASCADE"), unique=True)
    referrer_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    referral_notified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

class Ticket(Base):
    __tablename__ = "tickets"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String, default="open")  # "open", "in_progress", "closed"
    admin_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    text: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    
    user: Mapped["User"] = relationship(back_populates="tickets")

class CashbackTransaction(Base):
    __tablename__ = "cashback_transactions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"))
    amount: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String)  # "accrual" | "spend"
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    
    user: Mapped["User"] = relationship(back_populates="cashback_transactions")

class CalorieLog(Base):
    __tablename__ = "calorie_logs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"))
    dish: Mapped[str] = mapped_column(String)
    weight_g: Mapped[int] = mapped_column(Integer, default=0)
    calories: Mapped[int] = mapped_column(Integer, default=0)
    protein: Mapped[float] = mapped_column(Float, default=0.0)
    fat: Mapped[float] = mapped_column(Float, default=0.0)
    carbs: Mapped[float] = mapped_column(Float, default=0.0)
    tip: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    
    user: Mapped["User"] = relationship(back_populates="calorie_logs")

class WeightLog(Base):
    __tablename__ = "weight_logs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"))
    weight: Mapped[float] = mapped_column(Float)
    recorded_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    
    user: Mapped["User"] = relationship(back_populates="weight_logs")

class UserFitnessProfile(Base):
    __tablename__ = "user_fitness_profiles"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), unique=True)
    height_cm: Mapped[float] = mapped_column(Float)
    weight_kg: Mapped[float] = mapped_column(Float)
    initial_weight_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String, nullable=True, default="M")
    goal: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    
    user: Mapped["User"] = relationship(back_populates="fitness_profile")

