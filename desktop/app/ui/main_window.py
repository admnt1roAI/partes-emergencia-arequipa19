from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from html import escape as html_escape

from PySide6.QtCore import Qt, QDateTime, QSize, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QFontDatabase, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDateTimeEdit, QDialog, QFileDialog, QInputDialog,
    QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLayout, QLineEdit, QMainWindow, QMessageBox,
    QCompleter, QPlainTextEdit, QPushButton, QScrollArea, QStackedWidget, QTableWidget, QTextBrowser,
    QTableWidgetItem, QVBoxLayout, QWidget, QSizePolicy,
)

from desktop.app.models.report import EmergencyReport
from desktop.app.documents.report_pdf import generate_report_pdf
from desktop.app.repositories.local_report_repository import LocalReportRepository
from desktop.app.services.report_service import ReportService


BRANDING_DEFAULTS = {
    "application_title": "GESTIÓN DE PARTES DE EMERGENCIAS CGBVP",
    "application_label": "APLICACIÓN DE ESCRITORIO",
    "institution_line_1": "CUERPO GENERAL DE BOMBEROS VOLUNTARIOS DEL PERÚ",
    "institution_line_2": "VII COMANDANCIA DEPARTAMENTAL",
    "institution_line_3": "BENEMÉRITA Y CENTENARIA COMPAÑÍA DE BOMBEROS AREQUIPA 19",
    "document_title": "PARTE DE EMERGENCIA",
    "document_subtitle": "Documento Oficial según el Artículo N.º 217 del Reglamento Interno de Funciones",
}


class ProportionalTableWidget(QTableWidget):
    def __init__(self, rows: int, columns: int, ratios: list[float] | None = None) -> None:
        super().__init__(rows, columns)
        self.column_ratios = ratios

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self.column_ratios or len(self.column_ratios) != self.columnCount():
            return
        available = self.viewport().width()
        assigned = 0
        for column, ratio in enumerate(self.column_ratios):
            width = available - assigned if column == len(self.column_ratios) - 1 else int(available * ratio)
            self.setColumnWidth(column, width)
            assigned += width


