import json
import io
import matplotlib.pyplot as plt
from copy import deepcopy

from PySide6.QtCore import Qt, QStringListModel, QModelIndex, QItemSelectionModel
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QInputDialog, QMessageBox,
    QFileDialog, QDialog, QLabel, QSizePolicy, QAbstractItemView
)
from PySide6.QtGui import QPixmap

try:
    from maaf_editor.datastructures.organisation.UI.ui_singleton import UiSingleton
    from maaf_tools.datastructures.organisation.MOISEPlus.DeonticSpecification import DeonticSpecification

except:
    from maaf_editor.maaf_editor.ui_singleton import UiSingleton
    from maaf_tools.maaf_tools.datastructures.organisation.MOISEPlus.DeonticSpecification import DeonticSpecification

VISIBLE = 0
HIDDEN = 1


class DeonticSpecificationWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.ui = UiSingleton().interface

        # file and dirty state
        self.ui.current_file = None
        self.dirty = False
        self._suppress_dirty = True
        idx = self.ui.tabWidget_moise.indexOf(self.ui.tab_ds)
        self._orig_ds_tab_title = self.ui.tabWidget_moise.tabText(idx)

        # Modeless plot window placeholders
        self.plot_window = None
        self.plot_label = None

        # models
        self.model_perms = QStringListModel(self)
        self.model_obls  = QStringListModel(self)

        # wire up list views
        u = self.ui
        u.listView_ds_permissions.setModel(self.model_perms)
        u.listView_ds_obligations.setModel(self.model_obls)

        # file actions
        u.action_new_Deontic_Specification.triggered.connect(self.new_file)
        u.action_open_Deontic_Specification.triggered.connect(self.open_file)

        # permission signals
        u.pushButton_ds_add_permission.clicked.connect(self.onAddPermission)
        u.pushButton_ds_remove_permission.clicked.connect(self.onRemovePermission)
        u.listView_ds_permissions.selectionModel().currentChanged.connect(self.onPermissionSelected)
        u.comboBox_ds_permission_role_name.currentTextChanged.connect(self.onPermissionDetailChanged)
        u.comboBox_ds_permission_mission_name.currentTextChanged.connect(self.onPermissionDetailChanged)
        u.lineEdit_ds_permission_time_constraint.editingFinished.connect(self.onPermissionDetailChanged)

        # obligation signals
        u.pushButton_ds_add_obligation.clicked.connect(self.onAddObligation)
        u.pushButton_ds_remove_obligation.clicked.connect(self.onRemoveObligation)
        u.listView_ds_obligations.selectionModel().currentChanged.connect(self.onObligationSelected)
        u.comboBox_ds_obligation_role_name.currentTextChanged.connect(self.onObligationDetailChanged)
        u.comboBox_ds_obligation_mission_name.currentTextChanged.connect(self.onObligationDetailChanged)
        u.lineEdit_ds_obligation_time_constraint.editingFinished.connect(self.onObligationDetailChanged)

        # plot & verify
        u.toolButton_ds_refresh_inspection.clicked.connect(lambda: self.refreshInspection(user_triggered=True))
        u.pushButton_ds_plot.clicked.connect(self.onPlotMappings)
        u.action_plot_Deontic_Mappings.triggered.connect(self.onPlotMappings)
        u.pushButton_ds_verify.clicked.connect(self.onVerify)
        u.tabWidget_moise.currentChanged.connect(self.switchTab)

        # dirty tracking
        self.setup_dirty_tracking()

        # initial load
        if not hasattr(self.ui, 'moise_model'):
            from maaf_tools.maaf_tools.datastructures.organisation.MOISEPlus.MoiseModel import MoiseModel
            self.ui.moise_model = MoiseModel()
        self.ui.organisation.moise_model.deontic_specification = DeonticSpecification()

        # initial refresh
        self._suppress_dirty = False
        self.refreshData()

    # Permission handlers
    def refreshPermissions(self):
        ds = self.ui.organisation.moise_model.deontic_specification
        perms = [
            f"{p['role_name']} → {p['mission_name']} @ {p['time_constraint']}"
            for p in ds.permissions
        ]

        view = self.ui.listView_ds_permissions
        model = self.model_perms

        # 1) remember the old selection row (if any)
        prev_row = -1
        cur_idx = view.currentIndex()
        if cur_idx.isValid():
            prev_row = cur_idx.row()

        # 2) reset the model
        model.setStringList(perms)

        # 3) show/hide detail vs placeholder
        has = bool(perms)
        self.ui.stackedWidget_ds_permission.setCurrentIndex(VISIBLE if has else HIDDEN)

        # 4) restore selection if possible
        if perms:
            row = min(prev_row, len(perms) - 1) if prev_row >= 0 else 0
            idx = model.index(row, 0)
            sel = view.selectionModel()
            sel.clearSelection()
            view.setCurrentIndex(idx)
            sel.select(idx, QItemSelectionModel.Select | QItemSelectionModel.Rows)
            view.scrollTo(idx)
            view.setFocus()
        else:
            view.clearSelection()

    def onAddPermission(self):
        # 1) pick role
        role, ok1 = QInputDialog.getItem(
            self, "Add Permission", "Role name:",
            self.ui.organisation.moise_model.structural_specification.roles_names,
            0, False
        )
        if not (ok1 and role):
            return

        # 2) pick mission
        all_m = set(self.ui.organisation.moise_model.functional_specification.missions_names)
        used = set(self.ui.organisation.moise_model.deontic_specification
                   .get_missions_permitted_to_role(role_name=role))
        candidates = sorted(all_m - used)
        mission, ok2 = QInputDialog.getItem(
            self, "Add Permission", "Mission name:", candidates, 0, False
        )
        if not (ok2 and mission):
            return

        # 3) time constraint
        timec, ok3 = QInputDialog.getText(
            self, "Add Permission", "Time constraint:"
        )
        if not (ok3 and timec):
            return

        try:
            # add + refresh
            ds = self.ui.organisation.moise_model.deontic_specification
            ds.add_permission(role, mission, timec)

            self.refreshData(user_triggered=False)

            # auto-select the last row
            row = len(self.model_perms.stringList()) - 1
            idx = self.model_perms.index(row, 0)

            view = self.ui.listView_ds_permissions
            view.clearSelection()
            view.setCurrentIndex(idx)
            view.selectionModel().select(
                idx,
                QItemSelectionModel.Select | QItemSelectionModel.Rows
            )
            view.scrollTo(idx)
            view.setFocus()

        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def onRemovePermission(self):
        idx = self.ui.listView_ds_permissions.currentIndex().row()
        if idx < 0: return
        perm = self.ui.organisation.moise_model.deontic_specification.permissions[idx]
        self.ui.organisation.moise_model.deontic_specification.remove_permission(perm['role_name'], perm['mission_name'])

        self.refreshData(user_triggered=False)

        if self.ui.organisation.moise_model.deontic_specification.permissions:
            new = min(idx, len(self.ui.organisation.moise_model.deontic_specification.permissions) - 1)
            self.ui.listView_ds_permissions.setCurrentIndex(self.model_perms.index(new))

    def onPermissionSelected(self, current, previous):
        if self._suppress_dirty:
            return

        idx = current.row()
        u = self.ui
        ds = self.ui.organisation.moise_model.deontic_specification
        self._suppress_dirty = True

        if idx < 0:
            u.stackedWidget_ds_permission.setCurrentIndex(HIDDEN)
            u.comboBox_ds_permission_role_name.clear()
            u.comboBox_ds_permission_mission_name.clear()
            u.lineEdit_ds_permission_time_constraint.clear()
        else:
            p = ds.permissions[idx]

            # 1) refill the role combo
            u.comboBox_ds_permission_role_name.clear()
            u.comboBox_ds_permission_role_name.addItems(
                self.ui.organisation.moise_model.structural_specification.roles_names
            )
            # 2) refill the mission combo
            u.comboBox_ds_permission_mission_name.clear()
            u.comboBox_ds_permission_mission_name.addItems(
                self.ui.organisation.moise_model.functional_specification.missions_names
            )
            # 3) select the right items
            u.comboBox_ds_permission_role_name.setCurrentText(p['role_name'])
            u.comboBox_ds_permission_mission_name.setCurrentText(p['mission_name'])
            u.lineEdit_ds_permission_time_constraint.setText(p['time_constraint'])

            u.stackedWidget_ds_permission.setCurrentIndex(VISIBLE)

        self._suppress_dirty = False

    def onPermissionDetailChanged(self):
        idx = self.ui.listView_ds_permissions.currentIndex().row()
        if idx < 0: return

        p = self.ui.organisation.moise_model.deontic_specification.permissions[idx]
        p['role_name']       = self.ui.comboBox_ds_permission_role_name.currentText()
        p['mission_name']    = self.ui.comboBox_ds_permission_mission_name.currentText()
        p['time_constraint'] = self.ui.lineEdit_ds_permission_time_constraint.text()

        self.ui.listView_ds_permissions.setCurrentIndex(self.model_perms.index(idx))

        self.refreshData(user_triggered=False)

    # Obligation handlers
    def refreshObligations(self):
        ds = self.ui.organisation.moise_model.deontic_specification
        obls = [
            f"{o['role_name']} → {o['mission_name']} @ {o['time_constraint']}"
            for o in ds.obligations
        ]

        view = self.ui.listView_ds_obligations
        model = self.model_obls

        # 1) remember the old selection row (if any)
        prev_row = -1
        cur_idx = view.currentIndex()
        if cur_idx.isValid():
            prev_row = cur_idx.row()

        # 2) reset the model
        model.setStringList(obls)

        # 3) show/hide detail vs placeholder
        has = bool(obls)
        self.ui.stackedWidget_ds_obligation.setCurrentIndex(VISIBLE if has else HIDDEN)

        # 4) restore selection if possible
        if obls:
            row = min(prev_row, len(obls) - 1) if prev_row >= 0 else 0
            idx = model.index(row, 0)
            sel = view.selectionModel()
            sel.clearSelection()
            view.setCurrentIndex(idx)
            sel.select(idx, QItemSelectionModel.Select | QItemSelectionModel.Rows)
            view.scrollTo(idx)
            view.setFocus()
        else:
            view.clearSelection()

    def onAddObligation(self):
        # 1) pick role
        role, ok1 = QInputDialog.getItem(
            self, "Add Obligation", "Role name:",
            self.ui.organisation.moise_model.structural_specification.roles_names,
            0, False
        )
        if not (ok1 and role):
            return

        # 2) pick mission
        all_m = set(self.ui.organisation.moise_model.functional_specification.missions_names)
        used = set(self.ui.organisation.moise_model.deontic_specification
                   .get_missions_obligated_to_role(role_name=role))
        candidates = sorted(all_m - used)
        mission, ok2 = QInputDialog.getItem(
            self, "Add Obligation", "Mission name:", candidates, 0, False
        )
        if not (ok2 and mission):
            return

        # 3) time constraint
        timec, ok3 = QInputDialog.getText(
            self, "Add Obligation", "Time constraint:"
        )
        if not (ok3 and timec):
            return

        try:
            # add + refresh obligations
            ds = self.ui.organisation.moise_model.deontic_specification
            ds.add_obligation(role, mission, timec)

            self.refreshData(user_triggered=False)

            # auto-select the last row
            row = len(self.model_obls.stringList()) - 1
            idx = self.model_obls.index(row, 0)

            view = self.ui.listView_ds_obligations
            view.clearSelection()
            view.setCurrentIndex(idx)
            view.selectionModel().select(
                idx,
                QItemSelectionModel.Select | QItemSelectionModel.Rows
            )
            view.scrollTo(idx)
            view.setFocus()

        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def onRemoveObligation(self):
        idx = self.ui.listView_ds_obligations.currentIndex().row()
        if idx < 0: return
        o = self.ui.organisation.moise_model.deontic_specification.obligations[idx]
        self.ui.organisation.moise_model.deontic_specification.remove_obligation(o['role_name'], o['mission_name'])

        self.refreshData(user_triggered=False)

        if self.ui.organisation.moise_model.deontic_specification.obligations:
            new = min(idx, len(self.ui.organisation.moise_model.deontic_specification.obligations) - 1)
            self.ui.listView_ds_obligations.setCurrentIndex(self.model_obls.index(new))

    def onObligationSelected(self, current: QModelIndex, previous: QModelIndex):
        idx = current.row()
        u   = self.ui
        ds  = self.ui.organisation.moise_model.deontic_specification
        self._suppress_dirty = True

        # hide if nothing selected
        if idx < 0:
            u.stackedWidget_ds_obligation.setCurrentIndex(HIDDEN)
            u.comboBox_ds_obligation_role_name.clear()
            u.comboBox_ds_obligation_mission_name.clear()
            u.lineEdit_ds_obligation_time_constraint.clear()
        else:
            o = ds.obligations[idx]

            # 1) repopulate role list
            u.comboBox_ds_obligation_role_name.clear()
            u.comboBox_ds_obligation_role_name.addItems(
                self.ui.organisation.moise_model.structural_specification.roles_names
            )

            # 2) repopulate mission list
            u.comboBox_ds_obligation_mission_name.clear()
            u.comboBox_ds_obligation_mission_name.addItems(
                self.ui.organisation.moise_model.functional_specification.missions_names
            )

            # 3) set them to the current values
            u.comboBox_ds_obligation_role_name.setCurrentText(o['role_name'])
            u.comboBox_ds_obligation_mission_name.setCurrentText(o['mission_name'])
            u.lineEdit_ds_obligation_time_constraint.setText(o['time_constraint'])

            u.stackedWidget_ds_obligation.setCurrentIndex(VISIBLE)

        self._suppress_dirty = False

    def onObligationDetailChanged(self):
        if self._suppress_dirty:
            return

        idx = self.ui.listView_ds_obligations.currentIndex().row()
        if idx < 0: return

        o = self.ui.organisation.moise_model.deontic_specification.obligations[idx]
        o['role_name']       = self.ui.comboBox_ds_obligation_role_name.currentText()
        o['mission_name']    = self.ui.comboBox_ds_obligation_mission_name.currentText()
        o['time_constraint'] = self.ui.lineEdit_ds_obligation_time_constraint.text()

        self.ui.listView_ds_obligations.setCurrentIndex(self.model_obls.index(idx))

        self.refreshData(user_triggered=False)

    # --- Verify & inspect ---
    def onVerify(self):
        errors = []
        for i, p in enumerate(self.ui.organisation.moise_model.deontic_specification.permissions):
            if not p['role_name'] or not p['mission_name']:
                errors.append(f"Permission #{i+1} incomplete")
        for i, o in enumerate(self.ui.organisation.moise_model.deontic_specification.obligations):
            if not o['role_name'] or not o['mission_name']:
                errors.append(f"Obligation #{i+1} incomplete")

        if errors:
            QMessageBox.information(self, "Verify", "Errors:\n" + "\n".join(errors))
        else:
            QMessageBox.information(self, "Verify", "Specification is valid.")

    def refreshInspection(self, user_triggered=False):
        # If user triggered it, update current_raw_view
        if user_triggered:
            self.ui.current_raw_view = "ds"

        if self.ui.current_raw_view != "ds":
            return  # Don't execute if triggered by signal and not in "ds" view

        raw = json.dumps(self.ui.organisation.moise_model.deontic_specification.asdict(), indent=2)
        self.ui.plainTextEdit_raw.setPlainText(raw)

    def switchTab(self, index):
        if self.ui.tabWidget_moise.indexOf(self.ui.tab_ds) == index:
            self.refreshInspection(user_triggered=True)

    # Plot mappings
    def onPlotMappings(self):
        """
        Opens or updates a modeless window showing the structure graph.
        """
        # create dialog+label on first click
        if self.plot_window is None:
            self.plot_window = QDialog(self)
            self.plot_window.setWindowTitle("Deontic Mappings")
            self.plot_window.setModal(False)
            self.plot_window.setMinimumSize(200, 200)
            self.plot_label = AspectRatioLabel()
            layout = QVBoxLayout(self.plot_window)
            layout.addWidget(self.plot_label)

        # now it exists → render & show
        self.update_plot_window()
        self.plot_window.show()

    def update_plot_window(self):
        # ensure the dialog + label exist
        if self.plot_window is None:
            return

        # 1) Generate the figure without blocking
        try:
            fig = self.ui.organisation.moise_model.plot_mappings(display_plot=False)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to plot mappings:\n{e}")
            return

        # 2) Render to a PNG in memory
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150)
        plt.close(fig)
        buf.seek(0)

        pix = QPixmap()
        pix.loadFromData(buf.read())
        self.plot_label.setPixmap(pix)

    # ---------- File I/O & Dirty State ----------
    def setup_dirty_tracking(self):
        u = self.ui

        # Buttons → clicked
        for btn in (
                u.pushButton_ds_add_permission,
                u.pushButton_ds_remove_permission,
                u.pushButton_ds_add_obligation,
                u.pushButton_ds_remove_obligation
        ):
            btn.clicked.connect(self.mark_dirty)

        # ComboBoxes → currentTextChanged
        for cb in (
                u.comboBox_ds_permission_role_name,
                u.comboBox_ds_permission_mission_name,
                u.comboBox_ds_obligation_role_name,
                u.comboBox_ds_obligation_mission_name
        ):
            cb.currentTextChanged.connect(self.mark_dirty)

        # LineEdits → editingFinished
        for le in (
                u.lineEdit_ds_permission_time_constraint,
                u.lineEdit_ds_obligation_time_constraint
        ):
            le.editingFinished.connect(self.mark_dirty)

    def mark_dirty(self):
        if self._suppress_dirty:
            return
        if not self.dirty:
            self.dirty = True

    def update_title(self):
        suffix = "*" if self.dirty else ""
        idx = self.ui.tabWidget_moise.indexOf(self.ui.tab_ds)
        self.ui.tabWidget_moise.setTabText(idx, f"{self._orig_ds_tab_title}{suffix}")
        self.ui.label_ds_file_name.setText(self.ui.current_file or "…")

    def new_file(self, user_triggered = True):
        if self.dirty:
            resp = QMessageBox.question(
                self, "Unsaved Changes",
                "Save before creating new?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            if resp == QMessageBox.Cancel:
                return
            if resp == QMessageBox.Yes and not self.save_file():
                return

        self._suppress_dirty = True
        try:
            self.ui.organisation.moise_model.deontic_specification = DeonticSpecification()
            self.ui.current_file = None
            self.dirty = False
            self.refreshData(user_triggered=user_triggered)

            idx = self.ui.tabWidget.indexOf(self.ui.tab_ds)
            if idx != -1:
                self.ui.tabWidget.setCurrentIndex(idx)

        finally:
            self._suppress_dirty = False

    def open_file(self):
        if self.dirty:
            resp = QMessageBox.question(
                self, "Unsaved Changes",
                "Save before opening?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            if resp == QMessageBox.Cancel:
                return
            if resp == QMessageBox.Yes and not self.save_file():
                return

        path, _ = QFileDialog.getOpenFileName(
            self, "Open Deontic Spec", "", "Deontic Specification Files (*.ds);;JSON Files (*.json);;All Files (*)"
        )
        if not path:
            return

        try:
            self._suppress_dirty = True

            with open(path, 'r') as f:
                data = json.load(f)

            self.ui.organisation.moise_model.deontic_specification = DeonticSpecification(
                deontic_specification=data,
                structural_specification=None,
                functional_specification=None
            )
            self.ui.current_file = path
            self.dirty = False
            self.refreshData(user_triggered=True)

            # switch to the FS tab
            idx = self.ui.tabWidget.indexOf(self.ui.tab_ds)
            if idx != -1:
                self.ui.tabWidget.setCurrentIndex(idx)


        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to open:\n{e}")

        finally:
            self._suppress_dirty = False

    def save_file(self) -> bool:
        path = deepcopy(self.ui.current_file)

        if not path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Deontic Specification As", "", "Deontic Specification Files (*.ds);;JSON Files (*.json);;All Files (*)"
            )
            if not path:
                return False

        try:
            self.ui.organisation.save_to_file(
                filename=path,
                organisation=False,
                role_allocation=False,
                model=False,
                structural_specification=False,
                functional_specification=False,
                deontic_specification=True,
                allocation_specification=False
            )

            self.dirty = False
            self.refreshData()
            return True

        except Exception as e:
            QMessageBox.warning(self, "Error", f"Save failed:\n{e}")
            return False

    # ---------- UI Refresh ----------
    def refreshData(self, user_triggered=False):
        print("Refresh DS")
        self._suppress_dirty = True
        try:
            self.refreshPermissions()
            self.refreshObligations()

            self.refreshInspection(user_triggered=user_triggered)
            self.update_title()
            self.update_plot_window()

            if len(self.ui.organisation.moise_model.structural_specification.roles) < 1 or len(self.ui.organisation.moise_model.functional_specification.missions) < 1:
                self.ui.stackedWidget_ds_editor.setCurrentIndex(HIDDEN)
            else:
                self.ui.stackedWidget_ds_editor.setCurrentIndex(VISIBLE)
        finally:
            self._suppress_dirty = False


class AspectRatioLabel(QLabel):
    """A QLabel that always scales its pixmap with Qt.KeepAspectRatio."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._orig_pixmap = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def setPixmap(self, pixmap: QPixmap):
        self._orig_pixmap = pixmap
        self._update_scaled()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._update_scaled()

    def _update_scaled(self):
        if not self._orig_pixmap:
            return
        scaled = self._orig_pixmap.scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        super().setPixmap(scaled)
