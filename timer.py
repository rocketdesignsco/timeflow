"""Lógica del cronómetro y recuperación de sesiones de TimeFlow."""

import time
from datetime import datetime
from zoneinfo import ZoneInfo
import os


TIMEZONE = ZoneInfo(os.environ.get("TIMEFLOW_TIMEZONE", "America/Bogota"))


def local_datetime():
    """Fecha y hora local para guardar marcas temporales en la base de datos."""
    return datetime.now(TIMEZONE)


class TimerManager:
    """Controla como máximo una sesión de cronómetro a la vez."""

    def __init__(self, database):
        self.database = database
        self.session_id = None
        self.activity_id = None
        self.activity_name = None
        self.saved_seconds = 0
        self.running_since = None

    @property
    def has_session(self):
        """Indica si hay una sesión activa o pausada."""
        return self.session_id is not None

    @property
    def is_running(self):
        """Indica si el cronómetro está contando ahora mismo."""
        return self.running_since is not None

    def elapsed_seconds(self):
        """Calcula el tiempo acumulado usando un reloj monotónico."""
        elapsed = self.saved_seconds
        if self.running_since is not None:
            elapsed += time.monotonic() - self.running_since
        return max(0, int(elapsed))

    def start(self, activity_id):
        """Inicia una sesión nueva para una actividad pendiente."""
        if self.has_session:
            raise ValueError("Primero finaliza o recupera la sesión actual.")

        activity = self.database.get_activity(activity_id)
        if activity is None:
            raise ValueError("La actividad seleccionada ya no existe.")
        if activity["completed"]:
            raise ValueError("La actividad ya está completada.")

        started_at = local_datetime().isoformat(timespec="seconds")
        session_id = self.database.create_session(activity_id, started_at)
        self.session_id = session_id
        self.activity_id = activity_id
        self.activity_name = activity["name"]
        self.saved_seconds = 0
        self.running_since = time.monotonic()
        return session_id

    def pause(self):
        """Pausa la sesión y guarda el tiempo acumulado."""
        if not self.has_session or not self.is_running:
            return

        self.saved_seconds = self.elapsed_seconds()
        self.running_since = None
        self.database.update_session(self.session_id, self.saved_seconds, "paused")

    def resume(self):
        """Reanuda una sesión pausada."""
        if not self.has_session or self.is_running:
            return

        self.running_since = time.monotonic()
        self.database.update_session(self.session_id, self.saved_seconds, "running")

    def checkpoint(self):
        """Guarda un punto de recuperación sin detener el cronómetro."""
        if not self.has_session:
            return

        elapsed = self.elapsed_seconds()
        self.database.update_session(
            self.session_id,
            elapsed,
            "running" if self.is_running else "paused",
        )

    def finish(self):
        """Finaliza y guarda la sesión sin cambiar el estado de la actividad."""
        if not self.has_session:
            return 0

        elapsed = self.elapsed_seconds()
        ended_at = local_datetime().isoformat(timespec="seconds")
        self.database.finish_session(
            self.session_id,
            ended_at,
            elapsed,
            status="completed",
        )
        self._clear_session()
        return elapsed

    def recover(self, session):
        """Carga una sesión guardada y la deja pausada hasta que el usuario reanude."""
        if self.has_session:
            raise ValueError("Ya hay una sesión cargada.")

        self.session_id = session["id"]
        self.activity_id = session["activity_id"]
        self.activity_name = session["name"]
        self.saved_seconds = int(session["duration_seconds"] or 0)
        self.running_since = None
        self.database.update_session(self.session_id, self.saved_seconds, "paused")

    def reject_recovery(self, session):
        """Cierra como interrumpida una sesión que el usuario no quiere recuperar."""
        self.database.finish_session(
            session["id"],
            local_datetime().isoformat(timespec="seconds"),
            int(session["duration_seconds"] or 0),
            status="interrupted",
        )

    def save_for_recovery(self):
        """Guarda una sesión pausada antes de cerrar la aplicación."""
        if not self.has_session:
            return

        self.saved_seconds = self.elapsed_seconds()
        self.running_since = None
        self.database.update_session(self.session_id, self.saved_seconds, "paused")

    def _clear_session(self):
        """Limpia los datos de la sesión que acaba de finalizar."""
        self.session_id = None
        self.activity_id = None
        self.activity_name = None
        self.saved_seconds = 0
        self.running_since = None
