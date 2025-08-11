from __future__ import annotations
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Iterable

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "brasa.db"

def _connect() -> sqlite3.Connection:
    """Abre conexão nova por operação (bom com threads)."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5.0, isolation_level=None) # autocommit
    conn.row_factory = sqlite3.Row
    # PRAGMAs uteis para concorrencia moderada
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def init_db() -> None:
    """Cria tabelas se não existirem."""
    with _connect() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS eco_messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at  TEXT    NOT NULL,   -- ISO 8601 em UTC
            ip          TEXT    NOT NULL,
            nome        TEXT    NOT NULL,
            mensagem    TEXT    NOT NULL,
            ua          TEXT    NOT NULL
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_eco_created ON eco_messages(created_at DESC);")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS love_notes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at  TEXT    NOT NULL,
            author      TEXT    NOT NULL,
            message     TEXT    NOT NULL
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_love_created ON love_notes(created_at DESC);")


def insert_eco(ip: str, nome: str, mensagem: str, ua: str) -> int:
    """Insere uma mensagem e retorna o id."""
    ts = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    # saneamento leve de tamanho (defensivo)
    nome = (nome or "").strip()[:200]
    mensagem = (mensagem or "").strip()[:5000]
    ua = (ua or "").strip()[:500]

    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO eco_messages (created_at, ip, nome, mensagem, ua) VALUES (?, ?, ?, ?, ?)",
            (ts, ip, nome, mensagem, ua),
        )
        return cur.lastrowid

def fetch_recent(limit: int = 20) -> list[dict]:
    """Busca mensagens mais recentes, como dicts."""
    limit = max(1, min(int(limit or 20), 200))
    with _connect() as conn:
        cur = conn.execute(
            "SELECT id, created_at, ip, nome, mensagem, ua FROM eco_messages ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]
    
def insert_love_note(author: str, message: str) -> int:
    from datetime import datetime
    ts = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    author = (author or "Anônimo").strip()[:80]
    message = (message or "").strip()[:500]
    if not message:
        raise ValueError("empty message")
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO love_notes (created_at, author, message) VALUES (?, ?, ?)",
            (ts, author, message)
        )
        return cur.lastrowid

def fetch_love_notes(limit: int = 20) -> list[dict]:
    limit = max(1, min(int(limit or 20), 200))
    with _connect() as conn:
        cur = conn.execute(
            "SELECT id, created_at, author, message FROM love_notes ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        return [dict(r) for r in cur.fetchall()]