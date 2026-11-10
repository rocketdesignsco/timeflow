"""Interfaz web de TimeFlow creada con Streamlit.

Ejecuta la aplicación con: streamlit run main.py
"""

from datetime import datetime, time
from zoneinfo import ZoneInfo
import os
import sqlite3

import streamlit as st

from agenda import AgendaManager
from alarms import AlarmManager
from database import Database
from timer import TimerManager


st.set_page_config(
    page_title="TimeFlow | Tu tiempo, en equilibrio",
    page_icon="⏳",
    layout="wide",
    initial_sidebar_state="expanded",
)

COLORS = {
    "ink": "#1c2c25",
    "muted": "#718078",
    "green": "#5e9a72",
    "dark": "#14251f",
    "surface": "#ffffff",
    "soft": "#e7f1e8",
    "line": "#e4eae4",
}
TIMEZONE = ZoneInfo(os.environ.get("TIMEFLOW_TIMEZONE", "America/Bogota"))


def local_now():
    """Devuelve la hora en la zona horaria configurada para la app."""
    return datetime.now(TIMEZONE)


def apply_styles():
    """Aplica una identidad visual uniforme a los componentes Streamlit."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&display=swap');
        html, body, [class*="css"], [data-testid="stAppViewContainer"] { font-family: 'DM Sans', sans-serif; }
        .stApp { background: #f4f6f2; color: #1c2c25; }
        [data-testid="stHeader"] { background: rgba(244,246,242,.92); }
        [data-testid="stSidebar"] { background: #14251f; }
        [data-testid="stSidebar"] * { color: #f4f7f4; }
        [data-testid="stSidebar"] [data-testid="stRadio"] label { color: #dce6df; }
        [data-testid="stSidebar"] hr { border-color: #34483d; }
        h1, h2, h3 { color: #1c2c25; letter-spacing: -.035em; }
        .eyebrow { color: #5e9a72; font-size: .72rem; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; margin-bottom: .35rem; }
        .subtle { color: #718078; }
        div[data-testid="stMetric"] { background: #fff; border: 1px solid #e4eae4; border-radius: 16px; padding: 15px 18px; }
        div[data-testid="stMetricLabel"] p { color: #718078; font-size: .76rem; font-weight: 700; }
        div[data-testid="stMetricValue"] { color: #1c2c25; font-weight: 750; }
        .hero { background: #14251f; color: white; border-radius: 18px; padding: 22px 25px; margin: 0 0 1rem; }
        .hero .kicker { color: #a9d5b4; font-size: .68rem; letter-spacing: .12em; font-weight: 800; }
        .hero h2 { color: white; margin: .3rem 0; font-size: 1.55rem; }
        .hero p { color: #c1cec6; margin: 0; font-size: .9rem; }
        div.stButton > button, div.stFormSubmitButton > button { border-radius: 10px; font-weight: 700; }
        div.stButton > button[kind="primary"], div.stFormSubmitButton > button[kind="primary"] { background: #5e9a72; border-color: #5e9a72; }
        div[data-testid="stForm"] { background: #fff; border: 1px solid #e4eae4; border-radius: 16px; padding: 18px; }
        div[data-testid="stDataFrame"] { background: white; border: 1px solid #e4eae4; border-radius: 14px; overflow: hidden; }
        .timer { color: #5e9a72; font-size: clamp(3.2rem, 9vw, 5.8rem); font-weight: 800; line-height: 1.1; letter-spacing: -.06em; text-align: center; font-variant-numeric: tabular-nums; padding: .35rem 0 .8rem; }
        .timer-status { color: #718078; text-align: center; font-size: .85rem; font-weight: 700; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def get_services():
    """Abre una conexión por sesión de navegador y crea sus servicios."""
    if "database" not in st.session_state:
        st.session_state.database = Database()
        st.session_state.agenda_manager = AgendaManager(st.session_state.database)
        st.session_state.timer_manager = TimerManager(st.session_state.database)
        st.session_state.alarm_manager = AlarmManager(st.session_state.database)
        st.session_state.pending_notices = []

        recoverable = st.session_state.database.get_recoverable_session()
        if recoverable is not None:
            st.session_state.timer_manager.recover(recoverable)
    return (
        st.session_state.database,
        st.session_state.agenda_manager,
        st.session_state.timer_manager,
        st.session_state.alarm_manager,
    )


def format_duration(total_seconds, include_seconds=False):
    """Convierte segundos a HH:MM o HH:MM:SS."""
    total_seconds = max(0, int(total_seconds or 0))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if include_seconds:
        return f"{hours:02}:{minutes:02}:{seconds:02}"
    return f"{hours:02}:{minutes:02}"


def show_header(eyebrow, title, subtitle):
    st.markdown(f'<p class="eyebrow">{eyebrow}</p>', unsafe_allow_html=True)
    st.title(title)
    st.caption(subtitle)


@st.fragment(run_every="10s")
def check_alarms_fragment(alarm_manager, timer_manager):
    """Revisa avisos periódicamente y conserva las notificaciones visibles."""
    if timer_manager.has_session and timer_manager.is_running:
        timer_manager.checkpoint()
    events = alarm_manager.get_due_events(local_now(), timer_manager.has_session)
    notices = st.session_state.pending_notices
    for activity in events["reminders"]:
        notices.append({
            "type": "reminder", "id": activity["id"],
            "text": f'{activity["name"]} comienza a las {activity["start_time"]}.',
        })
    for activity in events["start_candidates"]:
        notices.append({
            "type": "start", "id": activity["id"],
            "text": f'{activity["name"]} ya está en horario. ¿Iniciar el cronómetro?',
        })
    for activity in events["ending_activities"]:
        notices.append({
            "type": "end", "id": activity["id"],
            "text": f'El horario de {activity["name"]} terminó a las {activity["end_time"]}.',
        })

    for index, notice in enumerate(st.session_state.pending_notices):
        if notice["type"] == "reminder":
            st.info(f'⏰ {notice["text"]}')
            if st.button("Descartar aviso", key=f'dismiss_reminder_{notice["id"]}'):
                st.session_state.pending_notices.pop(index)
                st.rerun()
        elif notice["type"] == "start":
            st.warning(notice["text"])
            col_start, col_later = st.columns([1, 5])
            if col_start.button("Iniciar actividad", type="primary", key=f'start_notice_{notice["id"]}'):
                try:
                    timer_manager.start(notice["id"])
                    st.session_state.pending_notices.pop(index)
                    st.success("Cronómetro iniciado. Abre Temporizador para ver el tiempo en curso.")
                    st.rerun()
                except (ValueError, sqlite3.Error) as error:
                    st.error(str(error))
            if col_later.button("Ahora no", key=f'later_notice_{notice["id"]}'):
                st.session_state.pending_notices.pop(index)
                st.rerun()
        else:
            st.success(f'✓ {notice["text"]}')
            if st.button("Cerrar aviso", key=f'dismiss_end_{notice["id"]}'):
                st.session_state.pending_notices.pop(index)
                st.rerun()


def render_home(database, timer_manager):
    now = local_now()
    today = now.date().isoformat()
    next_activity = database.get_next_activity(today, now.strftime("%H:%M"))
    show_header("Tu espacio personal", "Tu tiempo, en equilibrio.", "Organiza tus compromisos y disfruta cada avance.")

    left, right = st.columns([3, 1])
    with left:
        st.markdown(
            '<div class="hero"><div class="kicker">UN MOMENTO PARA TI</div>'
            '<h2>Avanza a tu ritmo.</h2><p>Planifica lo importante y deja espacio para concentrarte.</p></div>',
            unsafe_allow_html=True,
        )
    with right:
        live_clock()

    metrics = st.columns(3)
    metrics[0].metric("EN TU AGENDA HOY", database.get_activity_count_for_date(today))
    metrics[1].metric("TIEMPO ENFOCADO", format_duration(database.get_total_seconds()))
    metrics[2].metric("TAREAS COMPLETADAS", database.get_completed_activity_count())

    col_today, col_next = st.columns([1.4, 1])
    with col_today:
        st.subheader("Lo que tienes hoy")
        activities = database.get_activities_for_date(today)
        if activities:
            st.dataframe(
                [{
                    "Hora": f'{row["start_time"]}–{row["end_time"]}',
                    "Actividad": row["name"],
                    "Categoría": row["category"],
                    "Estado": "Completada" if row["completed"] else "Pendiente",
                } for row in activities],
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info("Tu día está despejado. Agrega una actividad a tu agenda cuando quieras.")
    with col_next:
        st.subheader("Siguiente en tu agenda")
        if next_activity:
            st.markdown(f'### {next_activity["name"]}')
            st.caption(f'{next_activity["activity_date"]} · {next_activity["start_time"]}–{next_activity["end_time"]}')
            st.caption(f'Categoría: {next_activity["category"]}')
        else:
            st.info("No hay actividades próximas. Un buen momento para planear lo que sigue.")
        if timer_manager.has_session:
            st.success(f"Sesión {('en curso' if timer_manager.is_running else 'en pausa')}: {timer_manager.activity_name}")


@st.fragment(run_every="1s")
def live_clock():
    """Mantiene actualizado el reloj sin volver a dibujar toda la página."""
    st.metric("HORA LOCAL", local_now().strftime("%H:%M:%S"))


def render_agenda(database, agenda_manager, timer_manager):
    show_header("Planea con intención", "Tu agenda", "Organiza tus compromisos y mantén tu día en perspectiva.")
    with st.form("new_activity", clear_on_submit=True):
        st.subheader("Agregar actividad")
        c1, c2 = st.columns([2, 1])
        name = c1.text_input("Nombre de la actividad", placeholder="Ej. Preparar presentación")
        category = c2.selectbox("Categoría", AgendaManager.CATEGORIES)
        c3, c4, c5, c6 = st.columns(4)
        activity_date = c3.date_input("Fecha", value=local_now().date())
        start_time = c4.time_input("Hora de inicio", value=time(9, 0), step=300)
        end_time = c5.time_input("Hora de fin", value=time(10, 0), step=300)
        submitted = c6.form_submit_button("＋ Agregar", type="primary", use_container_width=True)
        if submitted:
            try:
                agenda_manager.create_activity(
                    name,
                    activity_date.isoformat(),
                    start_time.strftime("%H:%M"),
                    end_time.strftime("%H:%M"),
                    category,
                )
                st.success("Actividad guardada en la agenda.")
            except ValueError as error:
                st.error(str(error))
            except sqlite3.Error as error:
                st.error(f"No se pudo guardar la actividad: {error}")

    st.divider()
    activities = agenda_manager.get_activities()
    st.subheader(f"Actividades programadas · {len(activities)}")
    if activities:
        st.dataframe(
            [{
                "Actividad": row["name"],
                "Fecha": row["activity_date"],
                "Horario": f'{row["start_time"]}–{row["end_time"]}',
                "Categoría": row["category"],
                "Estado": "Completada" if row["completed"] else "Pendiente",
            } for row in activities],
            hide_index=True,
            use_container_width=True,
        )
        options = {
            f'{row["activity_date"]} · {row["start_time"]} · {row["name"]}': row["id"]
            for row in activities
        }
        selected_label = st.selectbox("Selecciona una actividad para gestionar", list(options))
        selected_id = options[selected_label]
        selected = database.get_activity(selected_id)
        action_cols = st.columns([1, 1, 3])
        if action_cols[0].button("✓ Marcar completada", disabled=bool(selected["completed"]), use_container_width=True):
            if timer_manager.has_session and timer_manager.activity_id == selected_id:
                st.warning("Finaliza la sesión en curso antes de completar esta actividad.")
            else:
                try:
                    agenda_manager.complete_activity(selected_id)
                    st.success("Actividad completada.")
                    st.rerun()
                except (ValueError, sqlite3.Error) as error:
                    st.error(str(error))
        confirm_delete = action_cols[1].checkbox("Confirmar eliminación", key="confirm_delete_activity")
        if action_cols[2].button("Eliminar seleccionada", disabled=not confirm_delete, use_container_width=True):
            if timer_manager.has_session and timer_manager.activity_id == selected_id:
                st.warning("Finaliza la sesión en curso antes de eliminar esta actividad.")
            else:
                agenda_manager.delete_activity(selected_id)
                st.success("Actividad eliminada junto con sus sesiones asociadas.")
                st.rerun()
    else:
        st.info("Aún no hay actividades. Usa el formulario para planear la primera.")


@st.fragment(run_every="1s")
def timer_fragment(timer_manager, agenda_manager, database):
    """Actualiza el cronómetro dentro de un fragmento Streamlit."""
    if timer_manager.has_session:
        st.markdown(
            f'<p class="timer-status">{("En curso" if timer_manager.is_running else "En pausa")} · {timer_manager.activity_name}</p>',
            unsafe_allow_html=True,
        )
        st.markdown(f'<div class="timer">{format_duration(timer_manager.elapsed_seconds(), True)}</div>', unsafe_allow_html=True)
        if st.session_state.timer_manager.is_running:
            pause_col, finish_col = st.columns(2)
            if pause_col.button("Ⅱ Pausar", use_container_width=True):
                timer_manager.pause()
                st.rerun()
            if finish_col.button("✓ Finalizar sesión", type="primary", use_container_width=True):
                timer_manager.finish()
                st.success("Sesión finalizada y tiempo guardado.")
                st.rerun()
        else:
            resume_col, finish_col = st.columns(2)
            if resume_col.button("▶ Reanudar", type="primary", use_container_width=True):
                timer_manager.resume()
                st.rerun()
            if finish_col.button("✓ Finalizar sesión", use_container_width=True):
                timer_manager.finish()
                st.success("Sesión finalizada y tiempo guardado.")
                st.rerun()
    else:
        choices = agenda_manager.get_activities()
        pending = [row for row in choices if not row["completed"]]
        if pending:
            labels = {
                f'{row["activity_date"]} · {row["start_time"]} · {row["name"]}': row["id"]
                for row in pending
            }
            selected = st.selectbox("Actividad", list(labels), key="timer_activity_choice")
            st.markdown('<p class="timer-status">Elige una actividad y empieza cuando estés listo.</p>', unsafe_allow_html=True)
            st.markdown('<div class="timer">00:00:00</div>', unsafe_allow_html=True)
            if st.button("▶ Iniciar enfoque", type="primary", use_container_width=True):
                try:
                    timer_manager.start(labels[selected])
                    st.rerun()
                except (ValueError, sqlite3.Error) as error:
                    st.error(str(error))
        else:
            st.info("No hay actividades pendientes. Agrega una en Agenda para iniciar una sesión.")

def render_timer(timer_manager, agenda_manager, database):
    show_header("Un paso a la vez", "Tiempo de enfoque", "Registra el tiempo que dedicas a tus actividades.")
    st.caption("La sesión se guarda automáticamente para poder recuperarla si se interrumpe la conexión.")
    timer_fragment(timer_manager, agenda_manager, database)


def render_statistics(database):
    show_header("Mira lo que has logrado", "Tu resumen", "Una vista clara de tus actividades y del tiempo que has invertido.")
    cards = st.columns(3)
    cards[0].metric("TIEMPO REGISTRADO", format_duration(database.get_total_seconds(), True))
    cards[1].metric("ACTIVIDADES COMPLETADAS", database.get_completed_activity_count())
    sessions = database.get_recent_sessions(limit=100)
    cards[2].metric("SESIONES REGISTRADAS", len(sessions))

    st.subheader("Tiempo por actividad")
    activities = database.get_activity_time_totals()
    if activities:
        st.dataframe([{
            "Actividad": row["name"],
            "Fecha": row["activity_date"],
            "Tiempo": format_duration(row["total_seconds"], True),
            "Estado": "Completada" if row["completed"] else "Pendiente",
        } for row in activities], hide_index=True, use_container_width=True)
    else:
        st.info("Tus actividades aparecerán aquí cuando las agregues.")

    st.subheader("Historial de sesiones")
    if sessions:
        status_names = {
            "running": "En curso", "active": "En curso", "paused": "En pausa",
            "completed": "Finalizada", "interrupted": "Interrumpida",
        }
        st.dataframe([{
            "Actividad": row["name"],
            "Inicio": row["started_at"].replace("T", " ")[:16],
            "Duración": format_duration(row["duration_seconds"], True),
            "Estado": status_names.get(row["status"], row["status"]),
        } for row in sessions], hide_index=True, use_container_width=True)
    else:
        st.info("Aún no registras sesiones de enfoque.")


def main():
    apply_styles()
    database, agenda_manager, timer_manager, alarm_manager = get_services()

    with st.sidebar:
        st.markdown("# ⏳ TimeFlow")
        st.caption("TU TIEMPO, EN EQUILIBRIO")
        st.divider()
        section = st.radio(
            "NAVEGACIÓN",
            ["Inicio", "Agenda", "Temporizador", "Estadísticas"],
            key="navigation",
            label_visibility="collapsed",
        )
        st.divider()
        st.caption("●  Guardado en la base de datos local del servidor")

    check_alarms_fragment(alarm_manager, timer_manager)

    if section == "Inicio":
        render_home(database, timer_manager)
    elif section == "Agenda":
        render_agenda(database, agenda_manager, timer_manager)
    elif section == "Temporizador":
        render_timer(timer_manager, agenda_manager, database)
    else:
        render_statistics(database)


if __name__ == "__main__":
    main()
