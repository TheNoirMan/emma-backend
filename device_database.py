import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any


# ============================================================
# EMMA DEVICE DATABASE
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "emma_devices.db"


def get_connection():
    connection = sqlite3.connect(
        DATABASE_PATH,
        check_same_thread=False,
    )

    connection.row_factory = sqlite3.Row

    return connection


# ============================================================
# INITIALIZE DATABASE
# ============================================================

def initialize_database():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS devices (

            device_id TEXT PRIMARY KEY,

            device_name TEXT NOT NULL,

            platform TEXT NOT NULL,

            pairing_code TEXT,

            device_token TEXT,

            connected INTEGER DEFAULT 0,

            created_at REAL NOT NULL,

            last_seen REAL NOT NULL

        )
        """
    )

    connection.commit()
    connection.close()


# ============================================================
# CREATE DEVICE
# ============================================================

def create_device(
    device_id: str,
    device_name: str,
    platform: str,
    pairing_code: str,
    created_at: float,
):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO devices (
            device_id,
            device_name,
            platform,
            pairing_code,
            connected,
            created_at,
            last_seen
        )

        VALUES (?, ?, ?, ?, 0, ?, ?)
        """,
        (
            device_id,
            device_name,
            platform,
            pairing_code,
            created_at,
            created_at,
        ),
    )

    connection.commit()
    connection.close()


# ============================================================
# GET DEVICE
# ============================================================

def get_device(
    device_id: str,
) -> Optional[Dict[str, Any]]:

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT *
        FROM devices
        WHERE device_id = ?
        """,
        (device_id,),
    )

    row = cursor.fetchone()

    connection.close()

    if row is None:
        return None

    return dict(row)


# ============================================================
# FIND DEVICE BY PAIRING CODE
# ============================================================

def get_device_by_pairing_code(
    pairing_code: str,
) -> Optional[Dict[str, Any]]:

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT *
        FROM devices
        WHERE pairing_code = ?
        """,
        (pairing_code,),
    )

    row = cursor.fetchone()

    connection.close()

    if row is None:
        return None

    return dict(row)


# ============================================================
# UPDATE CONNECTION
# ============================================================

def set_connected(
    device_id: str,
    connected: bool,
    last_seen: float,
):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE devices

        SET
            connected = ?,
            last_seen = ?

        WHERE device_id = ?
        """,
        (
            1 if connected else 0,
            last_seen,
            device_id,
        ),
    )

    connection.commit()
    connection.close()


# ============================================================
# UPDATE LAST SEEN
# ============================================================

def update_last_seen(
    device_id: str,
    last_seen: float,
):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE devices

        SET last_seen = ?

        WHERE device_id = ?
        """,
        (
            last_seen,
            device_id,
        ),
    )

    connection.commit()
    connection.close()


# ============================================================
# SAVE DEVICE TOKEN
# ============================================================

def save_device_token(
    device_id: str,
    device_token: str,
):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE devices

        SET device_token = ?

        WHERE device_id = ?
        """,
        (
            device_token,
            device_id,
        ),
    )

    connection.commit()
    connection.close()


# ============================================================
# GET DEVICE BY TOKEN
# ============================================================

def get_device_by_token(
    device_token: str,
) -> Optional[Dict[str, Any]]:

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT *
        FROM devices

        WHERE device_token = ?
        """,
        (
            device_token,
        ),
    )

    row = cursor.fetchone()

    connection.close()

    if row is None:
        return None

    return dict(row)


# ============================================================
# REMOVE PAIRING CODE
# ============================================================

def clear_pairing_code(
    device_id: str,
):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE devices

        SET pairing_code = NULL

        WHERE device_id = ?
        """,
        (
            device_id,
        ),
    )

    connection.commit()
    connection.close()