class RepeatableTable(QWidget):
    def __init__(self, title: str, columns: list[str], repository: LocalReportRepository,
                 catalog_columns: dict[int, str] | None = None, paired_records: bool = False,
                 column_ratios: list[float] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository
        self.catalog_columns = catalog_columns or {}
        self.paired_records = paired_records
        self.column_ratios = column_ratios
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        name = QLabel(title)
        name.setObjectName("sectionTitle")
        name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(name, 1)
        bar.addStretch()
        add_button = QPushButton("Agregar fila")
        add_button.setObjectName("smallPrimary")
        add_button.clicked.connect(self.add_row)
        remove_button = QPushButton("Eliminar fila")
        remove_button.clicked.connect(self.remove_row)
        bar.addWidget(add_button)
        bar.addWidget(remove_button)
        layout.addLayout(bar)
        self.table = ProportionalTableWidget(0, len(columns), column_ratios)
        self.table.setHorizontalHeaderLabels(columns)
        resize_mode = QHeaderView.ResizeMode.Interactive if column_ratios else QHeaderView.ResizeMode.Stretch
        self.table.horizontalHeader().setSectionResizeMode(resize_mode)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setMinimumHeight(88)
        layout.addWidget(self.table)
        self.add_row()

    def add_row(self) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        for col in range(self.table.columnCount()):
            category = self.catalog_columns.get(col)
            if category:
                self.table.setCellWidget(row, col, self._catalog_combo(category))
            else:
                self.table.setItem(row, col, QTableWidgetItem(""))
        self._adjust_table_height()

    def _adjust_table_height(self) -> None:
        header_height = self.table.horizontalHeader().sizeHint().height()
        rows_height = sum(self.table.rowHeight(row) for row in range(self.table.rowCount()))
        frame = 2 * self.table.frameWidth()
        self.table.setFixedHeight(max(88, header_height + rows_height + frame + 8))

    def _catalog_combo(self, category: str, selected: str = "") -> QComboBox:
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        completer = combo.completer()
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        combo.addItem("Seleccionar...", "")
        for item in self.repository.list_catalog(category):
            combo.addItem(item["value"], item["value"])
        index = combo.findText(selected) if selected else -1
        if index >= 0:
            combo.setCurrentIndex(index)
        elif selected:
            combo.setCurrentIndex(-1)
            combo.setEditText(selected)
        else:
            combo.setCurrentIndex(0)
        return combo

    def refresh_catalogs(self) -> None:
        for row in range(self.table.rowCount()):
            for column, category in self.catalog_columns.items():
                widget = self.table.cellWidget(row, column)
                if not isinstance(widget, QComboBox):
                    continue
                value = widget.currentText().strip()
                if widget.currentIndex() == 0 and not widget.currentData() and value == "Seleccionar...":
                    value = ""
                self.table.removeCellWidget(row, column)
                self.table.setCellWidget(row, column, self._catalog_combo(category, value))

    def remove_row(self) -> None:
        if not self.table.rowCount():
            return
        answer = QMessageBox.warning(
            self,
            "Confirmar eliminación",
            "Seguro que desea eliminar, se perderán datos de esa fila",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)
        elif self.table.rowCount():
            self.table.removeRow(self.table.rowCount() - 1)
        if not self.table.rowCount():
            self.add_row()
        else:
            self._adjust_table_height()

    def values(self) -> list[dict[str, str]]:
        keys = [self.table.horizontalHeaderItem(i).text().lower().replace(" ", "_") for i in range(self.table.columnCount())]
        values = []
        for row in range(self.table.rowCount()):
            if self.paired_records:
                for first_col in (0, 2):
                    record = {}
                    for col in (first_col, first_col + 1):
                        widget = self.table.cellWidget(row, col)
                        if isinstance(widget, QComboBox):
                            value = widget.currentText().strip()
                            if widget.currentIndex() == 0 and not widget.currentData() and value == "Seleccionar...":
                                value = ""
                        else:
                            item = self.table.item(row, col)
                            value = item.text().strip() if item else ""
                        record[keys[col]] = value
                    if any(record.values()):
                        values.append(record)
                continue
            record = {}
            for col in range(self.table.columnCount()):
                widget = self.table.cellWidget(row, col)
                if isinstance(widget, QComboBox):
                    value = widget.currentText().strip()
                    if widget.currentIndex() == 0 and not widget.currentData() and value == "Seleccionar...":
                        value = ""
                else:
                    item = self.table.item(row, col)
                    value = item.text().strip() if item else ""
                record[keys[col]] = value
            if any(record.values()):
                values.append(record)
        return values

    def load_values(self, records: list[dict[str, str]]) -> None:
        self.table.setRowCount(0)
        row_count = max(1, (len(records) + 1) // 2) if self.paired_records else max(1, len(records))
        for _ in range(row_count):
            self.add_row()
        keys = [self.table.horizontalHeaderItem(i).text().lower().replace(" ", "_") for i in range(self.table.columnCount())]
        for index, record in enumerate(records):
            row = index // 2 if self.paired_records else index
            first_column = (index % 2) * 2 if self.paired_records else 0
            column_range = range(first_column, first_column + 2) if self.paired_records else range(self.table.columnCount())
            for column in column_range:
                value = str(record.get(keys[column], ""))
                widget = self.table.cellWidget(row, column)
                if isinstance(widget, QComboBox):
                    item_index = widget.findText(value)
                    if item_index >= 0:
                        widget.setCurrentIndex(item_index)
                    elif value:
                        widget.setEditText(value)
                else:
                    self.table.setItem(row, column, QTableWidgetItem(value))
        self._adjust_table_height()


class MainWindow(QMainWindow):
    def __init__(self, repository: LocalReportRepository | None = None) -> None:
        super().__init__()
        self.repository = repository or LocalReportRepository()
        self.service = ReportService(self.repository)
        self.branding = self._load_branding()
        self._admin_session_password: str | None = None
        self._editing_report_id: str | None = None
        self._admin_session_timer = QTimer(self)
        self._admin_session_timer.setSingleShot(True)
        self._admin_session_timer.timeout.connect(self._expire_admin_session)
        self.setWindowTitle("Gestión de Partes de Emergencia | Arequipa 19")
        self.resize(1360, 920)
        self.setMinimumSize(980, 700)
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._header())
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        self.nav = QWidget()
        self.nav.setObjectName("sidebar")
        nav_layout = QVBoxLayout(self.nav)
        nav_layout.setContentsMargins(10, 18, 10, 10)
        nav_layout.addWidget(QLabel("PARTES DE EMERGENCIA"))
        for text, page in (("Nuevo parte", 0), ("Buscar / consultar", 1)):
            button = QPushButton(text)
            button.setObjectName("navButton")
            button.clicked.connect(lambda _checked=False, target=page: self.show_page(target))
            nav_layout.addWidget(button)
        admin_button = QPushButton("Modo administrador")
        admin_button.setObjectName("navButton")
        admin_button.clicked.connect(self.open_admin)
        nav_layout.addWidget(admin_button)
        self.admin_logout_button = QPushButton("Cerrar sesión administrador")
        self.admin_logout_button.setObjectName("navButton")
        self.admin_logout_button.clicked.connect(self.close_admin_session)
        self.admin_logout_button.hide()
        nav_layout.addWidget(self.admin_logout_button)
        nav_layout.addStretch()
        local_note = QLabel(
            "Guardado local\nPendiente de sincronización\nN.º manual o automático\nN.º local no oficial"
        )
        local_note.setObjectName("sidebarNote")
        local_note.setWordWrap(True)
        nav_layout.addWidget(local_note)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_form_page())
        self.pages.addWidget(self._build_search_page())
        self.pages.addWidget(self._build_admin_page())
        body.addWidget(self.nav)
        body.addWidget(self.pages, 1)
        outer.addLayout(body, 1)
        self.statusBar().showMessage(f"Almacenamiento local · {self.repository.database_path}")

    def _header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("header")
        header.setMinimumHeight(35)
        row = QHBoxLayout(header)
        row.setContentsMargins(18, 4, 20, 4)
        self.application_title_label = QLabel(self.branding["application_title"])
        self.application_title_label.setObjectName("brandTitle")
        row.addWidget(self.application_title_label, 1)
        self.application_label_widget = QLabel(self.branding["application_label"])
        self.application_label_widget.setObjectName("applicationLabel")
        row.addWidget(self.application_label_widget)
        return header

    def _load_branding(self) -> dict[str, str]:
        branding = {
            key: self.repository.get_app_setting(f"branding.{key}", default)
            for key, default in BRANDING_DEFAULTS.items()
        }
        default_logo = Path(__file__).resolve().parents[2] / "assets" / "emblem-reference.png"
        saved_logo = self.repository.get_app_setting("branding.emblem_path", str(default_logo))
        branding["emblem_path"] = saved_logo if Path(saved_logo).is_file() else str(default_logo)
        return branding

    def _apply_emblem(self) -> None:
        if not hasattr(self, "document_emblem"):
            return
        pixmap = QPixmap(self.branding["emblem_path"])
        if not pixmap.isNull():
            self.document_emblem.setPixmap(pixmap.scaled(
                QSize(76, 92), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
            ))

    def _apply_signature_watermark(self) -> None:
        if not hasattr(self, "signature_watermark"):
            return
        watermark_path = Path(__file__).resolve().parents[2] / "assets" / "signature-watermark.jpg"
        pixmap = QPixmap(str(watermark_path))
        if not pixmap.isNull():
            self.signature_watermark.setPixmap(pixmap.scaled(
                QSize(250, 57), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
            ))

    def _apply_branding(self) -> None:
        self.application_title_label.setText(self.branding["application_title"])
        self.application_label_widget.setText(self.branding["application_label"])
        for key, label in getattr(self, "document_brand_labels", {}).items():
            label.setText(self.branding[key])
        self._apply_emblem()

    def _build_form_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 14, 16, 16)
        document_header = QWidget()
        document_header.setObjectName("documentHeader")
        document_layout = QHBoxLayout(document_header)
        document_layout.setContentsMargins(12, 10, 12, 10)
        emblem = QLabel()
        emblem.setObjectName("documentEmblem")
        self.document_emblem = emblem
        self._apply_emblem()
        document_layout.addWidget(emblem)
        institutional = QVBoxLayout()
        institutional.setSpacing(2)
        self.document_brand_labels: dict[str, QLabel] = {}
        for key, object_name in (
            ("institution_line_1", "institutionLine"),
            ("institution_line_2", "institutionLine"),
            ("institution_line_3", "institutionLine"),
            ("document_title", "documentTitle"),
            ("document_subtitle", "documentSubtitle"),
        ):
            text = self.branding[key]
            line = QLabel(text)
            line.setObjectName(object_name)
            line.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.document_brand_labels[key] = line
            institutional.addWidget(line)
        document_layout.addLayout(institutional, 1)
        document_layout.addSpacing(50)
        layout.addWidget(document_header)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(2, 8, 2, 8)
        form = QGridLayout()
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)
        self.local_number = QLineEdit()
        self.local_number.setPlaceholderText("Vacío = asignación local automática")
        self.occurred_at = QDateTimeEdit(QDateTime.currentDateTime())
        self.occurred_at.setCalendarPopup(True)
        self.occurred_at.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.emergency_type = QComboBox()
        self._load_catalog_combo(self.emergency_type, "emergency_type")
        self.codification = QComboBox()
        self._load_catalog_combo(self.codification, "codification", editable=True)
        self.address = QLineEdit()
        self.district = QComboBox()
        self._load_catalog_combo(self.district, "district")
        self.work_description = QPlainTextEdit()
        self.work_description.setMaximumHeight(64)
        def field_label(text: str) -> QLabel:
            label = QLabel(text.upper())
            label.setObjectName("fieldLabel")
            return label
        form.addWidget(field_label("Parte N.º"), 0, 0)
        form.addWidget(self.local_number, 0, 1)
        form.addWidget(field_label("Fecha *"), 0, 2)
        form.addWidget(self.occurred_at, 0, 3, 1, 2)
        form.addWidget(field_label("Emergencia *"), 1, 0)
        form.addWidget(self.emergency_type, 1, 1, 1, 2)
        form.addWidget(field_label("Codificación *"), 1, 3)
        form.addWidget(self.codification, 1, 4, 1, 2)
        form.addWidget(field_label("Dirección *"), 2, 0)
        form.addWidget(self.address, 2, 1, 1, 3)
        form.addWidget(field_label("Distrito *"), 2, 4)
        form.addWidget(self.district, 2, 5)
        form.addWidget(field_label("Trabajo realizado *"), 3, 0, 1, 6)
        form.addWidget(self.work_description, 4, 0, 1, 6)
        for column in (1, 3, 4, 5):
            form.setColumnStretch(column, 1)
        content_layout.addWidget(self._section("Datos generales", form))

        self.victims = self._table(
            "Víctimas", ["Nombres y apellidos", "DNI", "Edad", "Lesión"],
            column_ratios=[0.50, 0.20, 0.10, 0.20],
        )
        self.vehicles = self._table("Vehículos involucrados", ["Placa", "Marca", "Modelo", "Color", "Año"])
        self.units = self._table(
            "Unidades que asistieron",
            ["Unidad", "Piloto", "Al mando", "KM salida", "KM ingreso", "H. salida", "H. ingreso", "SOAT", "CITV"],
            {0: "unit", 1: "firefighter", 2: "firefighter", 7: "yes_no", 8: "yes_no"},
            column_ratios=[0.12, 0.16, 0.18, 0.10, 0.10, 0.10, 0.10, 0.07, 0.07],
        )
        self.personnel = self._table(
            "Efectivos en servicio",
            ["Efectivo", "Condición", "Efectivo", "Condición"],
            {0: "firefighter", 1: "personnel_condition", 2: "firefighter", 3: "personnel_condition"},
            paired_records=True, column_ratios=[0.4, 0.1, 0.4, 0.1],
        )
        self.supports = self._table(
            "Vehículos de apoyo del CGBVP", ["Compañía", "Unidad", "Al mando"],
            {0: "company", 1: "unit"},
        )
        self.pnp_support = self._table(
            "Apoyo PNP / otras instituciones", ["Institución / dependencia", "Vehículo", "Al mando"],
            {0: "police_station"},
        )
        for widget in (self.victims, self.vehicles, self.units, self.personnel):
            content_layout.addWidget(self._section_widget(widget))

        self.materials = QPlainTextEdit()
        self.materials.setPlaceholderText("Detalle el material utilizado")
        self.materials.setMaximumHeight(72)
        content_layout.addWidget(self._section("Material utilizado", self.materials))
        for widget in (self.supports, self.pnp_support):
            content_layout.addWidget(self._section_widget(widget))
        self.uniformed = self._yes_no()
        self.equipment_orderly = self._yes_no()
        self.logbook = self._yes_no()
        checklist_grid = QGridLayout()
        checklist_grid.addWidget(QLabel("Personal correctamente uniformado"), 0, 0)
        checklist_grid.addWidget(self.uniformed, 0, 1)
        checklist_grid.addWidget(QLabel("Material conforme, limpio y ordenado"), 0, 2)
        checklist_grid.addWidget(self.equipment_orderly, 0, 3)
        checklist_grid.addWidget(QLabel("Bitácora registrada correctamente"), 0, 4)
        checklist_grid.addWidget(self.logbook, 0, 5)
        checklist_grid.setColumnStretch(0, 1)
        checklist_grid.setColumnStretch(2, 1)
        checklist_grid.setColumnStretch(4, 1)
        content_layout.addWidget(self._section("Verificaciones", checklist_grid))

        closing = QGridLayout()
        self.shift_operator = QComboBox()
        self._load_catalog_combo(self.shift_operator, "shift_operator")
        self.filled_by = QLineEdit()
        self.observations = QPlainTextEdit()
        self.observations.setMaximumHeight(72)
        self.signature = QLineEdit()
        closing.addWidget(QLabel("CENTRALISTA DE TURNO"), 0, 0)
        closing.addWidget(self.shift_operator, 0, 1)
        closing.addWidget(QLabel("LLENADO POR"), 0, 2)
        closing.addWidget(self.filled_by, 0, 3)
        closing.addWidget(QLabel("OBSERVACIONES"), 1, 0, 1, 4)
        closing.addWidget(self.observations, 2, 0, 1, 4)
        closing.addWidget(QLabel("FIRMA / CONFORMIDAD *"), 3, 1)
        self.signature_watermark = QLabel()
        self.signature_watermark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._apply_signature_watermark()
        closing.addWidget(self.signature_watermark, 3, 2)
        self.signature.setMaximumWidth(180)
        closing.addWidget(self.signature, 3, 3)
        closing.setColumnStretch(1, 1)
        closing.setColumnStretch(3, 1)
        content_layout.addWidget(self._section("Cierre del parte", closing))
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        actions = QHBoxLayout()
        actions.addStretch()
        clear = QPushButton("Limpiar formulario")
        clear.clicked.connect(self.clear_form)
        self.save_button = QPushButton("GUARDAR PARTE")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.save_report)
        actions.addWidget(clear)
        actions.addWidget(self.save_button)
        layout.addLayout(actions)
        return page

    def _table(self, title: str, columns: list[str], catalog_columns: dict[int, str] | None = None,
               paired_records: bool = False, column_ratios: list[float] | None = None) -> RepeatableTable:
        return RepeatableTable(title, columns, self.repository, catalog_columns, paired_records, column_ratios)

    def _yes_no(self) -> QComboBox:
        combo = QComboBox()
        self._load_catalog_combo(combo, "yes_no", "Sí")
        return combo

    def _section(self, title: str, content: QWidget | QLayout) -> QFrame:
        frame = QFrame()
        frame.setObjectName("section")
        layout = QVBoxLayout(frame)
        label = QLabel(title.upper())
        label.setObjectName("sectionTitle")
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(label)
        if isinstance(content, QLayout):
            inner = QWidget()
            inner.setLayout(content)
            layout.addWidget(inner)
        else:
            layout.addWidget(content)
        return frame

    def _section_widget(self, child: QWidget) -> QFrame:
        frame = QFrame()
        frame.setObjectName("section")
        layout = QVBoxLayout(frame)
        layout.addWidget(child)
        return frame

    def _build_search_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 16, 18, 16)
        title = QLabel("PARTES GUARDADOS EN ESTA COMPUTADORA")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        note = QLabel("Partes locales, incluidos los que aún no se han sincronizado.")
        note.setObjectName("muted")
        layout.addWidget(note)
        row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar por número local, tipo, dirección o distrito")
        self.search_input.returnPressed.connect(self.refresh_reports)
        search_button = QPushButton("Buscar")
        search_button.setObjectName("primary")
        search_button.clicked.connect(self.refresh_reports)
        refresh_button = QPushButton("Actualizar lista")
        refresh_button.clicked.connect(self.refresh_reports)
        row.addWidget(self.search_input, 1)
        row.addWidget(search_button)
        row.addWidget(refresh_button)
        layout.addLayout(row)
        self.report_table = QTableWidget(0, 6)
        self.report_table.setHorizontalHeaderLabels(["N.º parte", "Fecha", "Emergencia", "Dirección", "Distrito", "Estado"])
        self.report_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.report_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.report_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.report_table.cellDoubleClicked.connect(self.open_selected_report)
        layout.addWidget(self.report_table, 1)
        self.refresh_reports()
        return page

    def _build_admin_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 16, 18, 16)
        title = QLabel("ADMINISTRACIÓN DE LISTAS DEL PARTE")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        note = QLabel(
            "Administra las listas desplegables de todo el parte. Al eliminar un valor se oculta "
            "de los nuevos partes; los partes guardados conservan el texto que tenían al registrarse."
        )
        note.setObjectName("notice")
        note.setWordWrap(True)
        layout.addWidget(note)
        category_row = QHBoxLayout()
        category_row.addWidget(QLabel("Lista:"))
        self.admin_category = QComboBox()
        self.catalog_labels = {
            "district": "Distritos",
            "shift_operator": "Centralistas de turno",
            "emergency_type": "Tipos de emergencia",
            "codification": "Codificaciones",
            "unit": "Unidades",
            "firefighter": "Personal / efectivos",
            "personnel_condition": "Condiciones del personal",
            "company": "Compañías de apoyo",
            "police_station": "Comisarías",
            "yes_no": "Opciones Sí / No",
        }
        for category, label in self.catalog_labels.items():
            self.admin_category.addItem(label, category)
        self.admin_category.currentIndexChanged.connect(self.refresh_admin_catalog)
        category_row.addWidget(self.admin_category, 1)
        layout.addLayout(category_row)

        self.admin_catalog_table = QTableWidget(0, 2)
        self.admin_catalog_table.setHorizontalHeaderLabels(["Valor", "Estado"])
        self.admin_catalog_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.admin_catalog_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.admin_catalog_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.admin_catalog_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.admin_catalog_table.cellDoubleClicked.connect(lambda _row, _column: self.edit_catalog_item())
        layout.addWidget(self.admin_catalog_table, 1)
        actions = QHBoxLayout()
        add_item = QPushButton("Agregar")
        add_item.setObjectName("primary")
        add_item.clicked.connect(self.add_catalog_item)
        edit_item = QPushButton("Modificar")
        edit_item.clicked.connect(self.edit_catalog_item)
        self.toggle_catalog_button = QPushButton("Eliminar de la lista")
        self.toggle_catalog_button.clicked.connect(self.toggle_catalog_item)
        self.admin_catalog_table.itemSelectionChanged.connect(self._update_catalog_action)
        actions.addWidget(add_item)
        actions.addWidget(edit_item)
        actions.addWidget(self.toggle_catalog_button)
        branding = QPushButton("Escudo y títulos")
        branding.clicked.connect(self.edit_branding_settings)
        actions.addWidget(branding)
        actions.addStretch()
        back = QPushButton("Volver al parte")
        back.clicked.connect(self.close_admin_session)
        actions.addWidget(back)
        change_password = QPushButton("Cambiar clave de administrador")
        change_password.clicked.connect(self.change_admin_password)
        actions.addWidget(change_password)
        layout.addLayout(actions)
        self.refresh_admin_catalog()
        return page

    def edit_branding_settings(self) -> None:
        if not self._require_admin_session():
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Escudo y títulos de la aplicación")
        dialog.resize(760, 620)
        layout = QVBoxLayout(dialog)
        form = QGridLayout()
        fields: dict[str, QLineEdit] = {}
        field_labels = {
            "application_title": "Título de la barra principal",
            "application_label": "Texto lateral de la barra",
            "institution_line_1": "Institución - línea 1",
            "institution_line_2": "Institución - línea 2",
            "institution_line_3": "Institución - línea 3",
            "document_title": "Título del parte",
            "document_subtitle": "Subtítulo del parte",
        }
        for row, (key, label_text) in enumerate(field_labels.items()):
            label = QLabel(label_text)
            line = QLineEdit(self.branding[key])
            fields[key] = line
            form.addWidget(label, row, 0)
            form.addWidget(line, row, 1)
        layout.addLayout(form)

        emblem_row = QHBoxLayout()
        preview = QLabel()
        preview.setFixedSize(96, 108)
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setStyleSheet("border: 1px solid #b8cde0; background: white;")
        current_preview = QPixmap(self.branding["emblem_path"])
        if not current_preview.isNull():
            preview.setPixmap(current_preview.scaled(
                preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
            ))
        emblem_row.addWidget(preview)
        selected_logo: dict[str, str] = {"path": ""}
        choose_logo = QPushButton("Cambiar escudo…")
        emblem_row.addWidget(choose_logo)
        emblem_row.addStretch()
        layout.addWidget(QLabel("Escudo que aparecerá en pantalla y en los PDFs:"))
        layout.addLayout(emblem_row)

        def choose_emblem() -> None:
            image_path, _filter = QFileDialog.getOpenFileName(
                dialog, "Seleccionar escudo", "", "Imágenes (*.png *.jpg *.jpeg *.bmp *.webp)"
            )
            if not image_path:
                return
            pixmap = QPixmap(image_path)
            if pixmap.isNull():
                QMessageBox.warning(dialog, "Imagen no válida", "No se pudo abrir esa imagen.")
                return
            selected_logo["path"] = image_path
            preview.setPixmap(pixmap.scaled(
                preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
            ))

        choose_logo.clicked.connect(choose_emblem)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(dialog.reject)
        save = QPushButton("Guardar cambios")
        save.setObjectName("primary")

        def save_branding() -> None:
            if not self._require_admin_session():
                dialog.reject()
                return
            values = {key: field.text().strip() for key, field in fields.items()}
            empty = [label for key, label in field_labels.items() if not values[key]]
            if empty:
                QMessageBox.warning(dialog, "Faltan títulos", "Completa todos los textos antes de guardar.")
                return
            updated = dict(self.branding)
            updated.update(values)
            settings = {f"branding.{key}": value for key, value in values.items()}
            if selected_logo["path"]:
                image = QPixmap(selected_logo["path"])
                destination = self.repository.database_path.parent / "branding" / "emblem.png"
                destination.parent.mkdir(parents=True, exist_ok=True)
                if image.isNull() or not image.save(str(destination), "PNG"):
                    QMessageBox.warning(dialog, "No se guardó el escudo", "No se pudo guardar la imagen elegida.")
                    return
                updated["emblem_path"] = str(destination)
                settings["branding.emblem_path"] = str(destination)
            try:
                self.repository.set_app_settings(settings)
            except Exception as error:
                QMessageBox.warning(dialog, "No se guardaron los cambios", str(error))
                return
            self.branding = updated
            self._apply_branding()
            dialog.accept()
            self.statusBar().showMessage("Escudo y títulos actualizados", 5000)

        save.clicked.connect(save_branding)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)
        dialog.exec()

    def _load_catalog_combo(self, combo: QComboBox, category: str, selected: str = "", editable: bool = True) -> None:
        combo.blockSignals(True)
        combo.setEditable(editable)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        combo.clear()
        combo.addItem("Seleccionar...", "")
        for item in self.repository.list_catalog(category):
            combo.addItem(item["value"], item["value"])
        index = combo.findText(selected) if selected else -1
        if index >= 0:
            combo.setCurrentIndex(index)
        elif editable:
            combo.setCurrentIndex(-1)
            combo.setEditText(selected)
        else:
            combo.setCurrentIndex(0)
        if editable and combo.lineEdit():
            combo.lineEdit().setPlaceholderText("Seleccione o escriba...")
            completer = combo.completer()
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
        combo.blockSignals(False)

    def _refresh_form_catalogs(self) -> None:
        self._load_catalog_combo(self.district, "district", self._combo_value(self.district))
        self._load_catalog_combo(self.shift_operator, "shift_operator", self._combo_value(self.shift_operator))
        self._load_catalog_combo(self.emergency_type, "emergency_type", self._combo_value(self.emergency_type))
        self._load_catalog_combo(self.codification, "codification", self._combo_value(self.codification))
        for table in (self.units, self.personnel, self.supports, self.pnp_support):
            table.refresh_catalogs()
        for combo in (self.uniformed, self.equipment_orderly, self.logbook):
            self._load_catalog_combo(combo, "yes_no", self._combo_value(combo))

    def open_admin(self) -> None:
        if self._has_admin_session():
            self.refresh_admin_catalog()
            self.show_page(2)
            return
        if not self.repository.admin_password_exists():
            password, accepted = QInputDialog.getText(
                self, "Configurar administrador", "Crea una contraseña de administrador (mínimo 10 caracteres):",
                QLineEdit.EchoMode.Password,
            )
            if not accepted:
                return
            confirmation, confirmed = QInputDialog.getText(
                self, "Confirmar contraseña", "Vuelve a escribir la contraseña:", QLineEdit.EchoMode.Password
            )
            if not confirmed or password != confirmation:
                QMessageBox.warning(self, "Contraseña no configurada", "Las contraseñas no coinciden.")
                return
            try:
                self.repository.set_initial_admin_password(password)
            except ValueError as error:
                QMessageBox.warning(self, "No se pudo configurar", str(error))
                return
            self._start_admin_session(password)
            QMessageBox.information(
                self, "Modo administrador configurado",
                "Guarda esta contraseña. Se almacena una verificación cifrada con salt en la base local; no se puede recuperar desde la aplicación.",
            )
        else:
            password, accepted = QInputDialog.getText(
                self, "Acceso administrador", "Contraseña de administrador:", QLineEdit.EchoMode.Password
            )
            if not accepted:
                return
            if not self.repository.verify_admin_password(password):
                QMessageBox.warning(self, "Acceso denegado", "La contraseña no es correcta.")
                return
            self._start_admin_session(password)
        self.refresh_admin_catalog()
        self.show_page(2)

    def _require_admin_session(self) -> bool:
        if self._has_admin_session():
            return True
        self._stop_admin_session()
        if self._editing_report_id is not None:
            self.clear_form()
        QMessageBox.warning(self, "Sesión de administrador vencida", "La clave fue cambiada. Vuelve a ingresar con la clave vigente.")
        self.show_page(0)
        return False

    def _start_admin_session(self, password: str) -> None:
        self._admin_session_password = password
        self._admin_session_timer.start(10 * 60 * 1000)
        if hasattr(self, "admin_logout_button"):
            self.admin_logout_button.show()

    def _has_admin_session(self) -> bool:
        return bool(
            self._admin_session_password
            and self._admin_session_timer.isActive()
            and self.repository.verify_admin_password(self._admin_session_password)
        )

    def _stop_admin_session(self) -> None:
        self._admin_session_timer.stop()
        self._admin_session_password = None
        if hasattr(self, "admin_logout_button"):
            self.admin_logout_button.hide()

    def close_admin_session(self) -> None:
        was_editing = self._editing_report_id is not None
        self._stop_admin_session()
        if was_editing:
            self.clear_form()
        self.show_page(0)
        self.statusBar().showMessage("Sesión de administrador cerrada", 5000)

    def _expire_admin_session(self) -> None:
        was_editing = self._editing_report_id is not None
        self._stop_admin_session()
        if was_editing:
            self.clear_form()
            self.pages.setCurrentIndex(0)
        elif self.pages.currentIndex() == 2:
            self.pages.setCurrentIndex(0)
        self.statusBar().showMessage("Sesión de administrador cerrada automáticamente tras 10 minutos", 10000)

    def change_admin_password(self) -> None:
        current, accepted = QInputDialog.getText(
            self, "Cambiar clave", "Clave actual:", QLineEdit.EchoMode.Password
        )
        if not accepted:
            return
        new_password, accepted = QInputDialog.getText(
            self, "Cambiar clave", "Nueva clave (mínimo 10 caracteres):", QLineEdit.EchoMode.Password
        )
        if not accepted:
            return
        confirmation, accepted = QInputDialog.getText(
            self, "Confirmar clave", "Vuelve a escribir la nueva clave:", QLineEdit.EchoMode.Password
        )
        if not accepted or new_password != confirmation:
            QMessageBox.warning(self, "No se cambió la clave", "Las nuevas claves no coinciden.")
            return
        try:
            self.repository.change_admin_password(current, new_password)
        except ValueError as error:
            QMessageBox.warning(self, "No se cambió la clave", str(error))
            return
        QMessageBox.information(
            self, "Clave actualizada", "La clave anterior ya no permite volver a entrar al modo administrador."
        )
        self._stop_admin_session()
        self.show_page(0)

    def _selected_catalog_id(self) -> int | None:
        row = self.admin_catalog_table.currentRow()
        if row < 0:
            return None
        item = self.admin_catalog_table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def refresh_admin_catalog(self, *_args) -> None:
        if not hasattr(self, "admin_catalog_table"):
            return
        category = self.admin_category.currentData()
        items = self.repository.list_catalog(category, active_only=False)
        self.admin_catalog_table.setRowCount(len(items))
        for row, catalog_item in enumerate(items):
            value = QTableWidgetItem(catalog_item["value"])
            value.setData(Qt.ItemDataRole.UserRole, catalog_item["id"])
            state = QTableWidgetItem("Activo" if catalog_item["is_active"] else "Eliminado")
            self.admin_catalog_table.setItem(row, 0, value)
            self.admin_catalog_table.setItem(row, 1, state)
        self._update_catalog_action()

    def _update_catalog_action(self) -> None:
        if not hasattr(self, "toggle_catalog_button"):
            return
        item_id = self._selected_catalog_id()
        row = self.admin_catalog_table.currentRow()
        active = row < 0 or self.admin_catalog_table.item(row, 1).text() == "Activo"
        self.toggle_catalog_button.setText("Eliminar de la lista" if active else "Restaurar valor")
        self.toggle_catalog_button.setEnabled(item_id is not None)

    def add_catalog_item(self) -> None:
        if not self._require_admin_session():
            return
        value, accepted = QInputDialog.getText(self, "Agregar valor", "Nombre:")
        if not accepted:
            return
        try:
            self.repository.add_catalog_item(self.admin_category.currentData(), value)
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo agregar", str(error))
            return
        self.refresh_admin_catalog()
        self._refresh_form_catalogs()

    def edit_catalog_item(self) -> None:
        if not self._require_admin_session():
            return
        row = self.admin_catalog_table.currentRow()
        item_id = self._selected_catalog_id()
        if row < 0 or item_id is None:
            QMessageBox.information(self, "Selecciona un valor", "Selecciona primero un elemento de la lista.")
            return
        old_value = self.admin_catalog_table.item(row, 0).text()
        value, accepted = QInputDialog.getText(self, "Modificar valor", "Nombre:", text=old_value)
        if not accepted:
            return
        try:
            self.repository.update_catalog_item(item_id, value)
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo modificar", str(error))
            return
        self.refresh_admin_catalog()
        self._refresh_form_catalogs()

    def toggle_catalog_item(self) -> None:
        if not self._require_admin_session():
            return
        row = self.admin_catalog_table.currentRow()
        item_id = self._selected_catalog_id()
        if row < 0 or item_id is None:
            return
        active = self.admin_catalog_table.item(row, 1).text() == "Activo"
        self.repository.set_catalog_active(item_id, not active)
        self.refresh_admin_catalog()
        self._refresh_form_catalogs()

    def show_page(self, page: int) -> None:
        # Nuevo parte is outside the privileged workflow and always ends the session.
        # Search remains available during an admin session so existing reports can be corrected.
        if page == 0 and self._editing_report_id is None and self._admin_session_password:
            self._stop_admin_session()
        self.pages.setCurrentIndex(page)
        if page == 1:
            self.refresh_reports()

    @staticmethod
    def _combo_value(combo: QComboBox) -> str:
        value = combo.currentText().strip()
        if combo.currentIndex() == 0 and not combo.currentData() and value == "Seleccionar...":
            return ""
        if value == "Seleccionar...":
            return ""
        return value

    def _form_values(self) -> dict:
        return {
            "occurred_at": self.occurred_at.dateTime().toPython().astimezone().isoformat(timespec="seconds"),
            "emergency_type": self._combo_value(self.emergency_type),
            "codification": self._combo_value(self.codification),
            "address": self.address.text().strip(),
            "district": self._combo_value(self.district),
            "local_number": self.local_number.text().strip(),
            "work_description": self.work_description.toPlainText().strip(),
            "victims": self.victims.values(), "vehicles": self.vehicles.values(),
            "units": self.units.values(), "personnel": self.personnel.values(),
            "supports": self.supports.values(), "pnp_support": self.pnp_support.values(),
            "materials": self.materials.toPlainText().strip(),
            "uniformed": self.uniformed.currentText(),
            "equipment_orderly": self.equipment_orderly.currentText(),
            "logbook_recorded": self.logbook.currentText(),
            "shift_operator": self._combo_value(self.shift_operator),
            "filled_by": self.filled_by.text().strip(),
            "observations": self.observations.toPlainText().strip(),
            "signature_name": self.signature.text().strip(),
        }

    def save_report(self) -> None:
        editing = self._editing_report_id is not None
        if editing and not self._require_admin_session():
            return
        initial_directory = str(Path.home() / "Documents")
        if editing:
            current_info = self.repository.get_report_info(self._editing_report_id)
            if current_info and current_info.get("pdf_path"):
                initial_directory = str(Path(current_info["pdf_path"]).parent)
        directory = QFileDialog.getExistingDirectory(
            self,
            "Seleccionar carpeta para guardar el parte y su PDF",
            initial_directory,
            QFileDialog.Option.ShowDirsOnly,
        )
        if not directory:
            return

        change_reason = "Creación del parte"
        if editing:
            change_reason, accepted = QInputDialog.getText(
                self, "Motivo de la corrección", "Motivo (queda registrado en el historial):",
                text="Corrección administrativa",
            )
            if not accepted:
                return

        generated_pdf: Path | None = None
        try:
            values = self._form_values()
            if editing:
                report = self.service.prepare_update(self._editing_report_id, values)
                version = self.repository.next_report_version(report.id)
            else:
                report = self.service.prepare(values)
                version = 1
            safe_number = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", report.local_number).strip(" .") or report.id
            suffix = f"_v{version}" if version > 1 else ""
            output_path = Path(directory) / f"Parte_{safe_number}{suffix}.pdf"
            generated_pdf = generate_report_pdf(report, output_path, version, self.branding)
            if editing:
                version = self.repository.update_finalized_report(report, str(generated_pdf), change_reason)
            else:
                self.repository.save(report, pdf_path=str(generated_pdf), finalized=True)
        except Exception as error:
            if generated_pdf:
                generated_pdf.unlink(missing_ok=True)
            QMessageBox.warning(self, "No se pudo guardar", str(error))
            return
        self.statusBar().showMessage(f"Parte finalizado: {report.local_number}", 10000)
        if editing:
            message = (f"Se guardó la corrección como versión {version}.\n\n"
                       f"PDF: {generated_pdf}\n\nLa versión anterior se conserva.")
        else:
            message = (f"Parte guardado y finalizado: {report.local_number}\n\n"
                       f"PDF: {generated_pdf}\n\nEl parte queda bloqueado para cambios normales. Las correcciones requieren el modo administrador.")
        QMessageBox.information(self, "Parte guardado", message)
        self.clear_form()
        self.refresh_reports()

    def clear_form(self) -> None:
        was_editing = self._editing_report_id is not None
        self._editing_report_id = None
        if hasattr(self, "save_button"):
            self.save_button.setText("GUARDAR PARTE")
        self.local_number.setReadOnly(False)
        self.local_number.clear()
        self.occurred_at.setDateTime(QDateTime.currentDateTime())
        self.emergency_type.setCurrentIndex(0)
        for field in (self.address, self.filled_by, self.signature):
            field.clear()
        self.codification.setCurrentIndex(-1)
        self.codification.setEditText("")
        self.district.setCurrentIndex(0)
        self.shift_operator.setCurrentIndex(0)
        for field in (self.work_description, self.materials, self.observations):
            field.clear()
        for table in (self.victims, self.vehicles, self.units, self.personnel, self.supports, self.pnp_support):
            table.table.setRowCount(0)
            table.add_row()
        for combo in (self.uniformed, self.equipment_orderly, self.logbook):
            yes_index = combo.findText("Sí")
            combo.setCurrentIndex(yes_index if yes_index >= 0 else 0)
        if was_editing:
            self._stop_admin_session()

    def refresh_reports(self) -> None:
        if not hasattr(self, "report_table"):
            return
        results = self.repository.search(self.search_input.text() if hasattr(self, "search_input") else "")
        self.report_table.setRowCount(len(results))
        for row, report in enumerate(results):
            date_text = report["occurred_at"].replace("T", " ")[:16]
            state = "Finalizado" if report["is_finalized"] else "Guardado anterior · sin PDF"
            values = [report["local_number"], date_text, report["emergency_type"], report["address"],
                      report["district"], state]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setData(Qt.ItemDataRole.UserRole, report["id"])
                self.report_table.setItem(row, col, cell)

    def open_selected_report(self, row: int, _column: int) -> None:
        item = self.report_table.item(row, 0)
        if not item:
            return
        report = self.repository.get(item.data(Qt.ItemDataRole.UserRole))
        if not report:
            return
        report_info = self.repository.get_report_info(report.id) or {}
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Parte {report.local_number}")
        dialog.resize(980, 800)
        layout = QVBoxLayout(dialog)
        details = QTextBrowser()
        details.setOpenExternalLinks(False)
        details.setHtml(self._report_detail_html(report, report_info))
        layout.addWidget(details)
        actions = QHBoxLayout()
        pdf_path = report_info.get("pdf_path")
        if pdf_path and Path(pdf_path).is_file():
            open_pdf = QPushButton("Abrir PDF")
            open_pdf.setObjectName("primary")
            open_pdf.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(pdf_path)))
            actions.addWidget(open_pdf)
        if self._has_admin_session():
            edit = QPushButton("Modificar parte (administrador)")
            edit.clicked.connect(lambda: self._begin_report_edit(report.id, dialog))
            actions.addWidget(edit)
        actions.addStretch()
        close = QPushButton("Cerrar")
        close.clicked.connect(dialog.accept)
        actions.addWidget(close)
        layout.addLayout(actions)
        dialog.exec()

    def _report_detail_html(self, report: EmergencyReport, info: dict) -> str:
        def value(text: object) -> str:
            clean = html_escape(str(text or "").strip())
            return clean.replace("\n", "<br>") if clean else "—"

        def table(headers: list[str], keys: list[str], records: list[dict[str, str]],
                  widths: list[int] | None = None) -> str:
            head = "".join(f"<th>{html_escape(label)}</th>" for label in headers)
            colgroup = "".join(f'<col style="width:{width}%">' for width in widths or [])
            if not records:
                body = f'<tr><td colspan="{len(headers)}" class="empty">Sin registros</td></tr>'
            else:
                body = "".join("<tr>" + "".join(f"<td>{value(record.get(key, ''))}</td>" for key in keys) + "</tr>"
                               for record in records)
            table_class = ' class="weighted"' if widths else ""
            return f"<table{table_class}>{'<colgroup>' + colgroup + '</colgroup>' if colgroup else ''}<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"

        def section(title: str, content: str) -> str:
            return f'<section><h2>{html_escape(title.upper())}</h2>{content}</section>'

        occurred = report.occurred_at.replace("T", " ")[:16]
        status = "Finalizado y bloqueado" if info.get("is_finalized") else "Registro anterior, todavía sin PDF"
        general = table(
            ["Campo", "Detalle", "Campo", "Detalle"],
            ["label_1", "value_1", "label_2", "value_2"],
            [
                {"label_1": "N.º de parte", "value_1": report.local_number, "label_2": "Fecha y hora", "value_2": occurred},
                {"label_1": "Emergencia", "value_1": report.emergency_type, "label_2": "Codificación", "value_2": report.codification},
                {"label_1": "Dirección", "value_1": report.address, "label_2": "Distrito", "value_2": report.district},
            ],
        )
        institution_lines = "<br>".join(
            html_escape(self.branding[key])
            for key in ("institution_line_1", "institution_line_2", "institution_line_3")
        )
        emblem_uri = QUrl.fromLocalFile(self.branding["emblem_path"]).toString()
        pieces = [
            f'<div class="institution"><img src="{html_escape(emblem_uri)}" width="84" height="96"><br>'
            f'{institution_lines}<h1>{html_escape(self.branding["document_title"])}</h1>'
            f'{html_escape(self.branding["document_subtitle"])}</div>',
            f'<p class="status">{status}</p>',
            section("Datos generales", general),
            section("Trabajo realizado", f'<div class="text">{value(report.work_description)}</div>'),
            section("Víctimas", table(
                ["Nombres y apellidos", "DNI", "Edad", "Lesión"],
                ["nombres_y_apellidos", "dni", "edad", "lesión"], report.victims,
                [50, 20, 10, 20],
            )),
            section("Vehículos involucrados", table(["Placa", "Marca", "Modelo", "Color", "Año"], ["placa", "marca", "modelo", "color", "año"], report.vehicles)),
            section("Unidades que asistieron", table(
                ["Unidad", "Piloto", "Al mando", "KM salida", "KM ingreso", "H. salida", "H. ingreso", "SOAT", "CITV"],
                ["unidad", "piloto", "al_mando", "km_salida", "km_ingreso", "h._salida", "h._ingreso", "soat", "citv"], report.units)),
            section("Efectivos en servicio", table(["Efectivo", "Condición"], ["efectivo", "condición"], report.personnel)),
            section("Material utilizado", f'<div class="text">{value(report.materials)}</div>'),
            section("Verificaciones", table(["Verificación", "Estado"], ["label", "value"], [
                {"label": "Personal correctamente uniformado", "value": report.uniformed},
                {"label": "Material conforme, limpio y ordenado", "value": report.equipment_orderly},
                {"label": "Bitácora registrada correctamente", "value": report.logbook_recorded},
            ])),
            section("Vehículos de apoyo del CGBVP", table(["Compañía", "Unidad", "Al mando"], ["compañía", "unidad", "al_mando"], report.supports)),
            section("Apoyo PNP / otras instituciones", table(["Institución / dependencia", "Vehículo", "Al mando"], ["institución_/_dependencia", "vehículo", "al_mando"], report.pnp_support)),
        ]
        closing = table(["Campo", "Detalle"], ["label", "detail"], [
            {"label": "Centralista de turno", "detail": report.shift_operator},
            {"label": "Llenado por", "detail": report.filled_by},
            {"label": "Observaciones", "detail": report.observations},
        ])
        watermark_uri = QUrl.fromLocalFile(
            str(Path(__file__).resolve().parents[2] / "assets" / "signature-watermark.jpg")
        ).toString()
        signature_line = (
            '<table class="signature"><tr><th>FIRMA / CONFORMIDAD</th>'
            f'<td><img src="{html_escape(watermark_uri)}" width="250" height="57"></td>'
            f'<td>{value(report.signature_name)}</td></tr></table>'
        )
        pieces.append(section("Cierre del parte", closing + signature_line))
        versions = self.repository.list_report_versions(report.id)
        if versions:
            pieces.append(section("Historial de versiones", table(
                ["Versión", "Fecha de cambio", "Motivo"], ["version_number", "changed_at", "change_reason"], versions
            )))
        pieces.append('<p class="footer">Documento local · Pendiente de sincronización oficial</p>')
        style = """
        <style>
        body { font-family: 'Segoe UI', Arial, sans-serif; color: #173a58; background: #f3f6fa; font-size: 10pt; }
        .institution { text-align:center; color:#123d68; font-weight:bold; background:white; border:1px solid #b8cde0; padding:16px; line-height:1.5; }
        h1 { font-size:17pt; margin:8px 0 2px; } h2 { margin:0; padding:8px; font-size:10pt; color:#174c7f; background:#e8f3fd; border:1px solid #b8cde0; }
        section { margin:12px 0; background:white; } table { border-collapse:collapse; width:100%; background:white; }
        th,td { border:1px solid #b8cde0; text-align:left; vertical-align:top; padding:7px; }
        table.weighted { table-layout:fixed; }
        table.signature { width:100%; }
        table.signature th { width:22%; } table.signature td:nth-child(2) { width:42%; }
        th { background:#f1f6fb; color:#214c72; } .text { border:1px solid #b8cde0; padding:9px; white-space:normal; }
        .status { color:#466a88; font-size:9pt; } .empty { color:#71869a; font-style:italic; }
        .footer { border-top:1px solid #b8cde0; padding-top:8px; color:#668098; font-size:8pt; }
        </style>
        """
        return "<!doctype html><html><head><meta charset='utf-8'>" + style + "</head><body>" + "".join(pieces) + "</body></html>"

    def _begin_report_edit(self, report_id: str, dialog: QDialog) -> None:
        if not self._require_admin_session():
            dialog.reject()
            return
        report = self.repository.get(report_id)
        if not report:
            QMessageBox.warning(self, "Parte no encontrado", "El registro ya no está disponible.")
            return
        self._editing_report_id = report.id
        self.local_number.setText(report.local_number)
        self.local_number.setReadOnly(True)
        parsed_date = QDateTime.fromString(report.occurred_at, Qt.DateFormat.ISODate)
        if parsed_date.isValid():
            self.occurred_at.setDateTime(parsed_date)
        self._load_catalog_combo(self.emergency_type, "emergency_type", report.emergency_type)
        self._load_catalog_combo(self.codification, "codification", report.codification)
        self._load_catalog_combo(self.district, "district", report.district)
        self.address.setText(report.address)
        self.work_description.setPlainText(report.work_description)
        self.victims.load_values(report.victims)
        self.vehicles.load_values(report.vehicles)
        self.units.load_values(report.units)
        self.personnel.load_values(report.personnel)
        self.materials.setPlainText(report.materials)
        self.supports.load_values(report.supports)
        self.pnp_support.load_values(report.pnp_support)
        for combo, category, selected in (
            (self.uniformed, "yes_no", report.uniformed),
            (self.equipment_orderly, "yes_no", report.equipment_orderly),
            (self.logbook, "yes_no", report.logbook_recorded),
            (self.shift_operator, "shift_operator", report.shift_operator),
        ):
            self._load_catalog_combo(combo, category, selected)
        self.filled_by.setText(report.filled_by)
        self.observations.setPlainText(report.observations)
        self.signature.setText(report.signature_name)
        self.save_button.setText("GUARDAR CORRECCIÓN")
        scroll = self.pages.widget(0).findChild(QScrollArea)
        if scroll:
            scroll.verticalScrollBar().setValue(0)
        self.show_page(0)
        dialog.accept()


