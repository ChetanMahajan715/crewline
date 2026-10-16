"""Command line entry point for the shop app."""
import sqlite3

from db import find_user, save_user
from settings import DB_PATH
from stats import average_price


def main():
    """Add a demo user and print the average price."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS users (name TEXT)")
    save_user(conn, "demo")
    print(find_user(conn, "demo"))
    print(average_price([10, 20, 30]))


if __name__ == "__main__":
    main()
