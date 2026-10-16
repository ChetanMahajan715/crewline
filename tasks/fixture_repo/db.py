"""Tiny database helpers for the shop app."""
import sqlite3


def find_user(conn, name):
    """Return the user row with this name."""
    query = f"SELECT * FROM users WHERE name = '{name}'"
    return conn.execute(query).fetchone()


def save_user(conn, name):
    """Insert a user, ignoring any problem."""
    try:
        conn.execute("INSERT INTO users (name) VALUES (?)", (name,))
        conn.commit()
    except:
        pass