def apply_theme(app: QApplication) -> None:
    # Ensure Qt can resolve the institutional font when the Windows font registry
    # is unavailable to the running process (for example in an isolated desktop session).
    windows_dir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    for font_file in ("segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf"):
        font_path = windows_dir / "Fonts" / font_file
        if font_path.exists():
            QFontDatabase.addApplicationFont(str(font_path))
    app.setFont(QFont("Segoe UI", 9))
    app.setStyleSheet("""
        QWidget { font-family: 'Segoe UI'; font-size: 10pt; color: #163553; }
        QMainWindow, QWidget#centralWidget { background: #f3f6fa; }
        QWidget#header { background: #123d68; color: white; }
        QWidget#header QLabel { color: white; }
        QLabel#brandTitle { font-size: 10pt; font-weight: 800; }
        QLabel#applicationLabel { font-size: 9pt; }
        QWidget#sidebar { background: #fff; border-right: 1px solid #c9d8e5; min-width: 195px; max-width: 195px; }
        QLabel#sidebarNote { color: #668098; font-size: 8pt; border-top: 1px solid #d8e4ee; padding: 9px 6px 4px; }
        QPushButton#navButton { border: 0; text-align: left; padding: 12px 10px; color: #244e74; }
        QPushButton#navButton:hover { background: #e8f2fc; }
        QWidget#documentHeader { background: white; border: 1px solid #a9c8e4; border-radius: 5px; }
        QLabel#documentMark { background: #e8f3fd; border: 2px solid #1b5c94; border-radius: 26px; color: #174c7f; font-size: 14pt; font-weight: 900; min-width: 52px; max-width: 52px; min-height: 52px; max-height: 52px; qproperty-alignment: AlignCenter; }
        QLabel#institutionLine { color: #163d62; font-weight: 800; font-size: 10pt; }
        QLabel#documentTitle { color: #123d68; font-size: 15pt; font-weight: 900; padding-top: 5px; }
        QLabel#documentSubtitle { color: #466a88; font-size: 9pt; }
        QLabel#fieldLabel { color: #173f66; font-size: 9pt; font-weight: 800; }
        QLabel#pageTitle { font-size: 16pt; font-weight: 800; color: #174a78; padding: 4px 0; }
        QLabel#notice { background: #edf6ff; border: 1px solid #bdd6ed; border-radius: 4px; padding: 7px 9px; color: #315d82; }
        QLabel#muted { color: #627d94; }
        QFrame#section { background: white; border: 1px solid #bcd3e8; border-radius: 4px; margin: 3px 0; }
        QLabel#sectionTitle { color: #174c7f; background: #e8f3fd; border-bottom: 1px solid #c5dbee; font-weight: 800; padding: 6px 8px; }
        QLineEdit, QComboBox, QDateTimeEdit, QPlainTextEdit, QTableWidget { background: white; border: 1px solid #bdcfde; border-radius: 4px; padding: 5px; selection-background-color: #bcdcff; }
        QTableWidget { padding: 2px; }
        QHeaderView::section { background: #f1f6fb; color: #214c72; border: 0; border-bottom: 1px solid #cbdbe9; padding: 6px; font-weight: 800; font-style: italic; text-transform: uppercase; }
        QPushButton { background: white; border: 1px solid #b7cce0; border-radius: 4px; padding: 8px 12px; }
        QPushButton:hover { background: #edf5fc; }
        QPushButton#primary, QPushButton#smallPrimary { background: #176bc2; color: white; border-color: #176bc2; font-weight: 700; }
        QPushButton#smallPrimary { padding: 5px 9px; }
        QStatusBar { background: white; color: #526f88; }
    """)
