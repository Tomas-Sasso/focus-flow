"""Análisis sobre las sesiones guardadas.

Devuelve estructuras planas listas para dibujar; ninguna función de acá sabe
nada de Tk.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

WEEKDAY_SHORT = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
MONTHS_SHORT = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago",
                "Sep", "Oct", "Nov", "Dic"]


def _as_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def totals(rows):
    """Suma las cuatro categorías de una lista de sesiones."""
    result = {"total": 0.0, "focus": 0.0, "rest": 0.0, "away": 0.0,
              "sessions": len(rows), "pauses": 0, "blocks": 0}
    for row in rows:
        result["total"] += row["total_seconds"] or 0.0
        result["focus"] += row["focus_seconds"] or 0.0
        result["rest"] += row["rest_seconds"] or 0.0
        result["away"] += row["away_seconds"] or 0.0
        result["pauses"] += row["pauses"] or 0
        result["blocks"] += row["blocks"] or 0
    # En pantalla se muestran dos categorías; el detalle queda en la base.
    result["not_focus"] = result["rest"] + result["away"]
    result["productivity"] = (
        result["focus"] / result["total"] * 100.0) if result["total"] > 0 else 0.0
    return result


def display_split(summary):
    """{concentrado, no concentrado} a partir de un resumen completo."""
    return {"focus": summary["focus"],
            "other": summary.get("not_focus", summary["rest"] + summary["away"])}


def display_percentages(summary):
    """Lo mismo, ya formateado como porcentajes para la leyenda."""
    total = summary["total"]
    if total <= 0:
        return {"focus": "0%", "other": "0%"}
    split = display_split(summary)
    return {key: f"{value / total * 100:.0f}%" for key, value in split.items()}


def by_day(rows):
    """{fecha: segundos concentrado}."""
    result = {}
    for row in rows:
        day = _as_date(row["day"])
        if day is not None:
            result[day] = result.get(day, 0.0) + (row["focus_seconds"] or 0.0)
    return result


def by_weekday(rows):
    """Concentración total y promedio por día de la semana."""
    totals_ = [0.0] * 7
    days_seen = [set() for _ in range(7)]
    for row in rows:
        day = _as_date(row["day"])
        if day is None:
            continue
        index = day.weekday()
        totals_[index] += row["focus_seconds"] or 0.0
        days_seen[index].add(day)
    averages = [totals_[i] / len(days_seen[i]) if days_seen[i] else 0.0 for i in range(7)]
    return totals_, averages


def by_hour(rows, db=None):
    """Reparto de la concentración por hora del día.

    Usa los tramos reales cuando están: una sesión de 20:00 a 23:00 no reparte
    su concentración en partes iguales, y el detalle importa para saber a qué
    hora rendís mejor.
    """
    hours = [0.0] * 24
    for row in rows:
        try:
            started = datetime.fromisoformat(row["started_at"])
        except (TypeError, ValueError):
            continue

        spans = []
        if db is not None:
            spans = [(s["start_offset"], s["end_offset"])
                     for s in db.segments_of(row["id"]) if s["kind"] == "focus"]
        if not spans:
            focus = row["focus_seconds"] or 0.0
            if focus <= 0:
                continue
            spans = [(0.0, focus)]

        for start_offset, end_offset in spans:
            begin = started + timedelta(seconds=start_offset)
            end = started + timedelta(seconds=end_offset)
            cursor_at = begin
            while cursor_at < end:
                next_hour = (cursor_at.replace(minute=0, second=0, microsecond=0)
                             + timedelta(hours=1))
                chunk_end = min(end, next_hour)
                hours[cursor_at.hour] += (chunk_end - cursor_at).total_seconds()
                cursor_at = chunk_end
    return hours


def streak(focus_by_day, today=None, minimum=60):
    """Días seguidos con al menos `minimum` segundos de concentración."""
    today = today or date.today()
    active = {day for day, seconds in focus_by_day.items() if seconds >= minimum}
    if not active:
        return 0
    day = today
    if today not in active:
        # Si todavía no arrancaste hoy, la racha de ayer sigue viva.
        if (today - timedelta(days=1)) not in active:
            return 0
        day = today - timedelta(days=1)
    count = 0
    while day in active:
        count += 1
        day -= timedelta(days=1)
    return count


def best_streak(focus_by_day, minimum=60):
    active = sorted(day for day, seconds in focus_by_day.items() if seconds >= minimum)
    if not active:
        return 0
    best = run = 1
    for previous, current in zip(active, active[1:]):
        run = run + 1 if (current - previous).days == 1 else 1
        best = max(best, run)
    return best


def records(rows, focus_map):
    """Los máximos personales, para la pantalla de análisis."""
    best_session = max(rows, key=lambda r: r["focus_seconds"] or 0.0, default=None)
    best_day = max(focus_map.items(), key=lambda item: item[1], default=(None, 0.0))
    best_rate = None
    for row in rows:
        if (row["total_seconds"] or 0) >= 600:  # ignoramos sesiones muy cortas
            rate = (row["focus_seconds"] or 0) / row["total_seconds"] * 100
            if best_rate is None or rate > best_rate[1]:
                best_rate = (row, rate)
    return {
        "best_session": best_session,
        "best_day": best_day,
        "best_rate": best_rate,
    }


def tag_ranking(db, rows, limit=8):
    """[(tag, segundos concentrado, % de concentración, sesiones)]."""
    buckets = {}
    for row in rows:
        for tag in db.tags_of(row["id"]):
            entry = buckets.setdefault(tag, [0.0, 0.0, 0])
            entry[0] += row["focus_seconds"] or 0.0
            entry[1] += row["total_seconds"] or 0.0
            entry[2] += 1
    ranked = sorted(buckets.items(), key=lambda item: item[1][0], reverse=True)
    return [
        (tag, focus, (focus / total * 100.0) if total > 0 else 0.0, count)
        for tag, (focus, total, count) in ranked[:limit]
    ]


def heatmap_cells(focus_map, weeks=26, today=None):
    """Celdas (columna, fila) -> segundos, estilo mapa de contribuciones."""
    today = today or date.today()
    end = today + timedelta(days=6 - today.weekday())   # domingo de esta semana
    start = end - timedelta(weeks=weeks * 1) + timedelta(days=1)
    start -= timedelta(days=start.weekday())            # lunes

    cells, labels = {}, []
    day = start
    column = 0
    last_month = None
    while day <= end:
        row = day.weekday()
        if day <= today:
            cells[(column, row)] = focus_map.get(day, 0.0)
        if row == 0 and day.month != last_month:
            # Sólo etiquetamos si hay lugar: si no, "Feb" y "Mar" se pisan.
            if not labels or column - labels[-1][0] >= 3:
                labels.append((column, MONTHS_SHORT[day.month - 1]))
            last_month = day.month
        day += timedelta(days=1)
        if day.weekday() == 0:
            column += 1
    return cells, column + 1, labels, start


def daily_series(rows, start, end):
    """Agrupa por día, semana o mes según el largo del rango.

    Devuelve (valores en horas, etiquetas, título) para el gráfico de barras.
    """
    focus_map = by_day(rows)
    if end < start:
        start, end = end, start
    span = (end - start).days + 1

    if span <= 45:
        buckets = [start + timedelta(days=i) for i in range(span)]
        values = [focus_map.get(day, 0.0) for day in buckets]
        labels = [day.strftime("%d/%m") for day in buckets]
        title = "Concentración por día"
    elif span <= 210:
        first = start - timedelta(days=start.weekday())
        values, labels = [], []
        week = first
        while week <= end:
            following = week + timedelta(days=7)
            values.append(sum(v for d, v in focus_map.items() if week <= d < following))
            labels.append(week.strftime("%d/%m"))
            week = following
        title = "Concentración por semana"
    else:
        values, labels = [], []
        month = date(start.year, start.month, 1)
        while month <= end:
            following = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
            values.append(sum(v for d, v in focus_map.items() if month <= d < following))
            labels.append(month.strftime("%m/%y"))
            month = following
        title = "Concentración por mes"

    step = max(1, len(labels) // 9)
    labels = [label if i % step == 0 else "" for i, label in enumerate(labels)]
    return [v / 3600.0 for v in values], labels, title


def to_csv(db, rows):
    """Exporta las sesiones a texto CSV."""
    lines = ["fecha,dia,inicio,fin,total_min,concentracion_min,descanso_min,"
             "ausente_min,productividad,cortes,bloques,titulo,tags"]
    for row in rows:
        tags = " ".join(f"#{t}" for t in db.tags_of(row["id"]))
        total = row["total_seconds"] or 0.0
        productivity = (row["focus_seconds"] or 0) / total * 100 if total else 0
        title = (row["title"] or "").replace('"', "'")
        lines.append(
            f'{row["day"]},{WEEKDAY_SHORT[row["weekday"]]},'
            f'{row["started_at"][11:16]},{row["ended_at"][11:16]},'
            f'{total / 60:.1f},{(row["focus_seconds"] or 0) / 60:.1f},'
            f'{(row["rest_seconds"] or 0) / 60:.1f},'
            f'{(row["away_seconds"] or 0) / 60:.1f},{productivity:.0f},'
            f'{row["pauses"] or 0},{row["blocks"] or 0},"{title}","{tags}"'
        )
    return "\n".join(lines)
