"""Creación y conexión con la base de datos SQLite de TimeFlow."""

from pathlib import Path
from functools import wraps
import os
import sqlite3
import threading


DEFAULT_DATABASE_PATH = Path(__file__).resolve().parent / "data" / "timeflow.db"
DATABASE_PATH = Path(os.environ.get("TIMEFLOW_DB_PATH", DEFAULT_DATABASE_PATH))


def _serialized(method):
    """Serializa el acceso a la conexión SQLite, también desde fragmentos."""
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapper


class Database:
    """Abre la base de datos y crea las tablas necesarias si no existen."""

    def __init__(self, database_path=DATABASE_PATH):
        self._lock = threading.RLock()
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

        # Streamlit ejecuta los fragmentos y los reruns en hilos distintos.
        # El RLock anterior mantiene las operaciones de esta conexión serializadas.
        self.connection = sqlite3.connect(
            self.database_path,
            timeout=15,
            check_same_thread=False,
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA busy_timeout = 15000")
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.create_tables()

    @_serialized
    def create_tables(self):
        """Prepara las tablas que utilizarán las siguientes etapas."""
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                activity_date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'General',
                completed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity_id INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                duration_seconds INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                FOREIGN KEY (activity_id) REFERENCES activities(id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    @_serialized
    def add_activity(self, name, activity_date, start_time, end_time, category):
        """Guarda una actividad y devuelve el identificador asignado."""
        cursor = self.connection.execute(
            """
            INSERT INTO activities (name, activity_date, start_time, end_time, category)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, activity_date, start_time, end_time, category),
        )
        self.connection.commit()
        return cursor.lastrowid

    @_serialized
    def get_activities(self):
        """Devuelve las actividades ordenadas por fecha y hora."""
        cursor = self.connection.execute(
            """
            SELECT id, name, activity_date, start_time, end_time, category, completed
            FROM activities
            ORDER BY activity_date, start_time, name
            """
        )
        return cursor.fetchall()

    @_serialized
    def get_activity(self, activity_id):
        """Busca una actividad por su identificador."""
        cursor = self.connection.execute(
            "SELECT * FROM activities WHERE id = ?",
            (activity_id,),
        )
        return cursor.fetchone()

    @_serialized
    def get_activities_for_date(self, activity_date):
        """Devuelve las actividades de una fecha concreta, ordenadas por hora."""
        cursor = self.connection.execute(
            """
            SELECT id, name, activity_date, start_time, end_time, category, completed
            FROM activities
            WHERE activity_date = ?
            ORDER BY start_time, name
            """,
            (activity_date,),
        )
        return cursor.fetchall()

    @_serialized
    def get_incomplete_activities(self):
        """Devuelve actividades que todavía no se han completado."""
        cursor = self.connection.execute(
            """
            SELECT id, name, activity_date, start_time, end_time, category, completed
            FROM activities
            WHERE completed = 0
            ORDER BY activity_date, start_time, name
            """
        )
        return cursor.fetchall()

    @_serialized
    def get_next_activity(self, current_date, current_time):
        """Busca la próxima actividad pendiente, incluyendo la que está en curso."""
        cursor = self.connection.execute(
            """
            SELECT id, name, activity_date, start_time, end_time, category
            FROM activities
            WHERE completed = 0
              AND (
                    activity_date > ?
                    OR (activity_date = ? AND end_time >= ?)
              )
            ORDER BY activity_date, start_time
            LIMIT 1
            """,
            (current_date, current_date, current_time),
        )
        return cursor.fetchone()

    @_serialized
    def delete_activity(self, activity_id):
        """Elimina una actividad por su identificador."""
        cursor = self.connection.execute(
            "DELETE FROM activities WHERE id = ?",
            (activity_id,),
        )
        self.connection.commit()
        return cursor.rowcount > 0

    @_serialized
    def create_session(self, activity_id, started_at):
        """Crea una sesión de cronómetro y devuelve su identificador."""
        open_session = self.connection.execute(
            """
            SELECT id FROM sessions
            WHERE status IN ('running', 'paused', 'active')
            LIMIT 1
            """
        ).fetchone()
        if open_session:
            raise ValueError("Ya existe una sesión activa o pendiente de recuperar.")

        cursor = self.connection.execute(
            """
            INSERT INTO sessions (activity_id, started_at, status)
            VALUES (?, ?, 'running')
            """,
            (activity_id, started_at),
        )
        self.connection.commit()
        return cursor.lastrowid

    @_serialized
    def update_session(self, session_id, duration_seconds, status):
        """Guarda el tiempo acumulado y el estado de una sesión."""
        self.connection.execute(
            """
            UPDATE sessions
            SET duration_seconds = ?, status = ?
            WHERE id = ?
            """,
            (duration_seconds, status, session_id),
        )
        self.connection.commit()

    @_serialized
    def finish_session(self, session_id, ended_at, duration_seconds, status="completed"):
        """Cierra una sesión con su duración final y estado."""
        self.connection.execute(
            """
            UPDATE sessions
            SET ended_at = ?, duration_seconds = ?, status = ?
            WHERE id = ?
            """,
            (ended_at, duration_seconds, status, session_id),
        )
        self.connection.commit()

    @_serialized
    def set_activity_completed(self, activity_id, completed=True):
        """Actualiza el indicador de actividad completada."""
        self.connection.execute(
            "UPDATE activities SET completed = ? WHERE id = ?",
            (1 if completed else 0, activity_id),
        )
        self.connection.commit()

    @_serialized
    def get_recoverable_session(self):
        """Busca una sesión activa o pausada para ofrecer su recuperación."""
        cursor = self.connection.execute(
            """
            SELECT sessions.id, sessions.activity_id, sessions.started_at,
                   sessions.duration_seconds, sessions.status, activities.name
            FROM sessions
            JOIN activities ON activities.id = sessions.activity_id
            WHERE sessions.status IN ('running', 'paused', 'active')
            ORDER BY sessions.id DESC
            LIMIT 1
            """
        )
        return cursor.fetchone()

    @_serialized
    def get_total_seconds(self):
        """Suma el tiempo registrado en todas las sesiones."""
        cursor = self.connection.execute(
            "SELECT COALESCE(SUM(duration_seconds), 0) FROM sessions"
        )
        return int(cursor.fetchone()[0])

    @_serialized
    def get_completed_activity_count(self):
        """Cuenta las actividades marcadas como completadas."""
        cursor = self.connection.execute(
            "SELECT COUNT(*) FROM activities WHERE completed = 1"
        )
        return int(cursor.fetchone()[0])

    @_serialized
    def get_activity_count_for_date(self, activity_date):
        """Cuenta las actividades programadas para una fecha."""
        cursor = self.connection.execute(
            "SELECT COUNT(*) FROM activities WHERE activity_date = ?",
            (activity_date,),
        )
        return int(cursor.fetchone()[0])

    @_serialized
    def get_activity_time_totals(self):
        """Devuelve el tiempo registrado para cada actividad."""
        cursor = self.connection.execute(
            """
            SELECT activities.id, activities.name, activities.activity_date,
                   activities.completed,
                   COALESCE(SUM(sessions.duration_seconds), 0) AS total_seconds
            FROM activities
            LEFT JOIN sessions ON sessions.activity_id = activities.id
            GROUP BY activities.id
            ORDER BY activities.activity_date DESC, activities.start_time DESC
            """
        )
        return cursor.fetchall()

    @_serialized
    def get_recent_sessions(self, limit=30):
        """Devuelve el historial de sesiones más recientes."""
        cursor = self.connection.execute(
            """
            SELECT sessions.id, activities.name, sessions.started_at,
                   sessions.ended_at, sessions.duration_seconds, sessions.status
            FROM sessions
            JOIN activities ON activities.id = sessions.activity_id
            ORDER BY sessions.id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return cursor.fetchall()

    @_serialized
    def get_setting(self, key, default=None):
        """Lee una preferencia guardada o devuelve el valor predeterminado."""
        cursor = self.connection.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,),
        )
        row = cursor.fetchone()
        return row[0] if row else default

    @_serialized
    def set_setting(self, key, value):
        """Guarda una preferencia sencilla en SQLite."""
        self.connection.execute(
            """
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, str(value)),
        )
        self.connection.commit()

    @_serialized
    def close(self):
        """Cierra la conexión al terminar la aplicación."""
        self.connection.close()
