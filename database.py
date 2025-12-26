import os
import libsql_experimental as libsql
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
import pytz

# Load environment variables
load_dotenv()

# Turso DB configuration
DATABASE_URL = os.getenv("DATABASE_URL")
DATABASE_TOKEN = os.getenv("DATABASE_TOKEN")

# Connection instance
_connection = None


def get_connection():
    """Get database connection to Turso."""
    global _connection
    if _connection is None:
        if not DATABASE_URL or not DATABASE_TOKEN:
            raise ValueError("DATABASE_URL and DATABASE_TOKEN must be set in environment variables")
        _connection = libsql.connect(DATABASE_URL, auth_token=DATABASE_TOKEN)
    return _connection


def init_db() -> None:
    """Initialize database tables with full schema."""
    conn = get_connection()
    
    # Registered users table (opt-in system)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS registered_users (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            timezone TEXT DEFAULT 'UTC'
        )
    """)
    
    # Responses table with full standup data
    conn.execute("""
        CREATE TABLE IF NOT EXISTS responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            username TEXT NOT NULL,
            question_yesterday TEXT,
            question_today TEXT,
            blockers TEXT,
            confidence_mood INTEGER,
            standup_date DATE NOT NULL,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            edited_at TIMESTAMP,
            is_late INTEGER DEFAULT 0,
            response_date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Settings table with timezone and summary channel
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            collection_start_time TEXT DEFAULT '09:00',
            collection_end_time TEXT DEFAULT '17:00',
            timezone TEXT DEFAULT 'UTC',
            summary_channel_id TEXT,
            reminder_enabled INTEGER DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Insert default settings if not exists
    conn.execute("""
        INSERT OR IGNORE INTO settings (id, collection_start_time, collection_end_time, timezone)
        VALUES (1, '09:00', '17:00', 'UTC')
    """)
    
    # Partial responses table (for in-progress standups)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS partial_responses (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            question_yesterday TEXT,
            question_today TEXT,
            blockers TEXT,
            confidence_mood INTEGER,
            standup_date DATE NOT NULL,
            current_step INTEGER DEFAULT 0,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    print("✅ Database schema initialized")


# ============================================
# User Registration Functions
# ============================================

def register_user(user_id: str, username: str) -> bool:
    """Register a user for standups. Returns True if newly registered."""
    conn = get_connection()
    
    # Check if already registered
    cursor = conn.execute(
        "SELECT is_active FROM registered_users WHERE user_id = ?",
        (user_id,)
    )
    row = cursor.fetchone()
    
    if row:
        if row[0] == 1:
            return False  # Already active
        # Reactivate
        conn.execute(
            "UPDATE registered_users SET is_active = 1, username = ? WHERE user_id = ?",
            (username, user_id)
        )
    else:
        conn.execute(
            "INSERT INTO registered_users (user_id, username) VALUES (?, ?)",
            (user_id, username)
        )
    
    conn.commit()
    return True


def unregister_user(user_id: str) -> bool:
    """Unregister a user from standups. Returns True if was registered."""
    conn = get_connection()
    
    cursor = conn.execute(
        "SELECT is_active FROM registered_users WHERE user_id = ?",
        (user_id,)
    )
    row = cursor.fetchone()
    
    if not row or row[0] == 0:
        return False  # Not registered or already inactive
    
    conn.execute(
        "UPDATE registered_users SET is_active = 0 WHERE user_id = ?",
        (user_id,)
    )
    conn.commit()
    return True


def get_registered_users() -> List[Dict[str, Any]]:
    """Get all active registered users."""
    conn = get_connection()
    
    cursor = conn.execute(
        "SELECT user_id, username, registered_at, timezone FROM registered_users WHERE is_active = 1"
    )
    
    rows = cursor.fetchall()
    return [
        {"user_id": row[0], "username": row[1], "registered_at": row[2], "timezone": row[3] or "UTC"}
        for row in rows
    ]


def set_user_timezone(user_id: str, timezone: str) -> bool:
    """Set the timezone for a specific user."""
    conn = get_connection()
    
    # Verify timezone is valid
    try:
        pytz.timezone(timezone)
    except pytz.UnknownTimeZoneError:
        return False
        
    conn.execute(
        "UPDATE registered_users SET timezone = ? WHERE user_id = ?",
        (timezone, user_id)
    )
    conn.commit()
    return True


