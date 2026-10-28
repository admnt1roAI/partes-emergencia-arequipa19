from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from desktop.app.repositories.local_report_repository import LocalReportRepository
from desktop.app.ui.main_window import MainWindow, apply_theme


def main() -> int:
    log_dir = Path.home() / "AppData" / "Local" / "Arequipa19" / "PartesEmergencia"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=log_dir / "desktop.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    app.setApplicationName("Partes de Emergencia Arequipa 19")
    apply_theme(app)
    try:
        window = MainWindow(LocalReportRepository())
    except Exception as error:
        logging.exception("No se pudo iniciar la base local")
        QMessageBox.critical(None, "Error de inicio", f"No se pudo abrir el almacenamiento local.\n{error}")
        return 1
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
