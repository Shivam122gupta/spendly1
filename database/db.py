import sqlite3

from werkzeug.security import generate_password_hash


def seed_db():
    """Insert demo user and sample expenses for development.

    Guard clause: if the users table already contains any rows, returns
    immediately so repeated calls never duplicate seed data.
    """
    conn = get_db()
    cursor = conn.cursor()

    # ── Duplicate protection ──────────────────────────────────────────
    existing = cursor.execute("SELECT COUNT(*) FROM users").fetchone()
    if existing[0] > 0:
        conn.close()
        return

    # ── Demo user ─────────────────────────────────────────────────────
    cursor.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (
            "Demo User",
            "demo@spendly.com",
            generate_password_hash("demo123"),
        ),
    )
    user_id = cursor.lastrowid

    # ── 8 sample expenses across all 7 categories ─────────────────────
    sample_expenses = [
        (user_id, 45.50,  "Food",          "2026-05-01", "Grocery shopping"),
        (user_id, 12.00,  "Transport",     "2026-05-03", "Uber ride"),
        (user_id, 120.00, "Bills",         "2026-05-05", "Electricity bill"),
        (user_id, 60.00,  "Health",        "2026-05-08", "Pharmacy"),
        (user_id, 15.99,  "Entertainment", "2026-05-10", "Netflix subscription"),
        (user_id, 89.95,  "Shopping",      "2026-05-14", "New shoes"),
        (user_id, 25.00,  "Other",         "2026-05-18", "Miscellaneous"),
        (user_id, 32.75,  "Food",          "2026-05-20", "Restaurant dinner"),
    ]

    cursor.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description)"
        " VALUES (?, ?, ?, ?, ?)",
        sample_expenses,
    )

    conn.commit()
    conn.close()


def init_db():
    """Create the users and expenses tables if they do not already exist.

    Safe to call multiple times — uses CREATE TABLE IF NOT EXISTS so it
    will not fail or overwrite data on repeated runs.
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            email         TEXT    UNIQUE NOT NULL,
            password_hash TEXT    NOT NULL,
            created_at    TEXT    DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id),
            amount      REAL    NOT NULL,
            category    TEXT    NOT NULL,
            date        TEXT    NOT NULL,
            description TEXT,
            created_at  TEXT    DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    conn.close()


def get_db():
    """Open and return a SQLite connection to spendly.db.

    The connection is configured with:
    - row_factory = sqlite3.Row  — enables dictionary-like row access
    - PRAGMA foreign_keys = ON   — enforces foreign key constraints
    """
    conn = sqlite3.connect("spendly.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_user(name, email, password):
    """Insert a new user into the users table and return the new id.

    Hashes *password* with werkzeug before storing.
    Raises sqlite3.IntegrityError if *email* is already taken (UNIQUE constraint).
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (name, email, generate_password_hash(password)),
    )
    user_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return user_id
