"""Comptes utilisateurs et sessions de connexion, stockés dans SQLite.

Les mots de passe sont hachés avec scrypt (bibliothèque standard) ; seule
l'empreinte SHA-256 des jetons de session est conservée, pour qu'une fuite
de la base ne permette pas de se connecter à la place d'un utilisateur.
"""

import hashlib
import hmac
import re
import secrets
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL
);
"""

_SCRYPT = {"n": 2**14, "r": 8, "p": 1}
_USERNAME = re.compile(r"[A-Za-z0-9._-]{3,32}")
MIN_PASSWORD_LENGTH = 8


class UserError(ValueError):
    """Nom d'utilisateur ou mot de passe refusé."""


@dataclass
class User:
    id: str
    username: str
    is_admin: bool
    created_at: datetime


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    _, salt, expected = stored.split("$")
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), **_SCRYPT)
    return hmac.compare_digest(digest.hex(), expected)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        is_admin=bool(row["is_admin"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class UserStore:
    def __init__(self, db_path: Path, session_lifetime: timedelta = timedelta(days=7)):
        self.db_path = db_path
        self.session_lifetime = session_lifetime
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def create(self, username: str, password: str, is_admin: bool = False) -> User:
        username = username.strip()
        if not _USERNAME.fullmatch(username):
            raise UserError("Identifiant invalide : 3 à 32 caractères, lettres, chiffres, « . », « - » ou « _ »")
        if len(password) < MIN_PASSWORD_LENGTH:
            raise UserError(f"Mot de passe trop court ({MIN_PASSWORD_LENGTH} caractères minimum)")
        user = User(id=uuid.uuid4().hex, username=username, is_admin=is_admin, created_at=_now())
        try:
            with self._connect() as db:
                db.execute(
                    "INSERT INTO users (id, username, password_hash, is_admin, created_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (user.id, user.username, hash_password(password), int(is_admin),
                     user.created_at.isoformat()),
                )
        except sqlite3.IntegrityError:
            raise UserError("Cet identifiant est déjà utilisé") from None
        return user

    def ensure_admin(self, username: str, password: str) -> None:
        """Crée le compte administrateur configuré s'il n'existe pas encore."""
        with self._connect() as db:
            row = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
            if row:
                db.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (row["id"],))
                return
        self.create(username, password, is_admin=True)

    def get(self, user_id: str) -> User | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_to_user(row) if row else None

    def usernames(self, user_ids: set[str]) -> dict[str, str]:
        """Identifiant de chaque utilisateur, pour afficher le propriétaire des jobs."""
        if not user_ids:
            return {}
        placeholders = ", ".join("?" * len(user_ids))
        with self._connect() as db:
            rows = db.execute(
                f"SELECT id, username FROM users WHERE id IN ({placeholders})", tuple(user_ids),
            ).fetchall()
        return {row["id"]: row["username"] for row in rows}

    def authenticate(self, username: str, password: str) -> User | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM users WHERE username = ?", (username.strip(),)).fetchone()
        if row is None or not verify_password(password, row["password_hash"]):
            return None
        return _row_to_user(row)

    def open_session(self, user: User) -> str:
        token = secrets.token_urlsafe(32)
        with self._connect() as db:
            db.execute("DELETE FROM sessions WHERE expires_at < ?", (_now().isoformat(),))
            db.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (_hash_token(token), user.id, (_now() + self.session_lifetime).isoformat()),
            )
        return token

    def user_for_token(self, token: str) -> User | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT users.* FROM sessions JOIN users ON users.id = sessions.user_id"
                " WHERE token_hash = ? AND expires_at > ?",
                (_hash_token(token), _now().isoformat()),
            ).fetchone()
        return _row_to_user(row) if row else None

    def close_session(self, token: str) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash_token(token),))
