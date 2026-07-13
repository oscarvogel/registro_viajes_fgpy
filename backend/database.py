from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.exc import DisconnectionError
from sqlalchemy.orm import declarative_base, sessionmaker
import os
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")
load_dotenv()

# Default to sqlite for local dev if MySQL url not present, but user asked for MySQL
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sql_app.db")

# Configure engine with sensible pool settings for MySQL to avoid "Connection not available" errors
# - pool_pre_ping: tests connections before using them (avoids stale/disconnected connections)
# - pool_recycle: recycle connections older than this many seconds (avoid server-side timeouts)
# - pool_size / max_overflow: tune according to load
pool_settings = {}
if "sqlite" not in SQLALCHEMY_DATABASE_URL:
    pool_size = int(os.getenv("DB_POOL_SIZE", 5))
    max_overflow = int(os.getenv("DB_MAX_OVERFLOW", 10))
    pool_recycle = int(os.getenv("DB_POOL_RECYCLE", 280))
    pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", 30))
    connection_timeout = int(os.getenv("DB_CONNECT_TIMEOUT", 8))
    read_timeout = int(os.getenv("DB_READ_TIMEOUT", 20))
    write_timeout = int(os.getenv("DB_WRITE_TIMEOUT", 20))

    pool_settings = {
        "pool_size": pool_size,
        "max_overflow": max_overflow,
        "pool_recycle": pool_recycle,
        "pool_timeout": pool_timeout,
        "pool_pre_ping": True,
        "pool_use_lifo": True,
    }

connect_args = {"check_same_thread": False} if "sqlite" in SQLALCHEMY_DATABASE_URL else {
    "connection_timeout": connection_timeout,
    "connect_timeout": connection_timeout,
    "read_timeout": read_timeout,
    "write_timeout": write_timeout,
}

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    # check_same_thread is needed only for SQLite
    connect_args=connect_args,
    **pool_settings
)

if SQLALCHEMY_DATABASE_URL.startswith("mysql"):
    @event.listens_for(engine, "checkout")
    def ping_mysql_connection(dbapi_connection, connection_record, connection_proxy):
        try:
            dbapi_connection.ping(reconnect=True, attempts=1, delay=0)
        except Exception as exc:
            connection_record.invalidate(exc)
            raise DisconnectionError() from exc

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
