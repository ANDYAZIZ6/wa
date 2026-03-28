from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from flask import current_app, g
from sqlalchemy import JSON, BigInteger, ForeignKey, Index, String, Text, UniqueConstraint, case, create_engine, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from sqlalchemy.types import DateTime, TypeDecorator


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_datetime(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return ensure_utc(value)
    normalized = value.strip().replace("Z", "+00:00")
    return ensure_utc(datetime.fromisoformat(normalized))


def serialize_datetime(value: str | datetime | None) -> str | None:
    dt = parse_datetime(value)
    if dt is None:
        return None
    return dt.isoformat().replace("+00:00", "Z")


class UTCDateTime(TypeDecorator):
    cache_ok = True
    impl = DateTime(timezone=True)

    def load_dialect_impl(self, dialect):
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(32))
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(self, value, dialect):
        dt = parse_datetime(value)
        if dt is None:
            return None
        if dialect.name == "sqlite":
            return serialize_datetime(dt)
        return dt

    def process_result_value(self, value, dialect):
        return parse_datetime(value)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    initial_balance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    plan: Mapped[str] = mapped_column(String(32), nullable=False, default="FREE")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    messages: Mapped[list["Message"]] = relationship(back_populates="user")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("idx_transactions_user_time", "user_id", "transaction_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="whatsapp")
    transaction_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)

    user: Mapped[User] = relationship(back_populates="transactions")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("provider", "provider_message_id", "direction", name="uq_message_provider_direction"),
        Index("idx_messages_user_time", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_message_id: Mapped[str] = mapped_column(String(120), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)

    user: Mapped[User | None] = relationship(back_populates="messages")


def _db_state() -> dict[str, Any]:
    return current_app.extensions["db"]


def get_session() -> Session:
    if "db_session" not in g:
        g.db_session = _db_state()["session_factory"]()
    return g.db_session


def close_db(_: Any = None) -> None:
    session = g.pop("db_session", None)
    if session is not None:
        session.close()


def _engine_kwargs(url: str) -> dict[str, Any]:
    if url.startswith("sqlite"):
        return {
            "future": True,
            "connect_args": {"check_same_thread": False},
        }
    return {
        "future": True,
        "pool_pre_ping": True,
        "pool_size": current_app.config["DB_POOL_SIZE"],
        "max_overflow": current_app.config["DB_MAX_OVERFLOW"],
        "pool_recycle": current_app.config["DB_POOL_RECYCLE_SECONDS"],
    }


def init_app(app) -> None:
    with app.app_context():
        engine = create_engine(app.config["DATABASE_URL"], **_engine_kwargs(app.config["DATABASE_URL"]))
        Base.metadata.create_all(engine)
        app.extensions["db"] = {
            "engine": engine,
            "session_factory": sessionmaker(bind=engine, expire_on_commit=False, future=True),
        }
    app.teardown_appcontext(close_db)


def healthcheck() -> bool:
    try:
        session = get_session()
        session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _tz() -> ZoneInfo:
    return ZoneInfo(current_app.config["APP_TIMEZONE"])


def _local_date_bounds(start_date: str | None = None, end_date: str | None = None, days: int | None = None) -> tuple[datetime | None, datetime | None]:
    local_today = datetime.now(_tz()).date()
    effective_start = date.fromisoformat(start_date) if start_date else None
    effective_end = date.fromisoformat(end_date) if end_date else None

    if days is not None:
        effective_start = local_today - timedelta(days=days - 1)
        effective_end = local_today

    start_utc = None
    end_utc = None
    if effective_start is not None:
        start_utc = datetime.combine(effective_start, time.min, tzinfo=_tz()).astimezone(timezone.utc)
    if effective_end is not None:
        end_utc = datetime.combine(effective_end + timedelta(days=1), time.min, tzinfo=_tz()).astimezone(timezone.utc)
    return start_utc, end_utc


def _base_tx_filters(*, user_id: int, search: str | None = None, tx_type: str | None = None, start_date: str | None = None, end_date: str | None = None, days: int | None = None) -> list:
    filters = [Transaction.user_id == int(user_id)]
    if search:
        filters.append(func.lower(Transaction.description).like(f"%{search.lower()}%"))
    if tx_type in {"income", "expense"}:
        filters.append(Transaction.type == tx_type)

    start_utc, end_utc = _local_date_bounds(start_date=start_date, end_date=end_date, days=days)
    if start_utc is not None:
        filters.append(Transaction.transaction_at >= start_utc)
    if end_utc is not None:
        filters.append(Transaction.transaction_at < end_utc)
    return filters


def _user_to_dict(user: User | None) -> dict[str, Any] | None:
    if user is None:
        return None
    return {
        "id": user.id,
        "phone": user.phone,
        "name": user.name,
        "password_hash": user.password_hash,
        "initial_balance": int(user.initial_balance),
        "plan": user.plan,
        "created_at": serialize_datetime(user.created_at),
        "updated_at": serialize_datetime(user.updated_at),
    }


def _transaction_to_dict(tx: Transaction | None) -> dict[str, Any] | None:
    if tx is None:
        return None
    return {
        "id": tx.id,
        "user_id": tx.user_id,
        "amount": int(tx.amount),
        "type": tx.type,
        "description": tx.description,
        "category": tx.category,
        "source": tx.source,
        "transaction_at": serialize_datetime(tx.transaction_at),
        "created_at": serialize_datetime(tx.created_at),
        "updated_at": serialize_datetime(tx.updated_at),
    }


def _message_to_dict(message: Message | None) -> dict[str, Any] | None:
    if message is None:
        return None
    return {
        "id": message.id,
        "user_id": message.user_id,
        "provider": message.provider,
        "provider_message_id": message.provider_message_id,
        "direction": message.direction,
        "phone": message.phone,
        "body": message.body,
        "raw_payload": message.raw_payload or {},
        "created_at": serialize_datetime(message.created_at),
    }


def get_user_by_phone(phone: str) -> dict[str, Any] | None:
    session = get_session()
    user = session.execute(select(User).where(User.phone == phone)).scalar_one_or_none()
    return _user_to_dict(user)


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    session = get_session()
    user = session.get(User, int(user_id))
    return _user_to_dict(user)


def create_user(*, phone: str, password_hash: str, name: str | None = None, initial_balance: int = 0, plan: str = "FREE") -> int:
    session = get_session()
    now = utcnow()
    user = User(
        phone=phone,
        name=name or phone,
        password_hash=password_hash,
        initial_balance=int(initial_balance),
        plan=plan,
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    session.commit()
    return int(user.id)


def update_user_password(user_id: int, password_hash: str) -> None:
    session = get_session()
    user = session.get(User, int(user_id))
    if not user:
        return
    user.password_hash = password_hash
    user.updated_at = utcnow()
    session.commit()


def update_user_balance(user_id: int, initial_balance: int) -> None:
    session = get_session()
    user = session.get(User, int(user_id))
    if not user:
        return
    user.initial_balance = int(initial_balance)
    user.updated_at = utcnow()
    session.commit()


def update_user_plan(user_id: int, plan: str) -> None:
    session = get_session()
    user = session.get(User, int(user_id))
    if not user:
        return
    user.plan = plan
    user.updated_at = utcnow()
    session.commit()


def create_transaction(*, user_id: int, amount: int, description: str, category: str | None, source: str, transaction_at: str | datetime | None = None) -> int:
    session = get_session()
    now = utcnow()
    tx = Transaction(
        user_id=int(user_id),
        amount=int(amount),
        type="income" if int(amount) >= 0 else "expense",
        description=description,
        category=category,
        source=source,
        transaction_at=parse_datetime(transaction_at) or now,
        created_at=now,
        updated_at=now,
    )
    session.add(tx)
    session.commit()
    return int(tx.id)


def update_transaction(tx_id: int, *, amount: int, description: str, category: str | None) -> None:
    session = get_session()
    tx = session.get(Transaction, int(tx_id))
    if not tx:
        return
    tx.amount = int(amount)
    tx.type = "income" if int(amount) >= 0 else "expense"
    tx.description = description
    tx.category = category
    tx.updated_at = utcnow()
    session.commit()


def delete_transaction(tx_id: int) -> None:
    session = get_session()
    tx = session.get(Transaction, int(tx_id))
    if not tx:
        return
    session.delete(tx)
    session.commit()


def get_transaction(tx_id: int) -> dict[str, Any] | None:
    session = get_session()
    tx = session.get(Transaction, int(tx_id))
    return _transaction_to_dict(tx)


def count_transactions(*, user_id: int, search: str | None = None, tx_type: str | None = None, start_date: str | None = None, end_date: str | None = None) -> int:
    session = get_session()
    filters = _base_tx_filters(user_id=user_id, search=search, tx_type=tx_type, start_date=start_date, end_date=end_date)
    return int(session.execute(select(func.count(Transaction.id)).where(*filters)).scalar_one())


def list_transactions(
    *,
    user_id: int,
    search: str | None = None,
    tx_type: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    session = get_session()
    filters = _base_tx_filters(user_id=user_id, search=search, tx_type=tx_type, start_date=start_date, end_date=end_date)
    stmt = (
        select(Transaction)
        .where(*filters)
        .order_by(Transaction.transaction_at.desc(), Transaction.id.desc())
        .offset(max(int(offset), 0))
    )
    if limit is not None:
        stmt = stmt.limit(int(limit))
    rows = session.execute(stmt).scalars().all()
    return [_transaction_to_dict(row) for row in rows]


def reset_user_ledger(user_id: int) -> None:
    session = get_session()
    user = session.get(User, int(user_id))
    if not user:
        return
    session.query(Transaction).filter(Transaction.user_id == int(user_id)).delete(synchronize_session=False)
    user.initial_balance = 0
    user.updated_at = utcnow()
    session.commit()


def get_balance(user_id: int) -> int:
    session = get_session()
    user = session.get(User, int(user_id))
    if not user:
        return 0
    tx_total = session.execute(select(func.coalesce(func.sum(Transaction.amount), 0)).where(Transaction.user_id == int(user_id))).scalar_one()
    return int(user.initial_balance) + int(tx_total or 0)


def summarize(user_id: int, *, days: int | None = None, start_date: str | None = None, end_date: str | None = None) -> dict[str, int]:
    session = get_session()
    filters = _base_tx_filters(user_id=int(user_id), start_date=start_date, end_date=end_date, days=days)
    income_expr = func.coalesce(func.sum(case((Transaction.amount >= 0, Transaction.amount), else_=0)), 0)
    expense_expr = func.coalesce(func.sum(case((Transaction.amount < 0, -Transaction.amount), else_=0)), 0)
    income, expense = session.execute(select(income_expr, expense_expr).where(*filters)).one()
    income_total = int(income or 0)
    expense_total = int(expense or 0)
    return {
        "income": income_total,
        "expense": expense_total,
        "net": income_total - expense_total,
    }


def get_transaction_overview(user_id: int) -> dict[str, Any]:
    session = get_session()
    filters = _base_tx_filters(user_id=int(user_id))
    count_expr = func.count(Transaction.id)
    oldest_expr = func.min(Transaction.transaction_at)
    count_value, oldest = session.execute(select(count_expr, oldest_expr).where(*filters)).one()
    return {
        "count": int(count_value or 0),
        "since": serialize_datetime(oldest),
    }


def daily_rollup(user_id: int, *, start_date: str | None = None, end_date: str | None = None, limit: int = 60) -> list[dict[str, Any]]:
    session = get_session()
    if not start_date and not end_date:
        start_date = (datetime.now(_tz()).date() - timedelta(days=max(limit - 1, 0))).isoformat()
    filters = _base_tx_filters(user_id=int(user_id), start_date=start_date, end_date=end_date)
    rows = session.execute(
        select(Transaction.transaction_at, Transaction.amount).where(*filters).order_by(Transaction.transaction_at.desc())
    ).all()

    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"income": 0, "expense": 0, "net": 0, "count": 0})
    for transaction_at, amount in rows:
        local_day = ensure_utc(transaction_at).astimezone(_tz()).date().isoformat()
        bucket = grouped[local_day]
        if int(amount) >= 0:
            bucket["income"] += int(amount)
        else:
            bucket["expense"] += abs(int(amount))
        bucket["net"] += int(amount)
        bucket["count"] += 1

    result = []
    for day in sorted(grouped.keys(), reverse=True)[:limit]:
        payload = grouped[day]
        result.append(
            {
                "day": day,
                "income": payload["income"],
                "expense": payload["expense"],
                "net": payload["net"],
                "count": payload["count"],
            }
        )
    return result


def log_message(*, user_id: int | None, provider: str, provider_message_id: str, direction: str, phone: str, body: str, raw_payload: dict[str, Any] | None = None) -> bool:
    session = get_session()
    message = Message(
        user_id=user_id,
        provider=provider,
        provider_message_id=provider_message_id,
        direction=direction,
        phone=phone,
        body=body,
        raw_payload=raw_payload or {},
        created_at=utcnow(),
    )
    session.add(message)
    try:
        session.commit()
        return True
    except IntegrityError:
        session.rollback()
        return False


def list_messages(user_id: int, limit: int = 20) -> list[dict[str, Any]]:
    session = get_session()
    rows = session.execute(
        select(Message)
        .where(Message.user_id == int(user_id))
        .order_by(Message.created_at.desc())
        .limit(int(limit))
    ).scalars().all()
    return [_message_to_dict(row) for row in rows]
