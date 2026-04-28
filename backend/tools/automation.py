"""Automation Rules Engine — if/then rules stored in SQLite.

Trigger types: email, time, keyword, startup
Action types:  notify, speak, send_email, open_app, run_command, create_event
"""
import json
from datetime import datetime
from typing import List, Dict, Any, Optional


def _get_db():
    from backend.database import get_db
    return get_db()


# ── CRUD ──────────────────────────────────────────────────────────────────────

def create_rule(name: str, trigger_type: str, trigger_config: Dict,
                actions: List[Dict]) -> str:
    """Create a new automation rule. Returns description of what was created."""
    if not name or not trigger_type or not actions:
        return "Rule needs a name, trigger type, and at least one action."

    conn = _get_db()
    try:
        conn.execute(
            """INSERT INTO automation_rules
               (name, trigger_type, trigger_config, actions)
               VALUES (?, ?, ?, ?)""",
            (name, trigger_type, json.dumps(trigger_config), json.dumps(actions))
        )
        conn.commit()
        return f"Automation rule '{name}' created. Trigger: {trigger_type}."
    except Exception as e:
        return f"Could not create rule: {e}"
    finally:
        conn.close()


def list_rules() -> str:
    """List all automation rules."""
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT id, name, trigger_type, enabled, run_count FROM automation_rules ORDER BY id"
        ).fetchall()
        if not rows:
            return "No automation rules set up yet. Try: 'create a rule that alerts me when I get email from [sender]'."
        lines = [f"Automation rules ({len(rows)} total):"]
        for row in rows:
            status = "on" if row['enabled'] else "off"
            lines.append(f"  [{row['id']}] {row['name']} — trigger: {row['trigger_type']} — {status} — ran {row['run_count']}x")
        return "\n".join(lines)
    finally:
        conn.close()


def get_rule(rule_id: int) -> Optional[Dict]:
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT * FROM automation_rules WHERE id = ?", (rule_id,)
        ).fetchone()
        if not row:
            return None
        return {
            'id': row['id'],
            'name': row['name'],
            'trigger_type': row['trigger_type'],
            'trigger_config': json.loads(row['trigger_config']),
            'actions': json.loads(row['actions']),
            'enabled': bool(row['enabled']),
            'run_count': row['run_count'],
        }
    finally:
        conn.close()


def delete_rule(rule_id: int) -> str:
    conn = _get_db()
    try:
        row = conn.execute("SELECT name FROM automation_rules WHERE id = ?", (rule_id,)).fetchone()
        if not row:
            return f"No rule found with ID {rule_id}."
        conn.execute("DELETE FROM automation_rules WHERE id = ?", (rule_id,))
        conn.commit()
        return f"Rule '{row['name']}' deleted."
    except Exception as e:
        return f"Could not delete rule: {e}"
    finally:
        conn.close()


def toggle_rule(rule_id: int, enabled: bool) -> str:
    conn = _get_db()
    try:
        conn.execute(
            "UPDATE automation_rules SET enabled = ? WHERE id = ?",
            (1 if enabled else 0, rule_id)
        )
        conn.commit()
        state = "enabled" if enabled else "disabled"
        return f"Rule {rule_id} {state}."
    except Exception as e:
        return f"Could not toggle rule: {e}"
    finally:
        conn.close()


# ── Trigger checking ──────────────────────────────────────────────────────────

def check_email_triggers(sender: str, subject: str, body_preview: str = "") -> List[Dict]:
    """Return rules that match an incoming email. Called by email_monitor."""
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM automation_rules WHERE trigger_type = 'email' AND enabled = 1"
        ).fetchall()
        triggered = []
        for row in rows:
            cfg = json.loads(row['trigger_config'])
            from_match = cfg.get('from', '').lower()
            subject_match = cfg.get('subject', '').lower()
            keyword_match = cfg.get('keyword', '').lower()

            if from_match and from_match not in sender.lower():
                continue
            if subject_match and subject_match not in subject.lower():
                continue
            if keyword_match and keyword_match not in (subject + body_preview).lower():
                continue

            triggered.append({
                'id': row['id'],
                'name': row['name'],
                'actions': json.loads(row['actions']),
            })
        return triggered
    finally:
        conn.close()


