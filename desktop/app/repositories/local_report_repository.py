from __future__ import annotations

import json
import hashlib
import hmac
import os
import secrets
import sqlite3
import unicodedata
from contextlib import closing
from pathlib import Path
from typing import Any

from desktop.app.models.report import EmergencyReport


DEFAULT_CATALOGS = {
    "district": [
        "Alto Selva Alegre", "Cayma", "Cercado", "Cerro Colorado", "Characato", "Chiguata",
        "Hunter (Jacobo Hunter)", "José Luis Bustamante y Rivero", "La Joya", "Mariano Melgar",
        "Miraflores", "Mollebaya", "Paucarpata", "Pocsi", "Polobaya", "Quequeña", "Sabandía",
        "Sachaca", "San Juan de Siguas", "San Juan de Tarucani", "Santa Isabel de Siguas",
        "Santa Rita de Siguas", "Socabaya", "Tiabaya", "Uchumayo", "Vítor", "Yanahuara",
        "Yarabamba", "Yura",
    ],
    "shift_operator": [],
    "emergency_type": [
        "Accidente vehicular", "Atención prehospitalaria", "Falsa alarma", "Incendio",
        "Materiales peligrosos", "Rescate", "Otros",
    ],
    "yes_no": ["No", "Sí"],
    "codification": [],
    "unit": [],
    "firefighter": [],
    "personnel_condition": ["Asiste", "Retén"],
    "company": [],
    "police_station": [],
}


def _sort_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold()


def default_database_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "Arequipa19" / "PartesEmergencia" / "partes.sqlite3"


