"""
NutriTracker Database Layer
===========================
SQLite database with all tables for users, meals, goals, and chat history.
All data stays local. No encryption needed since it never leaves the machine.
"""

import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime, date
from contextlib import contextmanager

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "nutritracker.db"


def get_db_path():
    """Return the database path, creating parent dirs if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return str(DB_PATH)


@contextmanager
def get_connection():
    """Context manager for database connections with WAL mode."""
    conn = sqlite3.connect(get_db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create all tables if they don't exist."""
    with get_connection() as conn:
        conn.executescript("""
            -- Users / profiles
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                avatar_emoji TEXT DEFAULT '🍎',
                pin_hash TEXT,
                age INTEGER,
                sex TEXT CHECK(sex IN ('male', 'female', 'other')),
                height_cm REAL,
                weight_kg REAL,
                body_fat_pct REAL,
                body_fat_method TEXT DEFAULT 'visual',
                neck_cm REAL,
                waist_cm REAL,
                hip_cm REAL,
                activity_level TEXT DEFAULT 'moderate'
                    CHECK(activity_level IN ('sedentary', 'light', 'moderate', 'active', 'very_active')),
                goal_type TEXT DEFAULT 'maintain'
                    CHECK(goal_type IN ('lose_fat', 'gain_muscle', 'maintain', 'recomp')),
                goal_weight_kg REAL,
                goal_timeline_weeks INTEGER DEFAULT 12,
                goal_aggression TEXT DEFAULT 'moderate'
                    CHECK(goal_aggression IN ('conservative', 'moderate', 'aggressive')),
                calorie_target INTEGER,
                protein_g INTEGER,
                carbs_g INTEGER,
                fat_g INTEGER,
                ai_provider TEXT DEFAULT 'google',
                ai_model TEXT,
                ai_api_key TEXT,
                vision_provider TEXT,
                vision_model TEXT,
                vision_api_key TEXT,
                body_fat_navy REAL,
                unit_system TEXT DEFAULT 'metric'
                    CHECK(unit_system IN ('metric', 'imperial')),
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                onboarding_complete INTEGER DEFAULT 0
            );

            -- Daily weight / check-in log
            CREATE TABLE IF NOT EXISTS daily_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                log_date TEXT NOT NULL,
                weight_kg REAL,
                body_fat_pct REAL,
                energy_level INTEGER CHECK(energy_level BETWEEN 1 AND 5),
                sleep_hours REAL,
                water_ml INTEGER,
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(user_id, log_date)
            );

            -- Meals
            CREATE TABLE IF NOT EXISTS meals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                meal_date TEXT NOT NULL,
                meal_type TEXT DEFAULT 'meal'
                    CHECK(meal_type IN ('breakfast', 'lunch', 'dinner', 'snack', 'meal')),
                description TEXT,
                photo_path TEXT,
                ai_analysis TEXT,
                ai_confidence REAL,
                calories INTEGER,
                protein_g REAL,
                carbs_g REAL,
                fat_g REAL,
                fiber_g REAL,
                user_adjusted INTEGER DEFAULT 0,
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            -- Individual food items within a meal
            CREATE TABLE IF NOT EXISTS meal_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meal_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                quantity TEXT,
                calories INTEGER,
                protein_g REAL,
                carbs_g REAL,
                fat_g REAL,
                fiber_g REAL,
                confidence REAL,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (meal_id) REFERENCES meals(id) ON DELETE CASCADE
            );

            -- Chat conversations
            CREATE TABLE IF NOT EXISTS chat_conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT DEFAULT 'New Chat',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            -- Chat history with AI
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                conversation_id INTEGER,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                content TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (conversation_id) REFERENCES chat_conversations(id) ON DELETE CASCADE
            );

            -- Persistent AI memory (facts the coach remembers across all chats)
            CREATE TABLE IF NOT EXISTS chat_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                fact TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            -- User lifestyle preferences (dietary, cooking, dining habits)
            CREATE TABLE IF NOT EXISTS user_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                dietary_restrictions TEXT DEFAULT '[]',
                allergies TEXT DEFAULT '[]',
                cuisine_preferences TEXT DEFAULT '[]',
                cooking_frequency TEXT DEFAULT 'few_times_week',
                dining_out_frequency TEXT DEFAULT 'weekly',
                fast_food_frequency TEXT DEFAULT 'rarely',
                travel_frequency TEXT DEFAULT 'rarely',
                budget_preference TEXT DEFAULT 'moderate',
                favorite_foods TEXT DEFAULT '[]',
                disliked_foods TEXT DEFAULT '[]',
                notes TEXT DEFAULT '',
                nutritionix_app_id TEXT,
                nutritionix_app_key TEXT,
                usda_api_key TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            -- App settings (server-level)
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        # ─── Migrations (safe to re-run) ──────────────────────────────────────
        _migrate_add_columns(conn)


def _migrate_add_columns(conn):
    """Add columns that may be missing from older database versions."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    migrations = [
        ('body_fat_navy', 'ALTER TABLE users ADD COLUMN body_fat_navy REAL'),
        ('coach_name', "ALTER TABLE users ADD COLUMN coach_name TEXT DEFAULT 'Coach'"),
    ]
    for col, sql in migrations:
        if col not in existing:
            conn.execute(sql)

    # Add conversation_id to chat_messages if missing
    msg_cols = {row[1] for row in conn.execute("PRAGMA table_info(chat_messages)").fetchall()}
    if 'conversation_id' not in msg_cols:
        conn.execute('ALTER TABLE chat_messages ADD COLUMN conversation_id INTEGER')

    # Create chat_conversations table if missing
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    if 'chat_conversations' not in tables:
        conn.execute("""CREATE TABLE IF NOT EXISTS chat_conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT DEFAULT 'New Chat',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )""")
    # Add weighin_frequency to user_preferences if missing
    if 'user_preferences' in tables:
        pref_cols = {row[1] for row in conn.execute("PRAGMA table_info(user_preferences)").fetchall()}
        if 'weighin_frequency' not in pref_cols:
            conn.execute("ALTER TABLE user_preferences ADD COLUMN weighin_frequency TEXT DEFAULT 'weekly'")

    if 'chat_memory' not in tables:
        conn.execute("""CREATE TABLE IF NOT EXISTS chat_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            fact TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )""")