def check_keyword_triggers(text: str) -> List[Dict]:
    """Return rules that match a keyword in user speech/text."""
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM automation_rules WHERE trigger_type = 'keyword' AND enabled = 1"
        ).fetchall()
        triggered = []
        for row in rows:
            cfg = json.loads(row['trigger_config'])
            keyword = cfg.get('keyword', '').lower()
            if keyword and keyword in text.lower():
                triggered.append({
                    'id': row['id'],
                    'name': row['name'],
                    'actions': json.loads(row['actions']),
                })
        return triggered
    finally:
        conn.close()


# ── Action execution ──────────────────────────────────────────────────────────

async def execute_actions(rule_id: int, rule_name: str,
                           actions: List[Dict], trigger_data: str = "") -> List[str]:
    """Execute the actions of a triggered rule. Returns list of result strings."""
    results = []

    for action in actions:
        action_type = action.get('type', '')
        try:
            if action_type == 'speak':
                msg = action.get('message', rule_name)
                from backend.audio.text_to_speech import speak
                speak(msg)
                results.append(f"Spoke: {msg}")

            elif action_type == 'notify':
                msg = action.get('message', rule_name)
                # Broadcast to UI
                from backend.app import broadcast_message
                await broadcast_message({'type': 'proactive_alert', 'content': msg})
                results.append(f"Notified: {msg}")

            elif action_type == 'send_email':
                from backend.tools.gmail import send_email
                result = send_email(
                    to=action.get('to', ''),
                    subject=action.get('subject', 'Jarvis Automation'),
                    body=action.get('body', ''),
                )
                results.append(result)

            elif action_type == 'open_app':
                from backend.tools.mac_control import execute_mac_action
                result = execute_mac_action('open_app', action.get('app', ''))
                results.append(result)

            elif action_type == 'run_command':
                from backend.tools.mac_control import execute_mac_action
                result = execute_mac_action('run_terminal_command', action.get('command', ''))
                results.append(result)

            elif action_type == 'create_event':
                from backend.tools.calendar import create_event_from_text
                result = create_event_from_text(action.get('text', ''))
                results.append(result)

            else:
                results.append(f"Unknown action type: {action_type}")

        except Exception as e:
            results.append(f"Action '{action_type}' failed: {e}")

    # Log the run
    _log_run(rule_id, trigger_data, results)
    _increment_run_count(rule_id)

    return results


def _log_run(rule_id: int, trigger_data: str, results: List[str]):
    conn = _get_db()
    try:
        conn.execute(
            "INSERT INTO automation_log (rule_id, trigger_data, actions_taken) VALUES (?, ?, ?)",
            (rule_id, trigger_data, json.dumps(results))
        )
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def _increment_run_count(rule_id: int):
    conn = _get_db()
    try:
        conn.execute(
            "UPDATE automation_rules SET run_count = run_count + 1, last_run = CURRENT_TIMESTAMP WHERE id = ?",
            (rule_id,)
        )
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


# ── Voice interface helper ─────────────────────────────────────────────────────

def handle_automation_request(action: str, name: str = "", trigger_type: str = "",
                               trigger_config: Dict = None, actions: List = None,
                               rule_id: int = 0) -> str:
    """Single entry point for Claude tool calls."""
    if action == "list":
        return list_rules()
    elif action == "create":
        return create_rule(name, trigger_type, trigger_config or {}, actions or [])
    elif action == "delete":
        return delete_rule(rule_id)
    elif action == "enable":
        return toggle_rule(rule_id, True)
    elif action == "disable":
        return toggle_rule(rule_id, False)
    else:
        return f"Unknown automation action: {action}"
