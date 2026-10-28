from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from desktop.app.repositories.local_report_repository import LocalReportRepository
from desktop.app.services.report_service import ReportService
from desktop.app.documents.report_pdf import generate_report_pdf


class LocalReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repository = LocalReportRepository(Path(self.temp.name) / "test.sqlite3")
        self.service = ReportService(self.repository)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def values(self) -> dict:
        return {
            "occurred_at": "2026-10-28T10:20:00-05:00",
            "emergency_type": "Incendio",
            "codification": "INC-01",
            "address": "Av. Ejemplo 123",
            "district": "Cercado",
            "work_description": "Control y extinción del incendio.",
            "shift_operator": "Operador de turno",
            "signature_name": "Bombero de prueba",
            "victims": [{"nombres_y_apellidos": "Persona de prueba", "edad": "34", "lesión": "Leve"}],
        }

    def test_save_and_search_report_with_related_rows(self) -> None:
        report = self.service.create(self.values())
        self.assertEqual(report.local_number, "LOCAL-2026-000001")
        found = self.repository.search("Ejemplo")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["id"], report.id)
        loaded = self.repository.get(report.id)
        self.assertEqual(loaded.victims[0]["nombres_y_apellidos"], "Persona de prueba")
        self.assertEqual(loaded.sync_status, "pending")

    def test_required_fields_are_validated_before_insert(self) -> None:
        values = self.values()
        values["address"] = ""
        with self.assertRaisesRegex(ValueError, "Dirección"):
            self.service.create(values)
        self.assertEqual(self.repository.search(), [])

    def test_catalogs_are_sorted_editable_and_preserve_existing_report_values(self) -> None:
        district_names = [item["value"] for item in self.repository.list_catalog("district")]
        self.assertEqual(district_names, sorted(district_names, key=lambda value: value.casefold().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")))
        report = self.service.create(self.values())
        cercado = next(item for item in self.repository.list_catalog("district") if item["value"] == "Cercado")
        self.repository.update_catalog_item(cercado["id"], "Cercado Histórico")
        self.repository.set_catalog_active(cercado["id"], False)
        self.assertNotIn("Cercado Histórico", [item["value"] for item in self.repository.list_catalog("district")])
        self.assertEqual(self.repository.get(report.id).district, "Cercado")

    def test_admin_password_is_hashed_and_verified(self) -> None:
        self.repository.set_initial_admin_password("una-clave-segura")
        self.assertTrue(self.repository.admin_password_exists())
        self.assertTrue(self.repository.verify_admin_password("una-clave-segura"))
        self.assertFalse(self.repository.verify_admin_password("incorrecta"))

    def test_admin_password_can_be_changed_and_old_key_stops_working(self) -> None:
        self.repository.set_initial_admin_password("clave-administrador-1")
        self.repository.change_admin_password("clave-administrador-1", "clave-administrador-2")
        self.assertFalse(self.repository.verify_admin_password("clave-administrador-1"))
        self.assertTrue(self.repository.verify_admin_password("clave-administrador-2"))
        with self.assertRaisesRegex(ValueError, "actual no es correcta"):
            self.repository.change_admin_password("clave-administrador-1", "clave-administrador-3")

    def test_manual_report_number_is_saved_and_duplicates_are_rejected(self) -> None:
        values = self.values()
        values["local_number"] = "AQP19-TECLADO-77"
        report = self.service.create(values)
        self.assertEqual(report.local_number, "AQP19-TECLADO-77")
        self.assertTrue(self.repository.local_number_exists("AQP19-TECLADO-77"))
        with self.assertRaisesRegex(ValueError, "ya está registrado"):
            self.service.create(values)

    def test_manual_local_sequence_does_not_collide_with_automatic_number(self) -> None:
        values = self.values()
        values["local_number"] = "LOCAL-2026-000001"
        self.service.create(values)
        next_values = self.values()
        next_values["occurred_at"] = "2026-10-29T10:20:00-05:00"
        automatic = self.service.create(next_values)
        self.assertEqual(automatic.local_number, "LOCAL-2026-000002")

    def test_one_off_dropdown_values_are_saved_without_changing_catalogs(self) -> None:
        values = self.values()
        values.update({
            "district": "Distrito temporal",
            "shift_operator": "Centralista suplente",
            "emergency_type": "Evento especial",
            "codification": "COD-ESPECIAL",
        })
        report = self.service.create(values)
        saved = self.repository.get(report.id)
        self.assertEqual(saved.district, "Distrito temporal")
        self.assertEqual(saved.shift_operator, "Centralista suplente")
        self.assertEqual(saved.emergency_type, "Evento especial")
        self.assertNotIn("Distrito temporal", [item["value"] for item in self.repository.list_catalog("district")])

    def test_finalized_report_pdf_and_admin_correction_keep_both_versions(self) -> None:
        report = self.service.prepare(self.values())
        pdf_v1 = Path(self.temp.name) / "Parte_v1.pdf"
        generate_report_pdf(report, pdf_v1, version=1)
        self.repository.save(report, pdf_path=str(pdf_v1), finalized=True)
        info = self.repository.get_report_info(report.id)
        self.assertEqual(info["is_finalized"], 1)
        self.assertEqual(Path(info["pdf_path"]), pdf_v1)

        corrected_values = self.values()
        corrected_values["work_description"] = "Se corrige el detalle del trabajo realizado."
        corrected = self.service.prepare_update(report.id, corrected_values)
        pdf_v2 = Path(self.temp.name) / "Parte_v2.pdf"
        generate_report_pdf(corrected, pdf_v2, version=2)
        version = self.repository.update_finalized_report(corrected, str(pdf_v2), "Completar descripción")

        self.assertEqual(version, 2)
        self.assertTrue(pdf_v1.is_file())
        self.assertTrue(pdf_v2.is_file())
        self.assertEqual(self.repository.get(report.id).work_description, corrected_values["work_description"])
        history = self.repository.list_report_versions(report.id)
        self.assertEqual([item["version_number"] for item in history], [2, 1])
        self.assertEqual(history[1]["pdf_path"], str(pdf_v1))


if __name__ == "__main__":
    unittest.main()