def get_user_timezone(user_id: str) -> str:
    """Get the timezone for a specific user, falling back to global setting."""
    conn = get_connection()
    
    cursor = conn.execute(
        "SELECT timezone FROM registered_users WHERE user_id = ?",
        (user_id,)
    )
    row = cursor.fetchone()
    
    if row and row[0]:
        return row[0]
    
    # Fallback to global setting
    return get_settings()["timezone"]


def is_user_registered(user_id: str) -> bool:
    """Check if a user is registered and active."""
    conn = get_connection()
    
    cursor = conn.execute(
        "SELECT is_active FROM registered_users WHERE user_id = ?",
        (user_id,)
    )
    row = cursor.fetchone()
    return row is not None and row[0] == 1


def get_registered_user_count() -> int:
    """Get count of active registered users."""
    conn = get_connection()
    cursor = conn.execute(
        "SELECT COUNT(*) FROM registered_users WHERE is_active = 1"
    )
    return cursor.fetchone()[0]


# ============================================
# Standup Date Logic
# ============================================

def get_standup_date(timezone_str: str = "UTC") -> str:
    """
    Calculate the logical standup date.
    If collection window spans midnight (e.g., 22:00-02:00),
    responses after midnight still count for "yesterday's" standup date.
    """
    settings = get_settings()
    tz = pytz.timezone(timezone_str)
    now = datetime.now(tz)
    
    start_hour = int(settings["start_time"].split(":")[0])
    end_hour = int(settings["end_time"].split(":")[0])
    
    # If end time is before start time, window spans midnight
    if end_hour < start_hour:
        # If current hour is between midnight and end time, use yesterday's date
        if now.hour < end_hour:
            return (now.date() - timedelta(days=1)).isoformat()
    
    return now.date().isoformat()


# ============================================
# Response Functions
# ============================================

