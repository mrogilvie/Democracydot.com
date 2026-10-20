import os
import hashlib
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st
from dotenv import load_dotenv
from streamlit.errors import StreamlitSecretNotFoundError


def _setting(name: str) -> str | None:
    load_dotenv(Path(__file__).resolve().with_name(".env"))
    try:
        value = st.secrets.get(name)
    except StreamlitSecretNotFoundError:
        value = None
    return value or os.getenv(name)


def get_owner_password() -> str | None:
    return _setting("DEMOCRACYDOT_OWNER_PASSWORD")


def _database_path() -> Path:
    configured_path = _setting("DEMOCRACYDOT_COMMENTS_DB")
    path = (
        Path(configured_path).expanduser()
        if configured_path
        else Path(__file__).resolve().with_name("comments.sqlite3")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_database_path(), timeout=10)
    os.chmod(_database_path(), 0o600)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submitted_at TEXT NOT NULL,
            bill_title TEXT NOT NULL,
            comment TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS signups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT COLLATE NOCASE UNIQUE,
            name TEXT NOT NULL DEFAULT '',
            mobile TEXT NOT NULL,
            consented_at TEXT NOT NULL
        )
        """
    )
    signup_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(signups)")
    }
    if "name" not in signup_columns:
        connection.execute(
            "ALTER TABLE signups ADD COLUMN name TEXT NOT NULL DEFAULT ''"
        )
    email_column = next(
        row
        for row in connection.execute("PRAGMA table_info(signups)")
        if row["name"] == "email"
    )
    if email_column["notnull"]:
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                """
                CREATE TABLE signups_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT COLLATE NOCASE UNIQUE,
                    name TEXT NOT NULL DEFAULT '',
                    mobile TEXT NOT NULL,
                    consented_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO signups_new (id, email, name, mobile, consented_at)
                SELECT id, email, name, mobile, consented_at FROM signups
                """
            )
            connection.execute("DROP TABLE signups")
            connection.execute("ALTER TABLE signups_new RENAME TO signups")
            connection.commit()
        except sqlite3.Error:
            connection.rollback()
            raise
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS signup_devices (
            device_hash TEXT PRIMARY KEY,
            signup_id INTEGER NOT NULL REFERENCES signups(id),
            device_reference TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    return connection


def save_comment(comment: str, bill_title: str = "") -> int:
    submitted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    normalized_bill_title = " ".join(bill_title.split())
    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO comments (submitted_at, bill_title, comment)
            VALUES (?, ?, ?)
            """,
            (submitted_at, normalized_bill_title, comment.strip()),
        )
        return int(cursor.lastrowid)


def get_comments() -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT id, submitted_at, bill_title, comment
            FROM comments
            ORDER BY id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def _normalize_mobile_key(mobile: str) -> str:
    digits = re.sub(r"\D", "", mobile)
    if len(digits) == 10 and digits.startswith("0"):
        return f"61{digits[1:]}"
    return digits


def save_signup(name: str, mobile: str, device_token: str) -> int:
    normalized_name = " ".join(name.split())
    normalized_mobile = " ".join(mobile.split())
    mobile_key = _normalize_mobile_key(normalized_mobile)
    normalized_name_key = normalized_name.casefold()
    device_hash = hashlib.sha256(device_token.encode("utf-8")).hexdigest()
    device_reference = device_hash[:12]
    consented_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        matching_mobile_signups = [
            signup
            for signup in connection.execute(
                "SELECT id, name, mobile FROM signups"
            ).fetchall()
            if _normalize_mobile_key(signup["mobile"]) == mobile_key
        ]
        existing_signup = next(
            (
                signup
                for signup in matching_mobile_signups
                if " ".join(signup["name"].split()).casefold()
                == normalized_name_key
            ),
            None,
        )
        if matching_mobile_signups and not existing_signup:
            raise ValueError(
                "That mobile number is already registered with a different "
                "name. Check the details or contact the app owner."
            )

        if existing_signup:
            signup_id = int(existing_signup["id"])
        else:
            cursor = connection.execute(
                """
                INSERT INTO signups (name, email, mobile, consented_at)
                VALUES (?, ?, ?, ?)
                """,
                (normalized_name, None, normalized_mobile, consented_at),
            )
            signup_id = int(cursor.lastrowid)

        connection.execute(
            """
            INSERT INTO signup_devices
                (device_hash, signup_id, device_reference, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(device_hash) DO NOTHING
            """,
            (device_hash, signup_id, device_reference, consented_at),
        )
        linked_signup = connection.execute(
            "SELECT signup_id FROM signup_devices WHERE device_hash = ?",
            (device_hash,),
        ).fetchone()
        if linked_signup is None or int(linked_signup["signup_id"]) != signup_id:
            raise ValueError("This browser token is already linked to another sign-up.")
        return signup_id


def get_signup_for_device(device_token: str) -> dict[str, Any] | None:
    if not device_token:
        return None
    device_hash = hashlib.sha256(device_token.encode("utf-8")).hexdigest()
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT signups.id, signups.name, signups.mobile
            FROM signup_devices
            JOIN signups ON signups.id = signup_devices.signup_id
            WHERE signup_devices.device_hash = ?
            """,
            (device_hash,),
        ).fetchone()
    return dict(row) if row else None


def get_signups() -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT
                signups.name,
                signups.email,
                signups.mobile,
                signups.consented_at,
                COUNT(signup_devices.device_hash) AS device_count,
                GROUP_CONCAT(signup_devices.device_reference, ', ')
                    AS device_references
            FROM signups
            LEFT JOIN signup_devices ON signup_devices.signup_id = signups.id
            GROUP BY signups.id
            ORDER BY signups.consented_at DESC, signups.id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]
