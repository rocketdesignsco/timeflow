"""Recordatorios de inicio y fin para las actividades de hoy."""

from datetime import datetime, time, timedelta


class AlarmManager:
    """Busca avisos pendientes y guarda cuáles ya se mostraron."""

    DEFAULT_REMINDER_MINUTES = 5

    def __init__(self, database):
        self.database = database
        if self.database.get_setting("reminder_minutes") is None:
            self.database.set_setting(
                "reminder_minutes", self.DEFAULT_REMINDER_MINUTES
            )

    def get_due_events(self, now, timer_has_session):
        """Devuelve avisos de aproximación, inicio pendiente y fin de horario."""
        # Conserva la hora local al construir los horarios de actividad sin zona.
        if now.tzinfo is not None:
            now = now.replace(tzinfo=None)
        activity_date = now.date().isoformat()
        activities = self.database.get_activities_for_date(activity_date)
        reminder_minutes = self._reminder_minutes()

        reminders = []
        start_candidates = []
        ending_activities = []

        for activity in activities:
            start_at = datetime.combine(
                now.date(), time.fromisoformat(activity["start_time"])
            )
            end_at = datetime.combine(
                now.date(), time.fromisoformat(activity["end_time"])
            )

            reminder_key = f"alarm_reminder_{activity['id']}"
            reminder_at = start_at - timedelta(minutes=reminder_minutes)
            if (
                not activity["completed"]
                and reminder_at <= now < start_at
                and not self._was_shown(reminder_key)
            ):
                reminders.append(activity)
                self.database.set_setting(reminder_key, "shown")

            start_key = f"alarm_start_{activity['id']}"
            if (
                not timer_has_session
                and not activity["completed"]
                and start_at <= now
                and now < end_at
                and not self._was_shown(start_key)
            ):
                start_candidates.append(activity)
                self.database.set_setting(start_key, "shown")

            end_key = f"alarm_end_{activity['id']}"
            if end_at <= now and not self._was_shown(end_key):
                ending_activities.append(activity)
                self.database.set_setting(end_key, "shown")

        return {
            "reminders": reminders,
            "start_candidates": start_candidates,
            "ending_activities": ending_activities,
        }

    def _was_shown(self, key):
        """Comprueba si el recordatorio ya fue presentado."""
        return self.database.get_setting(key) == "shown"

    def _reminder_minutes(self):
        """Lee la anticipación guardada y usa cinco minutos si no es válida."""
        value = self.database.get_setting(
            "reminder_minutes", self.DEFAULT_REMINDER_MINUTES
        )
        try:
            return max(0, min(120, int(value)))
        except (TypeError, ValueError):
            return self.DEFAULT_REMINDER_MINUTES