class LocalReportRepository:
    """Guarda partes locales pendientes de sincronización, sin claves remotas."""

    def __init__(self, database_path: Path | str | None = None) -> None:
        self.database_path = Path(database_path) if database_path else default_database_path()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS emergency_reports (
                    id TEXT PRIMARY KEY,
                    local_number TEXT NOT NULL UNIQUE,
                    occurred_at TEXT NOT NULL,
                    emergency_type TEXT NOT NULL,
                    address TEXT NOT NULL,
                    district TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    sync_status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (sync_status IN ('pending', 'synced', 'error')),
                    remote_id TEXT,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                )
            """)
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(emergency_reports)")}
            if "is_finalized" not in columns:
                connection.execute("ALTER TABLE emergency_reports ADD COLUMN is_finalized INTEGER NOT NULL DEFAULT 0")
            if "pdf_path" not in columns:
                connection.execute("ALTER TABLE emergency_reports ADD COLUMN pdf_path TEXT")
            connection.execute("CREATE INDEX IF NOT EXISTS reports_occurred_at_idx ON emergency_reports(occurred_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS reports_type_idx ON emergency_reports(emergency_type)")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS emergency_report_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_id TEXT NOT NULL REFERENCES emergency_reports(id),
                    version_number INTEGER NOT NULL CHECK (version_number > 0),
                    payload_json TEXT NOT NULL,
                    pdf_path TEXT,
                    changed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    change_reason TEXT NOT NULL,
                    UNIQUE(report_id, version_number)
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS local_number_counters (
                    report_year INTEGER PRIMARY KEY,
                    last_number INTEGER NOT NULL CHECK (last_number >= 0)
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS catalog_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    value TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    UNIQUE(category, value COLLATE NOCASE)
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS app_settings (
                    setting_key TEXT PRIMARY KEY,
                    setting_value TEXT NOT NULL
                )
            """)
            for category, values in DEFAULT_CATALOGS.items():
                connection.executemany(
                    "INSERT OR IGNORE INTO catalog_entries(category, value) VALUES (?, ?)",
                    [(category, value) for value in values],
                )

    def next_local_number(self, year: int) -> str:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT last_number FROM local_number_counters WHERE report_year = ?", (year,)
            ).fetchone()
            if row is None:
                legacy = connection.execute(
                    "SELECT MAX(CAST(substr(local_number, ?) AS INTEGER)) AS amount "
                    "FROM emergency_reports WHERE local_number LIKE ?",
                    (len(f"LOCAL-{year}-") + 1, f"LOCAL-{year}-%"),
                ).fetchone()
                sequence = int(legacy["amount"] or 0) + 1
            else:
                sequence = int(row["last_number"]) + 1
            while connection.execute(
                "SELECT 1 FROM emergency_reports WHERE local_number = ?",
                (f"LOCAL-{year}-{sequence:06d}",),
            ).fetchone():
                sequence += 1
            if row is None:
                connection.execute(
                    "INSERT INTO local_number_counters(report_year, last_number) VALUES (?, ?)",
                    (year, sequence),
                )
            else:
                connection.execute(
                    "UPDATE local_number_counters SET last_number = ? WHERE report_year = ?",
                    (sequence, year),
                )
            connection.commit()
            return f"LOCAL-{year}-{sequence:06d}"

    def local_number_exists(self, local_number: str) -> bool:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT 1 FROM emergency_reports WHERE local_number = ?", (local_number,)
            ).fetchone()
        return row is not None

    def save(self, report: EmergencyReport, pdf_path: str | None = None, finalized: bool = False) -> None:
        payload = report.to_dict()
        with closing(self._connect()) as connection, connection:
            connection.execute("""
                INSERT INTO emergency_reports
                    (id, local_number, occurred_at, emergency_type, address, district, payload_json,
                     sync_status, is_finalized, pdf_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                report.id, report.local_number, report.occurred_at, report.emergency_type,
                report.address, report.district,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")), report.sync_status,
                int(finalized), pdf_path,
            ))
            if finalized:
                connection.execute("""
                    INSERT INTO emergency_report_versions
                        (report_id, version_number, payload_json, pdf_path, change_reason)
                    VALUES (?, 1, ?, ?, 'Creación del parte')
                """, (report.id, json.dumps(payload, ensure_ascii=False, separators=(",", ":")), pdf_path))

    def search(self, query: str = "") -> list[dict[str, Any]]:
        needle = f"%{query.strip()}%"
        with closing(self._connect()) as connection, connection:
            rows = connection.execute("""
                SELECT id, local_number, occurred_at, emergency_type, address, district,
                       sync_status, is_finalized, pdf_path, payload_json
                FROM emergency_reports
                WHERE ? = '%%' OR local_number LIKE ? OR emergency_type LIKE ? OR address LIKE ? OR district LIKE ?
                ORDER BY occurred_at DESC, created_at DESC
            """, (needle, needle, needle, needle, needle)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            result.append(item)
        return result

    def get(self, report_id: str) -> EmergencyReport | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute("SELECT payload_json FROM emergency_reports WHERE id = ?", (report_id,)).fetchone()
        return EmergencyReport.from_dict(json.loads(row["payload_json"])) if row else None

    def get_report_info(self, report_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT is_finalized, pdf_path FROM emergency_reports WHERE id = ?", (report_id,)
            ).fetchone()
        return dict(row) if row else None

    def next_report_version(self, report_id: str) -> int:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT MAX(version_number) AS latest FROM emergency_report_versions WHERE report_id = ?",
                (report_id,),
            ).fetchone()
        return max(2, int(row["latest"] or 0) + 1)

    def update_finalized_report(self, report: EmergencyReport, pdf_path: str, change_reason: str) -> int:
        payload_json = json.dumps(report.to_dict(), ensure_ascii=False, separators=(",", ":"))
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT payload_json, pdf_path, is_finalized FROM emergency_reports WHERE id = ?",
                (report.id,),
            ).fetchone()
            if not current:
                raise ValueError("No se encontró el parte que se desea corregir.")
            latest = connection.execute(
                "SELECT MAX(version_number) AS latest FROM emergency_report_versions WHERE report_id = ?",
                (report.id,),
            ).fetchone()["latest"]
            if not latest:
                connection.execute("""
                    INSERT INTO emergency_report_versions
                        (report_id, version_number, payload_json, pdf_path, change_reason)
                    VALUES (?, 1, ?, ?, 'Registro previo a la primera corrección')
                """, (report.id, current["payload_json"], current["pdf_path"]))
                version_number = 2
            else:
                version_number = int(latest) + 1
            connection.execute("""
                UPDATE emergency_reports
                SET occurred_at = ?, emergency_type = ?, address = ?, district = ?, payload_json = ?,
                    pdf_path = ?, is_finalized = 1
                WHERE id = ?
            """, (report.occurred_at, report.emergency_type, report.address, report.district,
                  payload_json, pdf_path, report.id))
            connection.execute("""
                INSERT INTO emergency_report_versions
                    (report_id, version_number, payload_json, pdf_path, change_reason)
                VALUES (?, ?, ?, ?, ?)
            """, (report.id, version_number, payload_json, pdf_path, change_reason.strip() or "Corrección administrativa"))
            connection.commit()
        return version_number

    def list_report_versions(self, report_id: str) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute("""
                SELECT version_number, pdf_path, changed_at, change_reason
                FROM emergency_report_versions WHERE report_id = ? ORDER BY version_number DESC
            """, (report_id,)).fetchall()
        return [dict(row) for row in rows]

    def list_catalog(self, category: str, active_only: bool = True) -> list[dict[str, Any]]:
        where_active = "AND is_active = 1" if active_only else ""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"SELECT id, value, is_active FROM catalog_entries WHERE category = ? {where_active}",
                (category,),
            ).fetchall()
        result = [dict(row) for row in rows]
        return sorted(result, key=lambda item: _sort_text(item["value"]))

    def get_app_setting(self, key: str, default: str = "") -> str:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT setting_value FROM app_settings WHERE setting_key = ?", (key,)
            ).fetchone()
        return str(row["setting_value"]) if row else default

    def set_app_setting(self, key: str, value: str) -> None:
        self.set_app_settings({key: value})

    def set_app_settings(self, settings: dict[str, str]) -> None:
        with closing(self._connect()) as connection, connection:
            connection.executemany(
                "INSERT INTO app_settings(setting_key, setting_value) VALUES (?, ?) "
                "ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value",
                list(settings.items()),
            )

    def add_catalog_item(self, category: str, value: str) -> int:
        normalized = value.strip()
        if not normalized:
            raise ValueError("El valor no puede estar vacío.")
        with closing(self._connect()) as connection, connection:
            existing = connection.execute(
                "SELECT id FROM catalog_entries WHERE category = ? AND value = ? COLLATE NOCASE",
                (category, normalized),
            ).fetchone()
            if existing:
                raise ValueError("Ese valor ya existe en la lista.")
            cursor = connection.execute(
                "INSERT INTO catalog_entries(category, value) VALUES (?, ?)", (category, normalized)
            )
            return int(cursor.lastrowid)

    def update_catalog_item(self, item_id: int, value: str) -> None:
        normalized = value.strip()
        if not normalized:
            raise ValueError("El valor no puede estar vacío.")
        with closing(self._connect()) as connection, connection:
            item = connection.execute("SELECT category FROM catalog_entries WHERE id = ?", (item_id,)).fetchone()
            if not item:
                raise ValueError("No se encontró el elemento seleccionado.")
            duplicate = connection.execute(
                "SELECT 1 FROM catalog_entries WHERE category = ? AND value = ? COLLATE NOCASE AND id <> ?",
                (item["category"], normalized, item_id),
            ).fetchone()
            if duplicate:
                raise ValueError("Ya existe otro elemento con ese nombre.")
            connection.execute(
                "UPDATE catalog_entries SET value = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
                (normalized, item_id),
            )

    def set_catalog_active(self, item_id: int, active: bool) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "UPDATE catalog_entries SET is_active = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
                (int(active), item_id),
            )

    def admin_password_exists(self) -> bool:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT 1 FROM app_settings WHERE setting_key = 'admin_password_hash'"
            ).fetchone()
        return row is not None

    def set_initial_admin_password(self, password: str) -> None:
        if len(password) < 10:
            raise ValueError("La contraseña debe tener al menos 10 caracteres.")
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
        with closing(self._connect()) as connection, connection:
            if self.admin_password_exists():
                raise ValueError("La contraseña de administrador ya fue configurada.")
            connection.executemany(
                "INSERT INTO app_settings(setting_key, setting_value) VALUES (?, ?)",
                [("admin_password_salt", salt.hex()), ("admin_password_hash", digest.hex())],
            )

    def verify_admin_password(self, password: str) -> bool:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT setting_key, setting_value FROM app_settings WHERE setting_key IN ('admin_password_salt','admin_password_hash')"
            ).fetchall()
        values = {row["setting_key"]: row["setting_value"] for row in rows}
        if not {"admin_password_salt", "admin_password_hash"}.issubset(values):
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(values["admin_password_salt"]), 310_000
        ).hex()
        return hmac.compare_digest(candidate, values["admin_password_hash"])

    def change_admin_password(self, current_password: str, new_password: str) -> None:
        if len(new_password) < 10:
            raise ValueError("La nueva clave debe tener al menos 10 caracteres.")
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT setting_key, setting_value FROM app_settings "
                "WHERE setting_key IN ('admin_password_salt','admin_password_hash')"
            ).fetchall()
            values = {row["setting_key"]: row["setting_value"] for row in rows}
            if not {"admin_password_salt", "admin_password_hash"}.issubset(values):
                raise ValueError("Primero debe configurar la clave de administrador.")
            current_digest = hashlib.pbkdf2_hmac(
                "sha256", current_password.encode("utf-8"), bytes.fromhex(values["admin_password_salt"]), 310_000
            ).hex()
            if not hmac.compare_digest(current_digest, values["admin_password_hash"]):
                raise ValueError("La clave actual no es correcta.")
            new_salt = secrets.token_bytes(16)
            new_digest = hashlib.pbkdf2_hmac("sha256", new_password.encode("utf-8"), new_salt, 310_000).hex()
            connection.executemany(
                "UPDATE app_settings SET setting_value = ? WHERE setting_key = ?",
                [(new_salt.hex(), "admin_password_salt"), (new_digest, "admin_password_hash")],
            )
            connection.commit()
