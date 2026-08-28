"""Base de datos.

A diferencia del programa original, los tramos y las etiquetas no viven metidos
dentro del texto de la sesión: son tablas propias. Eso permite preguntar cosas
como "cuántas horas concentrado bajo #teleco los martes" con una consulta, en
vez de leer todas las filas y parsear strings.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import date, datetime, timedelta

from .config import BASE_DIR, DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY,
    started_at      TEXT NOT NULL,
    ended_at        TEXT NOT NULL,
    day             TEXT NOT NULL,
    weekday         INTEGER NOT NULL,
    total_seconds   REAL NOT NULL DEFAULT 0,
    focus_seconds   REAL NOT NULL DEFAULT 0,
    rest_seconds    REAL NOT NULL DEFAULT 0,
    away_seconds    REAL NOT NULL DEFAULT 0,
    pauses          INTEGER NOT NULL DEFAULT 0,
    blocks          INTEGER NOT NULL DEFAULT 0,
    focus_target    INTEGER NOT NULL DEFAULT 0,
    break_target    INTEGER NOT NULL DEFAULT 0,
    preset          TEXT DEFAULT '',
    title           TEXT DEFAULT '',
    notes           TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS segments (
    id           INTEGER PRIMARY KEY,
    session_id   INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    start_offset REAL NOT NULL,
    end_offset   REAL NOT NULL,
    kind         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tags (
    id        INTEGER PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE,
    uses      INTEGER NOT NULL DEFAULT 0,
    last_used TEXT
);

CREATE TABLE IF NOT EXISTS session_tags (
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    tag_id     INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (session_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_sessions_day ON sessions(day);
CREATE INDEX IF NOT EXISTS idx_segments_session ON segments(session_id);
CREATE INDEX IF NOT EXISTS idx_session_tags_tag ON session_tags(tag_id);
"""

TAG_RE = re.compile(r"#([\wÀ-ɏ][\wÀ-ɏ-]*)", re.UNICODE)

WEEKDAY_NAMES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def extract_tags(text):
    if not text:
        return []
    found = []
    for match in TAG_RE.findall(text):
        tag = match.lower()
        if tag not in found:
            found.append(tag)
    return found