# ─── User Operations ────────────────────────────────────────────────────────

def create_user(name, avatar_emoji='🍎'):
    """Create a new user profile. Returns user ID."""
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO users (name, avatar_emoji) VALUES (?, ?)",
            (name, avatar_emoji)
        )
        return cursor.lastrowid


def get_user(user_id):
    """Get a single user by ID."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def get_all_users():
    """Get all user profiles."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name, avatar_emoji, onboarding_complete, created_at FROM users ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]


def update_user(user_id, **kwargs):
    """Update user fields. Only updates provided kwargs.
    Silently drops keys that aren't valid columns to prevent crashes."""
    if not kwargs:
        return
    # Filter to valid columns only
    with get_connection() as conn:
        valid_cols = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        kwargs = {k: v for k, v in kwargs.items() if k in valid_cols}
        if not kwargs:
            return
        kwargs['updated_at'] = datetime.now().isoformat()
        fields = ', '.join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [user_id]
        conn.execute(f"UPDATE users SET {fields} WHERE id = ?", values)


def delete_user(user_id):
    """Delete a user and all their data (cascades)."""
    with get_connection() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


# ─── User Preferences ──────────────────────────────────────────────────────

def get_user_preferences(user_id):
    """Get user lifestyle/dietary preferences."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM user_preferences WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row:
            prefs = dict(row)
            # Parse JSON arrays
            for field in ('dietary_restrictions', 'allergies', 'cuisine_preferences',
                          'favorite_foods', 'disliked_foods'):
                try:
                    prefs[field] = json.loads(prefs.get(field, '[]'))
                except (json.JSONDecodeError, TypeError):
                    prefs[field] = []
            return prefs
        return None


def upsert_user_preferences(user_id, **kwargs):
    """Create or update user preferences."""
    # Serialize lists to JSON strings
    for field in ('dietary_restrictions', 'allergies', 'cuisine_preferences',
                  'favorite_foods', 'disliked_foods'):
        if field in kwargs and isinstance(kwargs[field], list):
            kwargs[field] = json.dumps(kwargs[field])

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM user_preferences WHERE user_id = ?", (user_id,)
        ).fetchone()

        if existing:
            kwargs['updated_at'] = datetime.now().isoformat()
            fields = ', '.join(f"{k} = ?" for k in kwargs)
            values = list(kwargs.values()) + [user_id]
            conn.execute(f"UPDATE user_preferences SET {fields} WHERE user_id = ?", values)
        else:
            kwargs['user_id'] = user_id
            cols = ', '.join(kwargs.keys())
            placeholders = ', '.join('?' * len(kwargs))
            conn.execute(
                f"INSERT INTO user_preferences ({cols}) VALUES ({placeholders})",
                list(kwargs.values())
            )


# ─── Meal Operations ────────────────────────────────────────────────────────

def add_meal(user_id, meal_date, meal_type, description=None, photo_path=None,
             ai_analysis=None, ai_confidence=None, calories=0, protein_g=0,
             carbs_g=0, fat_g=0, fiber_g=0, notes=None, items=None):
    """Add a meal with optional food items. Returns meal ID."""
    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO meals (user_id, meal_date, meal_type, description, photo_path,
                             ai_analysis, ai_confidence, calories, protein_g, carbs_g,
                             fat_g, fiber_g, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, meal_date, meal_type, description, photo_path,
              ai_analysis, ai_confidence, calories, protein_g, carbs_g,
              fat_g, fiber_g, notes))
        meal_id = cursor.lastrowid

        if items:
            for item in items:
                conn.execute("""
                    INSERT INTO meal_items (meal_id, name, quantity, calories,
                                          protein_g, carbs_g, fat_g, fiber_g, confidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (meal_id, item.get('name', 'Unknown'), item.get('quantity'),
                      item.get('calories', 0), item.get('protein_g', 0),
                      item.get('carbs_g', 0), item.get('fat_g', 0),
                      item.get('fiber_g', 0), item.get('confidence')))

        return meal_id


