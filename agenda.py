"""Validación y operaciones básicas para las actividades de la agenda."""

from datetime import date, datetime


class AgendaManager:
    """Coordina la validación de actividades y su almacenamiento."""

    CATEGORIES = ("General", "Estudio", "Trabajo", "Personal", "Salud", "Otro")

    def __init__(self, database):
        self.database = database

    def create_activity(self, name, activity_date, start_time, end_time, category):
        """Valida los campos y guarda una actividad en la base de datos."""
        name = name.strip()
        if not name:
            raise ValueError("Escribe un nombre para la actividad.")

        activity_date = activity_date.strip()
        try:
            parsed_date = date.fromisoformat(activity_date)
        except ValueError as error:
            raise ValueError("La fecha debe tener el formato AAAA-MM-DD.") from error

        if parsed_date.isoformat() != activity_date:
            raise ValueError("La fecha debe tener el formato AAAA-MM-DD.")

        try:
            start = datetime.strptime(start_time.strip(), "%H:%M").time()
            end = datetime.strptime(end_time.strip(), "%H:%M").time()
        except ValueError as error:
            raise ValueError("Las horas deben tener el formato HH:MM, por ejemplo 09:30.") from error

        if start >= end:
            raise ValueError("La hora final debe ser posterior a la hora de inicio.")

        category = category.strip() or "General"
        return self.database.add_activity(
            name,
            parsed_date.isoformat(),
            start.strftime("%H:%M"),
            end.strftime("%H:%M"),
            category,
        )

    def get_activities(self):
        """Entrega las actividades en orden cronológico."""
        return self.database.get_activities()

    def delete_activity(self, activity_id):
        """Elimina la actividad seleccionada."""
        return self.database.delete_activity(activity_id)

    def complete_activity(self, activity_id):
        """Marca una actividad como completada."""
        activity = self.database.get_activity(activity_id)
        if activity is None:
            raise ValueError("La actividad ya no existe.")
        if activity["completed"]:
            raise ValueError("La actividad ya está completada.")
        self.database.set_activity_completed(activity_id, True)
