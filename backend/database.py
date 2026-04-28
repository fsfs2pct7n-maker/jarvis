import sqlite3
import os
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "jarvis.db"


def get_db():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            confidence REAL DEFAULT 1.0,
            source TEXT DEFAULT 'conversation',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            times_referenced INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            model_used TEXT,
            tools_used TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            result TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            content TEXT NOT NULL,
            delivered INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS briefings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            content TEXT NOT NULL,
            read INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS automation_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            trigger_type TEXT NOT NULL,
            trigger_config TEXT NOT NULL,
            actions TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            run_count INTEGER DEFAULT 0,
            last_run DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS automation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id INTEGER NOT NULL,
            trigger_data TEXT,
            actions_taken TEXT,
            success INTEGER DEFAULT 1,
            ran_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- Phase 3+4: Activity & Learning

        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            input_text TEXT,
            tool_used TEXT,
            tool_input TEXT,
            response_ms INTEGER,
            tone TEXT DEFAULT 'neutral',
            hour_of_day INTEGER,
            day_of_week INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS preferences (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            source TEXT DEFAULT 'inferred',
            confidence REAL DEFAULT 0.5,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS detected_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_type TEXT NOT NULL,
            description TEXT NOT NULL,
            data TEXT,
            confidence REAL DEFAULT 0.5,
            occurrence_count INTEGER DEFAULT 1,
            first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS email_importance (
            message_id TEXT PRIMARY KEY,
            sender TEXT,
            subject TEXT,
            importance_score REAL DEFAULT 0.5,
            action_required INTEGER DEFAULT 0,
            scored_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.commit()

    # Migration: add source_id to alerts if not present (idempotent)
    try:
        conn.execute("ALTER TABLE alerts ADD COLUMN source_id TEXT")
        conn.commit()
    except Exception:
        pass  # column already exists

    conn.close()
    print(f"[DB] Database initialized at {DB_PATH}")