def get_meals_for_date(user_id, meal_date):
    """Get all meals for a user on a specific date."""
    with get_connection() as conn:
        meals = conn.execute("""
            SELECT * FROM meals WHERE user_id = ? AND meal_date = ?
            ORDER BY created_at
        """, (user_id, meal_date)).fetchall()

        result = []
        for meal in meals:
            meal_dict = dict(meal)
            items = conn.execute(
                "SELECT * FROM meal_items WHERE meal_id = ?", (meal_dict['id'],)
            ).fetchall()
            meal_dict['items'] = [dict(i) for i in items]
            result.append(meal_dict)
        return result


def get_meals_range(user_id, start_date, end_date):
    """Get meals within a date range."""
    with get_connection() as conn:
        meals = conn.execute("""
            SELECT * FROM meals WHERE user_id = ? AND meal_date BETWEEN ? AND ?
            ORDER BY meal_date, created_at
        """, (user_id, start_date, end_date)).fetchall()

        result = []
        for meal in meals:
            meal_dict = dict(meal)
            items = conn.execute(
                "SELECT * FROM meal_items WHERE meal_id = ?", (meal_dict['id'],)
            ).fetchall()
            meal_dict['items'] = [dict(i) for i in items]
            result.append(meal_dict)
        return result


def update_meal(meal_id, **kwargs):
    """Update meal fields."""
    if not kwargs:
        return
    fields = ', '.join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [meal_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE meals SET {fields} WHERE id = ?", values)


def delete_meal(meal_id):
    """Delete a meal and its items (cascades)."""
    with get_connection() as conn:
        conn.execute("DELETE FROM meals WHERE id = ?", (meal_id,))


def get_meal_history(user_id, offset=0, limit=30):
    """Get meal dates with daily summaries, ordered newest first.
    Returns a list of date-grouped summaries for the history view."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT
                meal_date,
                COUNT(*) as meal_count,
                COALESCE(SUM(calories), 0) as total_calories,
                COALESCE(SUM(protein_g), 0) as total_protein,
                COALESCE(SUM(carbs_g), 0) as total_carbs,
                COALESCE(SUM(fat_g), 0) as total_fat
            FROM meals WHERE user_id = ?
            GROUP BY meal_date
            ORDER BY meal_date DESC
            LIMIT ? OFFSET ?
        """, (user_id, limit, offset)).fetchall()
        return [dict(r) for r in rows]


