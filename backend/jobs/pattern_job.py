"""Background job: hourly pattern detection and preference inference."""
import threading
import time
import traceback


def _run_pattern_loop():
    """Run every hour — detect patterns, infer preferences, score recent emails."""
    # Wait a bit after startup before first run
    time.sleep(120)

    while True:
        try:
            from backend.brain.insights import detect_and_store_patterns
            from backend.brain.activity import get_activity_stats
            from backend.brain.preferences import infer_response_length_pref

            patterns = detect_and_store_patterns()
            if patterns:
                print(f"[PATTERNS] {len(patterns)} pattern(s) updated.")

            stats = get_activity_stats(days=14)
            if stats.get("total_interactions", 0) >= 10:
                infer_response_length_pref(stats)

        except Exception:
            print(f"[PATTERNS] Error in pattern loop:\n{traceback.format_exc()}")

        # Run every hour
        time.sleep(3600)


def start_pattern_engine():
    t = threading.Thread(target=_run_pattern_loop, daemon=True, name="pattern-engine")
    t.start()
    print("[PATTERNS] Pattern engine started.")
