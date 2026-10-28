from __future__ import annotations

from datetime import datetime

from desktop.app.models.report import EmergencyReport
from desktop.app.repositories.local_report_repository import LocalReportRepository


class ReportService:
    REQUIRED = {
        "emergency_type": "Tipo de emergencia",
        "codification": "Codificación",
        "address": "Dirección",
        "district": "Distrito",
        "shift_operator": "Centralista de turno",
        "work_description": "Trabajo realizado",
        "signature_name": "Firma / conformidad",
    }

    def __init__(self, repository: LocalReportRepository) -> None:
        self.repository = repository

    def create(self, values: dict) -> EmergencyReport:
        report = self.prepare(values)
        self.repository.save(report)
        return report

    def prepare(self, values: dict) -> EmergencyReport:
        return self._build_report(values)

    def prepare_update(self, report_id: str, values: dict) -> EmergencyReport:
        current = self.repository.get(report_id)
        if current is None:
            raise ValueError("No se encontró el parte que se desea corregir.")
        values = dict(values)
        values.pop("local_number", None)
        data = self._validated_values(values)
        return EmergencyReport(
            id=current.id,
            local_number=current.local_number,
            created_at=current.created_at,
            sync_status=current.sync_status,
            **data,
        )

    def _build_report(self, values: dict) -> EmergencyReport:
        values = dict(values)
        manual_number = str(values.pop("local_number", "")).strip()
        data = self._validated_values(values)
        occurred = datetime.fromisoformat(data["occurred_at"])
        if manual_number:
            if len(manual_number) > 80:
                raise ValueError("El número de parte no debe superar 80 caracteres.")
            if self.repository.local_number_exists(manual_number):
                raise ValueError("Ese número de parte ya está registrado en esta computadora.")
            number = manual_number
        else:
            number = self.repository.next_local_number(occurred.year)
        return EmergencyReport.new(local_number=number, **data)

    def _validated_values(self, values: dict) -> dict:
        values = dict(values)
        missing = [label for key, label in self.REQUIRED.items() if not str(values.get(key, "")).strip()]
        if missing:
            raise ValueError("Complete los campos obligatorios: " + ", ".join(missing))
        try:
            datetime.fromisoformat(values["occurred_at"])
        except (ValueError, TypeError):
            raise ValueError("Indique una fecha y hora válidas para la emergencia.") from None
        return values
