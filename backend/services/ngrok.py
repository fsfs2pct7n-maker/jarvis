"""ngrok tunnel management for iPhone access."""
import os
import time
from backend.database import get_db


def start_ngrok_tunnel(port: int = 8000) -> str:
    """Start ngrok tunnel and return the public URL."""
    auth_token = os.getenv("NGROK_AUTH_TOKEN", "")

    if not auth_token:
        print("[NGROK] No auth token. iPhone access disabled. Set NGROK_AUTH_TOKEN in .env")
        return ""

    try:
        from pyngrok import ngrok, conf

        # Set auth token
        conf.get_default().auth_token = auth_token

        # Open tunnel
        tunnel = ngrok.connect(port, "http")
        url = tunnel.public_url

        # Save to database
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("ngrok_url", url)
        )
        db.commit()
        db.close()

        print(f"[NGROK] Tunnel active: {url}")
        print(f"[NGROK] iPhone access: {url}")

        return url

    except ImportError:
        print("[NGROK] pyngrok not installed. Run: pip install pyngrok")
        return ""
    except Exception as e:
        print(f"[NGROK] Failed to start tunnel: {e}")
        return ""


def get_ngrok_url() -> str:
    """Get the current ngrok URL from database."""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'ngrok_url'")
        row = cursor.fetchone()
        db.close()
        return row["value"] if row else ""
    except Exception:
        return ""
