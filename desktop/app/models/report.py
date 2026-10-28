from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


@dataclass
class EmergencyReport:
    id: str
    local_number: str
    occurred_at: str
    emergency_type: str
    codification: str
    address: str
    district: str
    work_description: str
    victims: list[dict[str, str]] = field(default_factory=list)
    vehicles: list[dict[str, str]] = field(default_factory=list)
    units: list[dict[str, str]] = field(default_factory=list)
    personnel: list[dict[str, str]] = field(default_factory=list)
    supports: list[dict[str, str]] = field(default_factory=list)
    pnp_support: list[dict[str, str]] = field(default_factory=list)
    materials: str = ""
    uniformed: str = "Sí"
    equipment_orderly: str = "Sí"
    logbook_recorded: str = "Sí"
    shift_operator: str = ""
    filled_by: str = ""
    observations: str = ""
    signature_name: str = ""
    sync_status: str = "pending"
    created_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat(timespec="seconds"))

    @classmethod
    def new(cls, local_number: str, **values: Any) -> "EmergencyReport":
        return cls(id=str(uuid4()), local_number=local_number, **values)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "EmergencyReport":
        return cls(**values)
