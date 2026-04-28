"""Google Calendar integration."""
import os
import re
import pickle
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import pytz

TOKEN_PATH = Path(__file__).parent.parent.parent / "gmail_token.pickle"
TIMEZONE = "America/Indiana/Indianapolis"


def get_calendar_service():
    """Get authenticated Google Calendar service."""
    try:
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        if not TOKEN_PATH.exists():
            return None

        with open(TOKEN_PATH, 'rb') as token:
            creds = pickle.load(token)

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_PATH, 'wb') as token:
                pickle.dump(creds, token)

        if not creds or not creds.valid:
            return None

        return build('calendar', 'v3', credentials=creds)
    except Exception as e:
        print(f"[CALENDAR] Service error: {e}")
        return None


def handle_calendar_request(timeframe: str = "today", query: str = "",
                             action: str = "list", title: str = "",
                             start_time: str = "", duration_minutes: int = 60,
                             event_id: str = "", description: str = "",
                             attendees: str = "") -> str:
    """Handle all calendar requests."""
    if action == "create":
        if start_time:
            return create_calendar_event(title, start_time, duration_minutes,
                                          description, attendees)
        else:
            # Natural language creation
            text = title or timeframe
            return create_event_from_text(text)

    if action == "delete":
        return delete_calendar_event(event_id)

    service = get_calendar_service()
    if not service:
        if not os.getenv("GOOGLE_CLIENT_ID"):
            return "Google Calendar not connected. OAuth credentials not configured."
        return "Google Calendar not connected. Visit http://localhost:8000/auth/google to connect."

    try:
        return _list_events(service, timeframe, query)
    except Exception as e:
        return f"Calendar error: {e}"


def _list_events(service, timeframe: str, query: str = "") -> str:
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)

    if timeframe == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
    elif timeframe == "tomorrow":
        start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
    elif timeframe == "this_week":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)
    else:
        try:
            start = tz.localize(datetime.strptime(timeframe, "%Y-%m-%d"))
            end = start + timedelta(days=1)
        except ValueError:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)

    kwargs = dict(
        calendarId='primary',
        timeMin=start.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,
        orderBy='startTime',
        maxResults=20,
    )
    if query:
        kwargs['q'] = query

    events_result = service.events().list(**kwargs).execute()
    events = events_result.get('items', [])

    if not events:
        return f"No events found for {timeframe}."

    summaries = []
    for event in events:
        start_val = event['start'].get('dateTime', event['start'].get('date'))
        if 'T' in start_val:
            dt = datetime.fromisoformat(start_val.replace('Z', '+00:00')).astimezone(tz)
            time_str = dt.strftime("%I:%M %p")
        else:
            time_str = "All day"
        title = event.get('summary', 'Untitled event')
        event_id = event.get('id', '')
        summaries.append(f"{time_str}: {title} (id: {event_id[:8]}...)")

    return f"Events for {timeframe}:\n" + "\n".join(summaries)


def create_event_from_text(text: str) -> str:
    """Create a calendar event from natural language like 'Meeting with John tomorrow at 2pm'."""
    service = get_calendar_service()
    if not service:
        return "Calendar not connected. Visit http://localhost:8000/auth/google to connect."

    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)

    # Day parsing
    if "tomorrow" in text.lower():
        base = now + timedelta(days=1)
    elif "next week" in text.lower():
        base = now + timedelta(days=7)
    else:
        base = now + timedelta(hours=1)

    # Time parsing
    time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', text, re.IGNORECASE)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        period = (time_match.group(3) or '').lower()
        if period == 'pm' and hour < 12:
            hour += 12
        elif period == 'am' and hour == 12:
            hour = 0
        start_dt = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    else:
        start_dt = base.replace(second=0, microsecond=0)

    # Duration
    dur_match = re.search(r'(\d+)\s*hour', text, re.IGNORECASE)
    duration = int(dur_match.group(1)) * 60 if dur_match else 60
    end_dt = start_dt + timedelta(minutes=duration)

    # Title — strip time/day words
    title = re.sub(r'\b(tomorrow|today|next week|at \d[\d:]*\s*(am|pm)?|\d+ hours?)\b', '',
                   text, flags=re.IGNORECASE).strip()
    title = title or "Meeting"

    try:
        event = {
            'summary': title,
            'description': text,
            'start': {'dateTime': start_dt.isoformat(), 'timeZone': TIMEZONE},
            'end': {'dateTime': end_dt.isoformat(), 'timeZone': TIMEZONE},
        }
        created = service.events().insert(calendarId='primary', body=event).execute()
        return (
            f"Added '{title}' to your calendar on "
            f"{start_dt.strftime('%B %d at %I:%M %p')}."
        )
    except Exception as e:
        return f"Could not create event: {e}"


def create_calendar_event(title: str, start_time: str, duration_minutes: int = 60,
                           description: str = "", attendees: str = "") -> str:
    """Create an event with explicit parameters."""
    service = get_calendar_service()
    if not service:
        return "Calendar not connected."

    try:
        tz = pytz.timezone(TIMEZONE)
        start_dt = datetime.fromisoformat(start_time)
        if start_dt.tzinfo is None:
            start_dt = tz.localize(start_dt)
        end_dt = start_dt + timedelta(minutes=duration_minutes)

        event = {
            'summary': title,
            'start': {'dateTime': start_dt.isoformat(), 'timeZone': TIMEZONE},
            'end': {'dateTime': end_dt.isoformat(), 'timeZone': TIMEZONE},
        }
        if description:
            event['description'] = description
        if attendees:
            event['attendees'] = [{'email': a.strip()} for a in attendees.split(',')]

        service.events().insert(calendarId='primary', body=event).execute()
        return f"Added '{title}' to your calendar at {start_dt.strftime('%I:%M %p on %B %d')}."
    except Exception as e:
        return f"Calendar error creating event: {e}"


def delete_calendar_event(event_id: str) -> str:
    """Delete a calendar event by ID."""
    if not event_id:
        return "No event ID provided."

    service = get_calendar_service()
    if not service:
        return "Calendar not connected."

    try:
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        return f"Event deleted."
    except Exception as e:
        return f"Could not delete event: {e}"


def get_events_for_briefing() -> List[Dict]:
    """Get today's events for morning briefing."""
    service = get_calendar_service()
    if not service:
        return []
    try:
        tz = pytz.timezone(TIMEZONE)
        now = datetime.now(tz)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        events_result = service.events().list(
            calendarId='primary',
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy='startTime',
            maxResults=10,
        ).execute()
        return events_result.get('items', [])
    except Exception:
        return []