def get_meal_date_count(user_id):
    """Get total number of distinct dates with meals."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(DISTINCT meal_date) as count FROM meals WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        return row['count'] if row else 0


def delete_meals_by_date(user_id, meal_date):
    """Delete all meals for a user on a specific date."""
    with get_connection() as conn:
        # Delete meal items first (no cascade on meal_items FK)
        conn.execute("""
            DELETE FROM meal_items WHERE meal_id IN (
                SELECT id FROM meals WHERE user_id = ? AND meal_date = ?
            )
        """, (user_id, meal_date))
        count = conn.execute(
            "DELETE FROM meals WHERE user_id = ? AND meal_date = ?",
            (user_id, meal_date)
        ).rowcount
        return count


def delete_meals_by_range(user_id, start_date, end_date):
    """Delete all meals for a user within a date range (inclusive)."""
    with get_connection() as conn:
        conn.execute("""
            DELETE FROM meal_items WHERE meal_id IN (
                SELECT id FROM meals WHERE user_id = ? AND meal_date BETWEEN ? AND ?
            )
        """, (user_id, start_date, end_date))
        count = conn.execute(
            "DELETE FROM meals WHERE user_id = ? AND meal_date BETWEEN ? AND ?",
            (user_id, start_date, end_date)
        ).rowcount
        return count


def delete_meals_by_ids(user_id, meal_ids):
    """Delete specific meals by ID list."""
    if not meal_ids:
        return 0
    placeholders = ','.join('?' * len(meal_ids))
    with get_connection() as conn:
        conn.execute(
            f"DELETE FROM meal_items WHERE meal_id IN ({placeholders})",
            meal_ids
        )
        count = conn.execute(
            f"DELETE FROM meals WHERE user_id = ? AND id IN ({placeholders})",
            [user_id] + meal_ids
        ).rowcount
        return count


def get_meal_date_range(user_id):
    """Get the earliest and latest meal dates for a user."""
    with get_connection() as conn:
        row = conn.execute("""
            SELECT MIN(meal_date) as earliest, MAX(meal_date) as latest
            FROM meals WHERE user_id = ?
        """, (user_id,)).fetchone()
        return dict(row) if row else {'earliest': None, 'latest': None}


# ─── Daily Summary ──────────────────────────────────────────────────────────

def get_daily_totals(user_id, meal_date):
    """Get aggregated macro totals for a date."""
    with get_connection() as conn:
        row = conn.execute("""
            SELECT
                COALESCE(SUM(calories), 0) as total_calories,
                COALESCE(SUM(protein_g), 0) as total_protein,
                COALESCE(SUM(carbs_g), 0) as total_carbs,
                COALESCE(SUM(fat_g), 0) as total_fat,
                COALESCE(SUM(fiber_g), 0) as total_fiber,
                COUNT(*) as meal_count
            FROM meals WHERE user_id = ? AND meal_date = ?
        """, (user_id, meal_date)).fetchone()
        return dict(row)


def get_weekly_totals(user_id, start_date, end_date):
    """Get daily totals for a date range (for charts)."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT
                meal_date,
                COALESCE(SUM(calories), 0) as total_calories,
                COALESCE(SUM(protein_g), 0) as total_protein,
                COALESCE(SUM(carbs_g), 0) as total_carbs,
                COALESCE(SUM(fat_g), 0) as total_fat,
                COUNT(*) as meal_count
            FROM meals WHERE user_id = ? AND meal_date BETWEEN ? AND ?
            GROUP BY meal_date ORDER BY meal_date
        """, (user_id, start_date, end_date)).fetchall()
        return [dict(r) for r in rows]


# ─── Daily Log Operations ───────────────────────────────────────────────────

def upsert_daily_log(user_id, log_date, **kwargs):
    """Insert or update a daily log entry."""
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM daily_logs WHERE user_id = ? AND log_date = ?",
            (user_id, log_date)
        ).fetchone()

        if existing:
            fields = ', '.join(f"{k} = ?" for k in kwargs)
            values = list(kwargs.values()) + [existing['id']]
            conn.execute(f"UPDATE daily_logs SET {fields} WHERE id = ?", values)
            return existing['id']
        else:
            kwargs['user_id'] = user_id
            kwargs['log_date'] = log_date
            cols = ', '.join(kwargs.keys())
            placeholders = ', '.join('?' * len(kwargs))
            cursor = conn.execute(
                f"INSERT INTO daily_logs ({cols}) VALUES ({placeholders})",
                list(kwargs.values())
            )
            return cursor.lastrowid


def get_daily_log(user_id, log_date):
    """Get daily log for a specific date."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM daily_logs WHERE user_id = ? AND log_date = ?",
            (user_id, log_date)
        ).fetchone()
        return dict(row) if row else None


def get_weight_history(user_id, limit=90):
    """Get weight entries for trend charting."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT log_date, weight_kg, body_fat_pct
            FROM daily_logs WHERE user_id = ? AND weight_kg IS NOT NULL
            ORDER BY log_date DESC LIMIT ?
        """, (user_id, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]


def get_last_weighin(user_id):
    """Get the most recent weigh-in date and weight."""
    with get_connection() as conn:
        row = conn.execute("""
            SELECT log_date, weight_kg FROM daily_logs
            WHERE user_id = ? AND weight_kg IS NOT NULL
            ORDER BY log_date DESC LIMIT 1
        """, (user_id,)).fetchone()
        return dict(row) if row else None


# ─── Chat Conversations ────────────────────────────────────────────────────

