"""Engine y sesiones. Lee `DATABASE_URL` (default `sqlite:///var/autoguard.db`).

Uso:
    from autoguard.db.session import session_scope
    with session_scope() as s:
        repo.save_vehicle(s, perfil)

Supabase/Postgres: DATABASE_URL=postgresql+psycopg://user:pass@host:5432/postgres (solo en .env).
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from autoguard.db.models import Base

DEFAULT_URL = "sqlite:///var/autoguard.db"

_engines: dict[str, Engine] = {}


def database_url() -> str:
    return os.environ.get("DATABASE_URL") or DEFAULT_URL


def _normalize(url: str) -> str:
    # Supabase entrega "postgres://..." / "postgresql://..."; usamos el driver psycopg 3 instalado.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def get_engine(url: Optional[str] = None, *, create_tables: bool = True) -> Engine:
    """Engine cacheado por URL. `sqlite://` (memoria) usa StaticPool para compartir la BD entre sesiones."""
    url = _normalize(url or database_url())
    if url in _engines:
        return _engines[url]
    if url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        path = url.split("///", 1)[1] if "///" in url else ""
        if path in ("", ":memory:"):
            kwargs["poolclass"] = StaticPool
        else:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, **kwargs)
    else:
        engine = create_engine(url, pool_pre_ping=True)
    if create_tables:
        init_db(engine)
    _engines[url] = engine
    return engine


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def get_sessionmaker(url: Optional[str] = None) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(url), expire_on_commit=False)


def get_session(url: Optional[str] = None) -> Session:
    return get_sessionmaker(url)()


@contextmanager
def session_scope(url: Optional[str] = None) -> Iterator[Session]:
    """Sesión transaccional: commit al salir, rollback si hay excepción."""
    session = get_session(url)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def dispose_all() -> None:
    for e in _engines.values():
        e.dispose()
    _engines.clear()
