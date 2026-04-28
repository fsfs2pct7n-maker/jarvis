"""Pre-load Owen's known information into the memory database."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from backend.database import get_db

SEED_MEMORIES = [
    # Identity
    ("identity", "full_name", "Owen Medley", 1.0, "explicit"),
    ("identity", "location", "Lafayette, Indiana", 1.0, "explicit"),
    ("identity", "timezone", "America/Indiana/Indianapolis", 1.0, "explicit"),
    ("identity", "description", "Young entrepreneur who started businesses at age 12. Driven, fast-moving, multiple irons in the fire simultaneously.", 1.0, "explicit"),

    # Business — Black Label Breaks
    ("business", "blb_name", "Black Label Breaks, also called BLB", 1.0, "explicit"),
    ("business", "blb_partner", "Michael Bennet is Owen's BLB business partner", 1.0, "explicit"),
    ("business", "blb_platform", "BLB runs card breaks on TikTok and Whatnot", 1.0, "explicit"),
    ("business", "blb_volume", "BLB does approximately 30 cases per week, organized into 10 breaks with 8 divisions per break", 1.0, "explicit"),
    ("business", "blb_pricing", "BLB divisions are priced between $35 and $75 each", 1.0, "explicit"),
    ("business", "blb_fees", "TikTok charges 7 percent per sale. Whatnot charges 12 percent per sale.", 1.0, "explicit"),
    ("business", "blb_margin_target", "BLB targets a 33 percent profit margin", 1.0, "explicit"),

    # Business — TrackMyCards
    ("business", "trackmycards_name", "TrackMyCards is a SaaS card inventory tracker", 1.0, "explicit"),
    ("business", "trackmycards_price", "TrackMyCards charges $9.99 per month", 1.0, "explicit"),

    # Business — SignalX
    ("business", "signalx_name", "SignalX is an MNQ futures paper trading AI assistant", 1.0, "explicit"),

    # Other ventures
    ("business", "other_ventures", "Owen is also interested in real estate, stocks, vending machines, and networking", 1.0, "explicit"),

    # Relationships
    ("relationships", "michael_bennet", "Michael Bennet is Owen's BLB business partner. They run breaks together.", 1.0, "explicit"),
    ("relationships", "jaden", "Jaden is an electrician and Owen's separate business partner for non-BLB ventures", 1.0, "explicit"),
    ("relationships", "father", "Owen's father is his business advisor and sounding board", 1.0, "explicit"),

    # Tools & Preferences
    ("tools", "primary_stack", "Owen uses Supabase, Netlify, Antigravity (AI coding environment), Cursor (IDE), and Claude", 1.0, "explicit"),
    ("preferences", "ai_assistant", "Owen built Jarvis as his personal AI operating system to run 24/7 on his Mac", 1.0, "explicit"),
    ("preferences", "wake_time", "Owen typically wakes up around 7am in Lafayette, Indiana", 0.8, "explicit"),
]


def seed_memories():
    conn = get_db()
    cursor = conn.cursor()

    # Check if already seeded
    cursor.execute("SELECT COUNT(*) FROM memories WHERE source = 'explicit'")
    count = cursor.fetchone()[0]
    if count > 0:
        print(f"[SEED] Memories already seeded ({count} explicit memories found). Skipping.")
        conn.close()
        return

    for category, key, value, confidence, source in SEED_MEMORIES:
        cursor.execute("""
            INSERT INTO memories (category, key, value, confidence, source)
            VALUES (?, ?, ?, ?, ?)
        """, (category, key, value, confidence, source))

    conn.commit()
    conn.close()
    print(f"[SEED] Seeded {len(SEED_MEMORIES)} memories about Owen.")


if __name__ == "__main__":
    from backend.database import init_db
    init_db()
    seed_memories()
    print("[SEED] Done.")