def create_conversation(user_id, title='New Chat'):
    """Create a new chat conversation. Returns conversation ID."""
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO chat_conversations (user_id, title) VALUES (?, ?)",
            (user_id, title)
        )
        return cursor.lastrowid


def get_conversations(user_id, limit=50):
    """Get all conversations for a user, most recent first."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT c.id, c.title, c.created_at, c.updated_at,
                   (SELECT COUNT(*) FROM chat_messages WHERE conversation_id = c.id) as message_count,
                   (SELECT content FROM chat_messages WHERE conversation_id = c.id
                    AND role = 'user' ORDER BY created_at LIMIT 1) as first_message
            FROM chat_conversations c
            WHERE c.user_id = ?
            ORDER BY c.updated_at DESC
            LIMIT ?
        """, (user_id, limit)).fetchall()
        return [dict(r) for r in rows]


def get_conversation(conv_id):
    """Get a single conversation."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM chat_conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        return dict(row) if row else None


def update_conversation(conv_id, **kwargs):
    """Update conversation fields (title, updated_at)."""
    if not kwargs:
        return
    kwargs['updated_at'] = datetime.now().isoformat()
    fields = ', '.join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [conv_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE chat_conversations SET {fields} WHERE id = ?", values)


def delete_conversation(conv_id):
    """Delete a conversation and all its messages."""
    with get_connection() as conn:
        conn.execute("DELETE FROM chat_messages WHERE conversation_id = ?", (conv_id,))
        conn.execute("DELETE FROM chat_conversations WHERE id = ?", (conv_id,))


# ─── Chat Messages ─────────────────────────────────────────────────────────

def add_chat_message(user_id, role, content, conversation_id=None):
    """Store a chat message in a conversation."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO chat_messages (user_id, role, content, conversation_id) VALUES (?, ?, ?, ?)",
            (user_id, role, content, conversation_id)
        )
        # Update conversation timestamp
        if conversation_id:
            conn.execute(
                "UPDATE chat_conversations SET updated_at = ? WHERE id = ?",
                (datetime.now().isoformat(), conversation_id)
            )


def get_chat_history(user_id, limit=50, conversation_id=None):
    """Get chat messages for a specific conversation or all."""
    with get_connection() as conn:
        if conversation_id:
            rows = conn.execute("""
                SELECT role, content, created_at FROM chat_messages
                WHERE user_id = ? AND conversation_id = ?
                ORDER BY created_at
            """, (user_id, conversation_id)).fetchall()
        else:
            rows = conn.execute("""
                SELECT role, content, created_at FROM chat_messages
                WHERE user_id = ? ORDER BY created_at DESC LIMIT ?
            """, (user_id, limit)).fetchall()
            rows = list(reversed(rows))
        return [dict(r) for r in rows]


def clear_chat_history(user_id):
    """Clear all chat messages and conversations for a user."""
    with get_connection() as conn:
        conn.execute("DELETE FROM chat_messages WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM chat_conversations WHERE user_id = ?", (user_id,))


# ─── Chat Memory (Persistent across conversations) ──────────────────────

def get_chat_memories(user_id, limit=50):
    """Get all persistent memory facts for a user."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT id, fact, category, created_at FROM chat_memory
            WHERE user_id = ? ORDER BY created_at DESC LIMIT ?
        """, (user_id, limit)).fetchall()
        return [dict(r) for r in rows]


def add_chat_memory(user_id, fact, category='general'):
    """Add a persistent memory fact."""
    with get_connection() as conn:
        # Avoid exact duplicates
        existing = conn.execute(
            "SELECT id FROM chat_memory WHERE user_id = ? AND fact = ?",
            (user_id, fact)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO chat_memory (user_id, fact, category) VALUES (?, ?, ?)",
                (user_id, fact, category)
            )


def delete_chat_memory(memory_id):
    """Delete a specific memory fact."""
    with get_connection() as conn:
        conn.execute("DELETE FROM chat_memory WHERE id = ?", (memory_id,))


def clear_chat_memories(user_id):
    """Clear all memory facts for a user."""
    with get_connection() as conn:
        conn.execute("DELETE FROM chat_memory WHERE user_id = ?", (user_id,))


# ─── App Settings ───────────────────────────────────────────────────────────

def get_setting(key, default=None):
    """Get an app-level setting."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", (key,)
        ).fetchone()
        return row['value'] if row else default


def set_setting(key, value):
    """Set an app-level setting."""
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
            (key, str(value))
        )


def is_first_run():
    """Check if this is the first time the app is running."""
    return get_setting('app_name') is None


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at: {get_db_path()}")
