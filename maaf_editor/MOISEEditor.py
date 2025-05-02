# main.py
import sys
import json
import os
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QFileDialog, QMessageBox, QDialog, QVBoxLayout, QLabel, QCheckBox, QFrame, QDialogButtonBox
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile
from PySide6.QtGui import QIcon
from copy import deepcopy

try:
    from maaf_editor.widget_Fleet_Config import FleetConfigWidget
    from maaf_editor.widget_Role_Allocation_Specification import RoleAllocationWidget
    from maaf_editor.widget_Functional_Specification import FunctionalSpecWidget
    from maaf_editor.widget_Structural_Specification import StructuralSpecificationWidget
    from maaf_editor.widget_Deontic_Specification import DeonticSpecificationWidget
    from maaf_editor.ui_singleton import UiSingleton

    from maaf_tools.datastructures.organisation.Organisation import Organisation
    from maaf_tools.datastructures.organisation.MOISEPlus.MoiseModel import MoiseModel

except:
    from maaf_editor.maaf_editor.widget_Fleet_Config import FleetConfigWidget
    from maaf_editor.maaf_editor.widget_Role_Allocation_Specification import RoleAllocationWidget
    from maaf_editor.maaf_editor.widget_Functional_Specification import FunctionalSpecWidget
    from maaf_editor.maaf_editor.widget_Structural_Specification import StructuralSpecificationWidget
    from maaf_editor.maaf_editor.widget_Deontic_Specification import DeonticSpecificationWidget
    from maaf_editor.maaf_editor.ui_singleton import UiSingleton

    from maaf_tools.maaf_tools.datastructures.organisation.Organisation import Organisation
    from maaf_tools.maaf_tools.datastructures.organisation.MOISEPlus.MoiseModel import MoiseModel

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # --- load the main UI ---
        # Load UI singleton
        self.ui = UiSingleton().interface
        self.setCentralWidget(self.ui)

        self.ui.organisation = Organisation()
        self.ui.moise_model = self.ui.organisation.moise_model

        # -> Add shared flags
        self.ui.current_raw_view = None
        self.ui.current_file = None
        self.ui.save_modes = {
            "organisation": True,
            "moise_model": False,
            "role_allocation": False,
            "structural_specification": False,
            "functional_specification": False,
            "deontic_specification": False,
        }

        self.ui.fc_widget = FleetConfigWidget()
        self.ui.ra_widget = RoleAllocationWidget()
        self.ui.ds_widget = DeonticSpecificationWidget()
        self.ui.ss_widget = StructuralSpecificationWidget()
        self.ui.fs_widget = FunctionalSpecWidget()

        # --- forward the File menu actions ---
        self.ui.actionSave.triggered.connect(self.saveModel)
        self.ui.actionSave_as.triggered.connect(self.saveModelAs)

        self.ui.action_open_Moise_Model.triggered.connect(self.open_MOISE_file)
        self.ui.action_open_Organisation.triggered.connect(self.open_ORGANISATION_file)

        self.ui.action_new_Moise_Model.triggered.connect(self.resetMoise)
        self.ui.action_new_Organisation.triggered.connect(self.resetAll)

        self.ui.action_show_Raw_Config_Panel.triggered.connect(lambda: self.ui.dockWidget_RAW.setVisible(True))

        self.setWindowTitle("MOISEPlus GUI")
        path = os.path.join(os.path.dirname(__file__), "MOISE_GUI.png")
        self.ui.setWindowIcon(QIcon(path))

        # Add methods to ui to be accessible to widgets
        self.ui.saveModel = self.saveModel
        self.ui.saveModelAs = self.saveModelAs
        self.ui.resetAll = self.resetAll

        self.ui.action_Refresh_all.triggered.connect(self.refreshAll)
        #self.open_ORGANISATION_file(path="/home/vguillet/ros2_ws/src/icare_alloc_config/icare_alloc_config/icare_team.org")

    def refreshAll(self):
        self.ui.fc_widget.refreshData()
        self.ui.ra_widget.refreshData()
        self.ui.ss_widget.refreshData()
        self.ui.fs_widget.refreshData()
        self.ui.ds_widget.refreshData()

    def resetAll(self):
        self.ui.organisation.reset_all()

        self.ui.fc_widget.new_file()
        self.ui.ra_widget.new_file()
        self.resetMoise()

    def resetMoise(self):
        self.ui.ss_widget.new_file()
        self.ui.fs_widget.new_file()
        self.ui.ds_widget.new_file()

    @property
    def dirty(self):
        fc_dirty = self.ui.fc_widget.dirty
        ra_dirty = self.ui.ra_widget.dirty
        ss_dirty = self.ui.ss_widget.dirty
        fs_dirty = self.ui.fs_widget.dirty
        ds_dirty = self.ui.ds_widget.dirty

        return fc_dirty or ra_dirty or ss_dirty or fs_dirty or ds_dirty

    def open_ORGANISATION_file(self):
        # offer to save if dirty
        if self.dirty:
            resp = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Save before opening?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            if resp == QMessageBox.Yes and not self.ui.saveModel():
                return
            if resp == QMessageBox.Cancel:
                return

        path, _ = QFileDialog.getOpenFileName(
                self, "Open Organisation Model", "", "Organisation Files (*.org);;JSON Files (*.json);;All Files (*)"
            )

        if not path or path is None:
            return

        # load the JSON and replace your FS object
        with open(path, 'r') as f:
            data = json.load(f)

        self.ui.organisation = Organisation(data=data)
        self.ui.current_file = path

        try:
            # load the JSON and replace your FS object
            with open(path, 'r') as f:
                data = json.load(f)

            self.ui.organisation = Organisation(data=data)
            self.ui.current_file = path

            self._reload_widgets()

            QMessageBox.information(self, "Success", "Organisation Loaded Successfully")

        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to open file:\n{e}")

    def open_MOISE_file(self):
        # offer to save if dirty
        if self.dirty:
            resp = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Save before opening?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            if resp == QMessageBox.Yes and not self.ui.saveModel():
                return
            if resp == QMessageBox.Cancel:
                return

        path, _ = QFileDialog.getOpenFileName(
            self, "Open Moise+ Model", "", "Moise+ Files (*.moise);;JSON Files (*.json);;All Files (*)"
        )
        if not path:
            return

        try:
            # load the JSON and replace your FS object
            with open(path, 'r') as f:
                data = json.load(f)

            self.ui.organisation.moise_model = MoiseModel(data=data)
            self.ui.current_file = path

            self._reload_widgets()

        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to open file:\n{e}")

    def _reload_widgets(self):
        try:
            # suppress dirty-tracking during load & rebuild UI
            # FC
            self.ui.fc_widget._suppress_dirty = True
            self.ui.fc_widget.dirty = False
            self.ui.fc_widget.refreshData()

            # SS
            self.ui.ss_widget._suppress_dirty = True
            self.ui.ss_widget.dirty = False
            self.ui.ss_widget.refreshData()

            # FS
            self.ui.fs_widget._suppress_dirty = True
            self.ui.fs_widget.dirty = False
            self.ui.fs_widget.refreshData()

            # DS
            self.ui.ds_widget._suppress_dirty = True
            self.ui.ds_widget.dirty = False
            self.ui.ds_widget.refreshData()

        finally:
            # re-enable dirty tracking
            self.ui.ss_widget._suppress_dirty = False
            self.ui.fs_widget._suppress_dirty = False
            self.ui.ds_widget._suppress_dirty = False

    def saveModel(self) -> bool:
        if not self.ui.current_file:
            return self.saveModelAs()

        # ——— Proceed with saving ———
        try:
            path = deepcopy(self.ui.current_file)

            self.ui.organisation.save_to_file(
                filename=path,
                organisation=self.ui.save_modes["organisation"],
                role_allocation=self.ui.save_modes["role_allocation"],
                model=self.ui.save_modes["moise_model"],
                structural_specification=self.ui.save_modes["structural_specification"],
                functional_specification=self.ui.save_modes["functional_specification"],
                deontic_specification=self.ui.save_modes["deontic_specification"],
                allocation_specification=False

            )

            if self.ui.save_modes["organisation"]:
                self.ui.fc_widget.dirty = False
                self.ui.fc_widget.update_title()

                self.ui.ss_widget.dirty = False
                self.ui.ss_widget.update_title()

                self.ui.fs_widget.dirty = False
                self.ui.fs_widget.update_title()

                self.ui.ds_widget.dirty = False
                self.ui.ds_widget.update_title()

            if self.ui.save_modes["moise_model"]:
                self.ui.ss_widget.dirty = False
                self.ui.ss_widget.update_title()

                self.ui.fs_widget.dirty = False
                self.ui.fs_widget.update_title()

                self.ui.ds_widget.dirty = False
                self.ui.ds_widget.update_title()

            if self.ui.save_modes["role_allocation"]:
                self.ui.ra_widget.dirty = False
                self.ui.ra_widget.update_title()

            if self.ui.save_modes["structural_specification"]:
                self.ui.ss_widget.dirty = False
                self.ui.ss_widget.update_title()

            if self.ui.save_modes["functional_specification"]:
                self.ui.fs_widget.dirty = False
                self.ui.fs_widget.update_title()

            if self.ui.save_modes["deontic_specification"]:
                self.ui.ds_widget.dirty = False
                self.ui.ds_widget.update_title()

            return True

        except Exception as e:
            # handle/log error as needed
            print(f"Error saving model: {e}")
            return False

    def saveModelAs(self) -> bool:
        # ——— Ask user which files to save ———
        dlg = QDialog(self)
        dlg.setWindowTitle("Save Options")
        layout = QVBoxLayout(dlg)

        label = QLabel("Select which config files to save:", dlg)
        layout.addWidget(label)

        cb_organisation = QCheckBox("Organisation Model (.org)", dlg)
        cb_organisation.setChecked(self.ui.save_modes.get("organisation", True))
        layout.addWidget(cb_organisation)

        cb_moise = QCheckBox("Moise Model (.moise)", dlg)
        cb_moise.setChecked(self.ui.save_modes.get("moise_model", True))
        layout.addWidget(cb_moise)

        line = QFrame(dlg)
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        cb_ra = QCheckBox("Role Allocation (.ra)", dlg)
        cb_ra.setChecked(self.ui.save_modes.get("role_allocation", True))
        layout.addWidget(cb_ra)

        line = QFrame(dlg)
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        cb_ss = QCheckBox("Structural Specification (.ss)", dlg)
        cb_ss.setChecked(self.ui.save_modes.get("structural_specification", False))
        layout.addWidget(cb_ss)

        cb_fs = QCheckBox("Functional Specification (.fs)", dlg)
        cb_fs.setChecked(self.ui.save_modes.get("functional_specification", False))
        layout.addWidget(cb_fs)

        cb_ds = QCheckBox("Deontic Specification (.ds)", dlg)
        cb_ds.setChecked(self.ui.save_modes.get("deontic_specification", False))
        layout.addWidget(cb_ds)

        buttonBox = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            dlg
        )
        layout.addWidget(buttonBox)
        buttonBox.accepted.connect(dlg.accept)
        buttonBox.rejected.connect(dlg.reject)

        if dlg.exec() != QDialog.Accepted:
            # User cancelled
            return False

        # Update save modes based on user choice
        self.ui.save_modes["organisation"] = cb_organisation.isChecked()
        self.ui.save_modes["moise_model"] = cb_moise.isChecked()
        self.ui.save_modes["role_allocation"] = cb_ra.isChecked()
        self.ui.save_modes["structural_specification"] = cb_ss.isChecked()
        self.ui.save_modes["functional_specification"] = cb_fs.isChecked()
        self.ui.save_modes["deontic_specification"] = cb_ds.isChecked()

        path, _ = QFileDialog.getSaveFileName(
            self, "Save As", "", "Organisation Files (*.org);;MOISEPlus Files (*.moise);;JSON Files (*.json);;All Files (*)"
        )

        if not path:
            return False

        self.ui.current_file = path

        return self.saveModel()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