def save_response(
    user_id: str,
    username: str,
    question_yesterday: str,
    question_today: str,
    blockers: Optional[str] = None,
    confidence_mood: Optional[int] = None,
    is_late: bool = False
) -> None:
    """Save a complete standup response."""
    conn = get_connection()
    settings = get_settings()
    standup_date = get_standup_date(settings["timezone"])
    
    # Check if response already exists for this date
    cursor = conn.execute(
        "SELECT id FROM responses WHERE user_id = ? AND standup_date = ?",
        (user_id, standup_date)
    )
    existing = cursor.fetchone()
    
    if existing:
        # Update existing
        conn.execute("""
            UPDATE responses 
            SET question_yesterday = ?, question_today = ?, blockers = ?, 
                confidence_mood = ?, edited_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND standup_date = ?
        """, (question_yesterday, question_today, blockers, confidence_mood, user_id, standup_date))
    else:
        # Insert new
        conn.execute("""
            INSERT INTO responses (user_id, username, question_yesterday, question_today, 
                                   blockers, confidence_mood, standup_date, is_late,
                                   response_date, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (user_id, username, question_yesterday, question_today, blockers, 
              confidence_mood, standup_date, 1 if is_late else 0, date.today().isoformat()))
    
    conn.commit()
    
    # Clean up partial response
    conn.execute("DELETE FROM partial_responses WHERE user_id = ?", (user_id,))
    conn.commit()


def update_response_field(user_id: str, standup_date: str, field: str, value: Any) -> bool:
    """Update a specific field of a response. Returns True if updated."""
    allowed_fields = ["question_yesterday", "question_today", "blockers", "confidence_mood"]
    if field not in allowed_fields:
        return False
    
    conn = get_connection()
    
    cursor = conn.execute(
        f"SELECT id FROM responses WHERE user_id = ? AND standup_date = ?",
        (user_id, standup_date)
    )
    if not cursor.fetchone():
        return False
    
    conn.execute(f"""
        UPDATE responses 
        SET {field} = ?, edited_at = CURRENT_TIMESTAMP
        WHERE user_id = ? AND standup_date = ?
    """, (value, user_id, standup_date))
    conn.commit()
    return True


def get_user_response(user_id: str, standup_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Get a user's response for a specific date."""
    if standup_date is None:
        settings = get_settings()
        standup_date = get_standup_date(settings["timezone"])
    
    conn = get_connection()
    cursor = conn.execute("""
        SELECT user_id, username, question_yesterday, question_today, blockers,
               confidence_mood, standup_date, submitted_at, edited_at, is_late
        FROM responses WHERE user_id = ? AND standup_date = ?
    """, (user_id, standup_date))
    
    row = cursor.fetchone()
    if not row:
        return None
    
    return {
        "user_id": row[0],
        "username": row[1],
        "question_yesterday": row[2],
        "question_today": row[3],
        "blockers": row[4],
        "confidence_mood": row[5],
        "standup_date": row[6],
        "submitted_at": row[7],
        "edited_at": row[8],
        "is_late": bool(row[9])
    }


def get_responses_for_date(target_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get all responses for a specific date (default: today's standup date)."""
    if target_date is None:
        settings = get_settings()
        target_date = get_standup_date(settings["timezone"])
    
    conn = get_connection()
    
    cursor = conn.execute("""
        SELECT user_id, username, question_yesterday, question_today, blockers, 
               confidence_mood, submitted_at, edited_at, is_late
        FROM responses
        WHERE standup_date = ?
        ORDER BY submitted_at ASC
    """, (target_date,))
    
    rows = cursor.fetchall()
    responses = []
    for row in rows:
        responses.append({
            "user_id": row[0],
            "username": row[1],
            "question_yesterday": row[2],
            "question_today": row[3],
            "blockers": row[4],
            "confidence_mood": row[5],
            "submitted_at": row[6],
            "edited_at": row[7],
            "is_late": bool(row[8])
        })
    
    return responses


def has_responded_today(user_id: str) -> bool:
    """Check if a user has already responded for today's standup."""
    settings = get_settings()
    standup_date = get_standup_date(settings["timezone"])
    
    conn = get_connection()
    cursor = conn.execute(
        "SELECT COUNT(*) FROM responses WHERE user_id = ? AND standup_date = ?",
        (user_id, standup_date)
    )
    return cursor.fetchone()[0] > 0


def get_non_responders(standup_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get registered users who haven't responded for a date."""
    if standup_date is None:
        settings = get_settings()
        standup_date = get_standup_date(settings["timezone"])
    
    conn = get_connection()
    
    cursor = conn.execute("""
        SELECT ru.user_id, ru.username
        FROM registered_users ru
        LEFT JOIN responses r ON ru.user_id = r.user_id AND r.standup_date = ?
        WHERE ru.is_active = 1 AND r.id IS NULL
    """, (standup_date,))
    
    rows = cursor.fetchall()
    return [{"user_id": row[0], "username": row[1]} for row in rows]


def get_response_stats(standup_date: Optional[str] = None) -> Dict[str, Any]:
    """Get statistics for a standup date."""
    if standup_date is None:
        settings = get_settings()
        standup_date = get_standup_date(settings["timezone"])
    
    registered = get_registered_users()
    responses = get_responses_for_date(standup_date)
    non_responders = get_non_responders(standup_date)
    
    blocked_users = [r for r in responses if r["blockers"] and r["blockers"].lower() != "none"]
    late_responses = [r for r in responses if r["is_late"]]
    
    return {
        "standup_date": standup_date,
        "registered_count": len(registered),
        "responded_count": len(responses),
        "missing_count": len(non_responders),
        "blocked_count": len(blocked_users),
        "late_count": len(late_responses),
        "non_responders": non_responders,
        "blocked_users": blocked_users
    }


# ============================================
# Partial Response Functions (In-Progress)
# ============================================

def save_partial_response(
    user_id: str,
    username: str,
    step: int,
    question_yesterday: Optional[str] = None,
    question_today: Optional[str] = None,
    blockers: Optional[str] = None,
    confidence_mood: Optional[int] = None
) -> None:
    """Save an in-progress standup response."""
    conn = get_connection()
    settings = get_settings()
    standup_date = get_standup_date(settings["timezone"])
    
    # Check if partial exists
    cursor = conn.execute(
        "SELECT user_id FROM partial_responses WHERE user_id = ?",
        (user_id,)
    )
    exists = cursor.fetchone()
    
    if exists:
        conn.execute("""
            UPDATE partial_responses 
            SET question_yesterday = COALESCE(?, question_yesterday),
                question_today = COALESCE(?, question_today),
                blockers = COALESCE(?, blockers),
                confidence_mood = COALESCE(?, confidence_mood),
                current_step = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (question_yesterday, question_today, blockers, confidence_mood, step, user_id))
    else:
        conn.execute("""
            INSERT INTO partial_responses 
            (user_id, username, question_yesterday, question_today, blockers, 
             confidence_mood, standup_date, current_step)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, username, question_yesterday, question_today, blockers,
              confidence_mood, standup_date, step))
    
    conn.commit()


def get_partial_response(user_id: str) -> Optional[Dict[str, Any]]:
    """Get an in-progress response for a user."""
    conn = get_connection()
    settings = get_settings()
    standup_date = get_standup_date(settings["timezone"])
    
    cursor = conn.execute("""
        SELECT question_yesterday, question_today, blockers, confidence_mood, current_step
        FROM partial_responses 
        WHERE user_id = ? AND standup_date = ?
    """, (user_id, standup_date))
    
    row = cursor.fetchone()
    if not row:
        return None
    
    return {
        "question_yesterday": row[0],
        "question_today": row[1],
        "blockers": row[2],
        "confidence_mood": row[3],
        "current_step": row[4]
    }


def delete_partial_response(user_id: str) -> None:
    """Delete a partial response."""
    conn = get_connection()
    conn.execute("DELETE FROM partial_responses WHERE user_id = ?", (user_id,))
    conn.commit()


# ============================================
# Settings Functions
# ============================================

def get_settings() -> Dict[str, Any]:
    """Get all settings including timezone and summary channel."""
    conn = get_connection()
    
    cursor = conn.execute("""
        SELECT collection_start_time, collection_end_time, timezone, 
               summary_channel_id, reminder_enabled 
        FROM settings WHERE id = 1
    """)
    row = cursor.fetchone()
    
    if row:
        return {
            "start_time": row[0],
            "end_time": row[1],
            "timezone": row[2] or "UTC",
            "summary_channel_id": row[3],
            "reminder_enabled": bool(row[4]) if row[4] is not None else True
        }
    return {
        "start_time": "09:00", 
        "end_time": "17:00", 
        "timezone": "UTC",
        "summary_channel_id": None,
        "reminder_enabled": True
    }


def set_settings(start_time: str, end_time: str, timezone: Optional[str] = None) -> None:
    """Update collection time settings."""
    conn = get_connection()
    
    if timezone:
        conn.execute("""
            UPDATE settings 
            SET collection_start_time = ?, collection_end_time = ?, timezone = ?, 
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
        """, (start_time, end_time, timezone))
    else:
        conn.execute("""
            UPDATE settings 
            SET collection_start_time = ?, collection_end_time = ?, 
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
        """, (start_time, end_time))
    
    conn.commit()


def set_timezone(timezone: str) -> None:
    """Update only the timezone setting."""
    conn = get_connection()
    
    conn.execute("""
        UPDATE settings 
        SET timezone = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = 1
    """, (timezone,))
    
    conn.commit()


def set_summary_channel(channel_id: str) -> None:
    """Set the channel for posting summaries."""
    conn = get_connection()
    
    conn.execute("""
        UPDATE settings 
        SET summary_channel_id = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = 1
    """, (channel_id,))
    
    conn.commit()


def set_reminder_enabled(enabled: bool) -> None:
    """Enable or disable reminders."""
    conn = get_connection()
    
    conn.execute("""
        UPDATE settings 
        SET reminder_enabled = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = 1
    """, (1 if enabled else 0,))
    
    conn.commit()


def is_within_collection_window() -> bool:
    """Check if current time is within the collection window."""
    settings = get_settings()
    tz = pytz.timezone(settings["timezone"])
    now = datetime.now(tz)
    current_minutes = now.hour * 60 + now.minute
    
    start_parts = settings["start_time"].split(":")
    end_parts = settings["end_time"].split(":")
    start_minutes = int(start_parts[0]) * 60 + int(start_parts[1])
    end_minutes = int(end_parts[0]) * 60 + int(end_parts[1])
    
    # Handle window spanning midnight
    if end_minutes < start_minutes:
        return current_minutes >= start_minutes or current_minutes < end_minutes
    else:
        return start_minutes <= current_minutes < end_minutes