class Database:
    def __init__(self, path=DB_PATH):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self._migrate()

    def _migrate(self):
        """Trae las bases viejas al esquema actual.

        El cambio: lo que se guardaba como "distracción" (`idle`) pasa a ser
        "ausente" (`away`). Son el mismo tipo de tiempo —no estabas
        concentrado— y tener dos nombres para eso sólo complicaba la lectura.
        """
        columns = {row[1] for row in
                   self.conn.execute("PRAGMA table_info(sessions)").fetchall()}
        if "idle_seconds" not in columns:
            return
        self.conn.execute(
            "UPDATE sessions SET away_seconds = COALESCE(away_seconds, 0) "
            "+ COALESCE(idle_seconds, 0)")
        self.conn.execute("UPDATE segments SET kind = 'away' WHERE kind = 'idle'")
        try:
            self.conn.execute("ALTER TABLE sessions DROP COLUMN idle_seconds")
        except sqlite3.OperationalError:
            # SQLite viejo sin DROP COLUMN: la dejamos en cero y la ignoramos.
            self.conn.execute("UPDATE sessions SET idle_seconds = 0")
        self.conn.commit()

    def close(self):
        try:
            self.conn.close()
        except sqlite3.Error:
            pass

    # ------------------------------------------------------------------ #
    # Escritura
    # ------------------------------------------------------------------ #

    def save_session(self, record):
        """`record` es el dict que devuelve `Engine.finish()` más título y notas."""
        started = record["started_at"]
        ended = record["ended_at"]
        day = started.date()
        cur = self.conn.execute(
            """
            INSERT INTO sessions (started_at, ended_at, day, weekday, total_seconds,
                                  focus_seconds, rest_seconds, away_seconds,
                                  pauses, blocks, focus_target,
                                  break_target, preset, title, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                started.isoformat(timespec="seconds"),
                ended.isoformat(timespec="seconds"),
                day.isoformat(),
                day.weekday(),
                record["total"],
                record["focus"],
                record["rest"],
                record["away"],
                record["pauses"],
                record["blocks"],
                record.get("focus_target", 0),
                record.get("break_target", 0),
                record.get("preset", ""),
                record.get("title", ""),
                record.get("notes", ""),
            ),
        )
        session_id = cur.lastrowid

        self.conn.executemany(
            "INSERT INTO segments (session_id, start_offset, end_offset, kind) "
            "VALUES (?,?,?,?)",
            [(session_id, s["start"], s["end"], s["kind"]) for s in record["segments"]],
        )
        self._link_tags(session_id, extract_tags(record.get("notes", "")))
        self.conn.commit()
        return session_id

    def _link_tags(self, session_id, tags):
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute("DELETE FROM session_tags WHERE session_id=?", (session_id,))
        for tag in tags:
            self.conn.execute(
                "INSERT INTO tags (name, uses, last_used) VALUES (?, 0, ?) "
                "ON CONFLICT(name) DO NOTHING",
                (tag, now),
            )
            self.conn.execute(
                "UPDATE tags SET uses = uses + 1, last_used = ? WHERE name = ?",
                (now, tag),
            )
            row = self.conn.execute("SELECT id FROM tags WHERE name=?", (tag,)).fetchone()
            if row:
                self.conn.execute(
                    "INSERT OR IGNORE INTO session_tags (session_id, tag_id) VALUES (?,?)",
                    (session_id, row["id"]),
                )

    def update_session(self, session_id, title=None, notes=None):
        if title is not None:
            self.conn.execute("UPDATE sessions SET title=? WHERE id=?", (title, session_id))
        if notes is not None:
            self.conn.execute("UPDATE sessions SET notes=? WHERE id=?", (notes, session_id))
            self._link_tags(session_id, extract_tags(notes))
        self.conn.commit()

    def delete_session(self, session_id):
        self.conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        self.conn.commit()

    # ------------------------------------------------------------------ #
    # Lectura
    # ------------------------------------------------------------------ #

    def sessions_on(self, day, tag=None):
        sql = ("SELECT s.* FROM sessions s "
               "{join} WHERE s.day = ? {extra} ORDER BY s.started_at")
        params = [day.isoformat() if hasattr(day, "isoformat") else day]
        if tag:
            sql = sql.format(
                join="JOIN session_tags st ON st.session_id = s.id "
                     "JOIN tags t ON t.id = st.tag_id",
                extra="AND t.name = ?")
            params.append(tag)
        else:
            sql = sql.format(join="", extra="")
        return self.conn.execute(sql, params).fetchall()

    def sessions_between(self, start, end, tag=None):
        sql = ("SELECT s.* FROM sessions s "
               "{join} WHERE s.day BETWEEN ? AND ? {extra} ORDER BY s.started_at")
        params = [str(start), str(end)]
        if tag:
            sql = sql.format(
                join="JOIN session_tags st ON st.session_id = s.id "
                     "JOIN tags t ON t.id = st.tag_id",
                extra="AND t.name = ?")
            params.append(tag)
        else:
            sql = sql.format(join="", extra="")
        return self.conn.execute(sql, params).fetchall()

    def session(self, session_id):
        return self.conn.execute("SELECT * FROM sessions WHERE id=?",
                                 (session_id,)).fetchone()

    def segments_of(self, session_id):
        return self.conn.execute(
            "SELECT start_offset, end_offset, kind FROM segments "
            "WHERE session_id=? ORDER BY start_offset", (session_id,)).fetchall()

    def tags_of(self, session_id):
        return [row["name"] for row in self.conn.execute(
            "SELECT t.name FROM tags t JOIN session_tags st ON st.tag_id = t.id "
            "WHERE st.session_id = ? ORDER BY t.name", (session_id,)).fetchall()]

    def all_tags(self, limit=200):
        return [row["name"] for row in self.conn.execute(
            "SELECT name FROM tags ORDER BY uses DESC, last_used DESC LIMIT ?",
            (limit,)).fetchall()]

    def suggest_tags(self, prefix="", limit=40):
        recent = [row["name"] for row in self.conn.execute(
            "SELECT name FROM tags ORDER BY last_used DESC LIMIT 3").fetchall()]
        ordered = recent + [t for t in self.all_tags(limit) if t not in recent]
        if prefix:
            prefix = prefix.lower()
            ordered = [t for t in ordered if t.startswith(prefix)]
        return ordered

    def focus_by_day(self, start=None, end=None):
        """{fecha: segundos concentrado}."""
        sql = "SELECT day, SUM(focus_seconds) AS focus FROM sessions"
        params = []
        if start and end:
            sql += " WHERE day BETWEEN ? AND ?"
            params = [str(start), str(end)]
        sql += " GROUP BY day"
        result = {}
        for row in self.conn.execute(sql, params).fetchall():
            try:
                result[date.fromisoformat(row["day"])] = row["focus"] or 0.0
            except ValueError:
                continue
        return result

    def day_bounds(self):
        row = self.conn.execute("SELECT MIN(day) AS a, MAX(day) AS b FROM sessions").fetchone()
        today = date.today()
        try:
            first = date.fromisoformat(row["a"])
        except (TypeError, ValueError):
            first = today - timedelta(days=30)
        try:
            last = date.fromisoformat(row["b"])
        except (TypeError, ValueError):
            last = today
        return first, last

    def count(self):
        return self.conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]

    # ------------------------------------------------------------------ #
    # Importación desde el programa viejo
    # ------------------------------------------------------------------ #

    def legacy_candidates(self):
        """Bases `productivity.db` que se puedan importar, si existen."""
        found = []
        for candidate in (
            os.path.join(os.path.dirname(BASE_DIR), "productivity.db"),
            os.path.join(os.path.dirname(BASE_DIR), "Focus Better Mejorado",
                         "productivity.db"),
            os.path.join(BASE_DIR, "productivity.db"),
        ):
            if os.path.exists(candidate) and candidate not in found:
                found.append(candidate)
        return found

    def import_legacy(self, path):
        """Trae las sesiones del formato viejo. Devuelve cuántas importó.

        Se saltea las que ya estén (mismo inicio y mismo nombre), así que se
        puede correr más de una vez sin duplicar nada.
        """
        try:
            source = sqlite3.connect(path)
            source.row_factory = sqlite3.Row
            rows = source.execute("SELECT * FROM sessions").fetchall()
        except sqlite3.Error:
            return 0

        columns = {description[0] for description in
                   source.execute("SELECT * FROM sessions LIMIT 1").description or []}
        imported = 0

        for row in rows:
            started = _parse_dt(row["start_time"])
            ended = _parse_dt(row["end_time"])
            if started is None or ended is None:
                continue

            existing = self.conn.execute(
                "SELECT id FROM sessions WHERE started_at=? AND title=?",
                (started.isoformat(timespec="seconds"), row["name"] or ""),
            ).fetchone()
            if existing:
                continue

            total = _as_float(row["total_time"])
            focus = _as_float(row["productive_time"])
            rest = _as_float(row["rest_time"]) if "rest_time" in columns else 0.0
            # El programa viejo llamaba a esto "tiempo no productivo"; acá es
            # ausente, que es la única categoría de no-concentración que queda.
            away = max(0.0, total - focus - rest)

            notes = row["annotations"] or ""
            block, description = _split_legacy_notes(notes)

            segments = []
            if "segments" in columns and row["segments"]:
                try:
                    segments = [
                        {"start": s["start"], "end": s["end"], "kind": s["kind"]}
                        for s in json.loads(row["segments"])
                    ]
                except (ValueError, KeyError, TypeError):
                    segments = []
            if not segments:
                # No hay detalle: dejamos los bloques proporcionales para que la
                # línea de tiempo muestre algo coherente.
                cursor_at = 0.0
                for value, kind in ((focus, "focus"), (rest, "rest"), (away, "away")):
                    if value > 0:
                        segments.append({"start": cursor_at, "end": cursor_at + value,
                                         "kind": kind})
                        cursor_at += value

            record = {
                "started_at": started,
                "ended_at": ended,
                "total": total,
                "focus": focus,
                "rest": rest,
                "away": away,
                "pauses": int(row["pauses"]) if "pauses" in columns and row["pauses"] else 0,
                "blocks": _blocks_from_legacy(block),
                "focus_target": 0,
                "break_target": 0,
                "preset": "importado",
                "title": row["name"] or "Sesión importada",
                "notes": description,
                "segments": segments,
            }
            self.save_session(record)
            imported += 1

        source.close()
        return imported


def _as_float(value):
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _parse_dt(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(value, fmt)
        except (ValueError, TypeError):
            continue
    return None


def _split_legacy_notes(text):
    """El formato viejo metía el resumen del pomodoro adentro de las anotaciones."""
    if not text:
        return "", ""
    if text.startswith("POMODORO"):
        parts = text.split("\n\n", 1)
        return parts[0].strip(), (parts[1].strip() if len(parts) > 1 else "")
    return "", text.strip()


def _blocks_from_legacy(block):
    match = re.search(r"(?:Períodos|Bloques) de concentración:\s*(\d+)", block or "")
    return int(match.group(1)) if match else 0
