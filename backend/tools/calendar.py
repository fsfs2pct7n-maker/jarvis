"""Google Calendar integration."""
import os
import pickle
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import pytz

TOKEN_PATH = Path(__file__).parent.parent.parent / "gmail_token.pickle"  # Shared token
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

        if not creds or not creds.valid:
            return None

        return build('calendar', 'v3', credentials=creds)
    except Exception as e:
        print(f"[CALENDAR] Service error: {e}")
        return None


def handle_calendar_request(timeframe: str = "today", query: str = "") -> str:
    """Handle calendar requests."""
    service = get_calendar_service()

    if not service:
        if not os.getenv("GOOGLE_CLIENT_ID"):
            return "Google Calendar not connected. OAuth credentials not configured yet."
        return "Google Calendar not connected. Visit http://localhost:8000/auth/google to connect."

    try:
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
            # Try to parse as date
            try:
                start = tz.localize(datetime.strptime(timeframe, "%Y-%m-%d"))
                end = start + timedelta(days=1)
            except ValueError:
                start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                end = start + timedelta(days=1)

        events_result = service.events().list(
            calendarId='primary',
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy='startTime',
            q=query if query else None,
            maxResults=20
        ).execute()

        events = events_result.get('items', [])

        if not events:
            return f"No events found for {timeframe}."

        summaries = []
        for event in events:
            start_time = event['start'].get('dateTime', event['start'].get('date'))
            if 'T' in start_time:
                dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                dt = dt.astimezone(tz)
                time_str = dt.strftime("%I:%M %p")
            else:
                time_str = "All day"

            summaries.append(f"{time_str}: {event.get('summary', 'Untitled event')}")

        return f"Events for {timeframe}:\n" + "\n".join(summaries)

    except Exception as e:
        return f"Calendar error: {e}"


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
            maxResults=10
        ).execute()

        return events_result.get('items', [])
    except Exception:
        return []


def create_calendar_event(title: str, start_time: str, duration_minutes: int = 60) -> str:
    """Create a calendar event."""
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
            'end': {'dateTime': end_dt.isoformat(), 'timeZone': TIMEZONE}
        }

        service.events().insert(calendarId='primary', body=event).execute()
        return f"Added '{title}' to your calendar at {start_dt.strftime('%I:%M %p on %B %d')}."

    except Exception as e:
        return f"Calendar error creating event: {e}"
