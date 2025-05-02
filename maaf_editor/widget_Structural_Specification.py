import json
import os
import io
from copy import deepcopy

import matplotlib.pyplot as plt
from PySide6.QtCore import Qt, QStringListModel, QModelIndex, QTimer, QSignalBlocker, QItemSelectionModel
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QDialog, QSizePolicy, QHeaderView,
    QInputDialog, QMessageBox, QApplication, QFileDialog, QTableWidgetItem, QAbstractItemView
)
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtGui import QIcon
from PySide6.QtGui import QPixmap

try:
    from maaf_editor.ui_singleton import UiSingleton
    from maaf_tools.datastructures.organisation.MOISEPlus.StructuralSpecification import StructuralSpecification

except:
    from maaf_editor.maaf_editor.ui_singleton import UiSingleton
    from maaf_tools.maaf_tools.datastructures.organisation.MOISEPlus.StructuralSpecification import StructuralSpecification

HIDDEN = 1
VISIBLE = 0

RELATIONS = ["acquaintance", "communication", "authority", "compatible", "couple"]
SCOPES = ["inter", "intra", "omni"]

class StructuralSpecificationWidget(QWidget):
    def __init__(self):
        super().__init__()

        # Load UI
        self.ui = UiSingleton().interface

        sb = self.ui.spinBox_ss_subgroup_max
        sb.setMinimum(0)
        sb.setMaximum(9999)  # or whatever hard cap
        sb.setSpecialValueText("Unlimited")  # when value()==0 Qt shows “Unlimited”

        grp_sb = self.ui.spinBox_ss_group_role_cardinality_max
        grp_sb.setMinimum(0)
        grp_sb.setMaximum(9999)
        grp_sb.setSpecialValueText("Unlimited")

        # Window state
        self.ui.current_file = None
        self.dirty = False
        self._suppress_dirty = True
        idx = self.ui.tabWidget_moise.indexOf(self.ui.tab_ss)
        self._orig_fs_tab_title = self.ui.tabWidget_moise.tabText(idx)

        # Modeless plot window placeholders
        self.plot_window = None
        self.plot_label = None

        self.last_subgroup_min_value = 0
        self.last_group_role_min_value = 0
        self.last_subgroup_max_value = 0
        self.last_group_role_max_value = 0

        # List models
        self.model_roles = QStringListModel(self)
        self.model_groups = QStringListModel(self)
        self.model_subgroups = QStringListModel(self)
        self.model_group_roles = QStringListModel(self)

        self.model_relations = QStandardItemModel(0, 4, self)
        self.model_relations.setHorizontalHeaderLabels(["Source", "Destination", "Type", "Scope"])

        # Assign models to views
        u = self.ui
        u.listView_ss_roles.setModel(self.model_roles)
        u.listView_ss_groups.setModel(self.model_groups)
        u.listView_ss_group_subgroups.setModel(self.model_subgroups)
        u.listView_ss_group_role_cardinality.setModel(self.model_group_roles)
        u.tableView_ss_role_relations.setModel(self.model_relations)

        for view in (
                u.tableView_ss_role_relations,
        ):
            # Horizontal header: disable resizing & moving
            h = view.horizontalHeader()
            h.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            h.setSectionsMovable(False)

            # Vertical header: disable resizing & moving
            v = view.verticalHeader()
            v.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            v.setSectionsMovable(False)

        # Connect signals
        self._connect_role_signals()
        self._connect_relation_signals()
        self._connect_group_signals()

        u.toolButton_ss_refresh_inspection.clicked.connect(lambda: self.refreshInspection(user_triggered=True))
        u.pushButton_ss_plot_structure.clicked.connect(self.onPlotStructure)
        u.action_plot_Structural_Organisation.triggered.connect(self.onPlotStructure)
        u.pushButton_ss_verify.clicked.connect(self.onVerify)
        u.tabWidget_moise.currentChanged.connect(self.switchTab)

        # File menu actions
        u.action_new_Structural_Specification.triggered.connect(self.new_file)
        u.action_open_Structural_Specification.triggered.connect(self.open_file)

        # Dirty tracking
        self.setup_dirty_tracking()

        # Initialize UI
        self.refreshData()

        self._reset_all_detail_panels()

        self._suppress_dirty = False
        self.dirty = False
        self.update_title()

    # ----------------- Signal Setup -----------------
    def _connect_role_signals(self):
        u = self.ui
        u.pushButton_ss_add_role.clicked.connect(self.onAddRole)
        u.pushButton_ss_remove_role.clicked.connect(self.onRemoveRole)
        u.listView_ss_roles.selectionModel().currentChanged.connect(self.onRoleSelected)
        u.lineEdit_ss_role_description.editingFinished.connect(self.onRoleDescriptionChanged)
        u.checkBox_ss_role_abstract.toggled.connect(self.onRoleAbstractToggled)
        u.comboBox_ss_role_inherits.currentTextChanged.connect(self.onRoleInheritsChanged)

    def _connect_relation_signals(self):
        u = self.ui
        u.pushButton_ss_add_relation.clicked.connect(self.onAddRelation)
        u.pushButton_ss_remove_relation.clicked.connect(self.onRemoveRelation)
        u.tableView_ss_role_relations.selectionModel().currentChanged.connect(self.onRelationSelected)
        u.comboBox_ss_relation_source.currentTextChanged.connect(self.onRelationSourceChanged)
        u.comboBox_ss_relation_destination.currentTextChanged.connect(self.onRelationDestinationChanged)
        u.comboBox_ss_relation_type.currentTextChanged.connect(self.onRelationTypeChanged)
        u.comboBox_ss_relation_scope.currentTextChanged.connect(self.onRelationScopeChanged)

    def _connect_group_signals(self):
        u = self.ui
        u.pushButton_ss_add_group.clicked.connect(self.onAddGroup)
        u.pushButton_ss_remove_group.clicked.connect(self.onRemoveGroup)
        u.listView_ss_groups.selectionModel().currentChanged.connect(self.onGroupSelected)
        u.lineEdit_ss_group_description.editingFinished.connect(self.onGroupDescriptionChanged)
        # Subgroups

        u.pushButton_ss_add_subgroup.clicked.connect(self.onAddSubgroup)
        u.pushButton_ss_remove_subgroup.clicked.connect(self.onRemoveSubgroup)
        u.listView_ss_group_subgroups.selectionModel().currentChanged.connect(self.onSubgroupSelected)
        u.spinBox_ss_subgroup_min.valueChanged.connect(self.onSubgroupMinChanged)
        u.spinBox_ss_subgroup_max.valueChanged.connect(self.onSubgroupMaxChanged)
        # Role cardinality
        u.pushButton_ss_add_group_role_cardinality.clicked.connect(self.onAddGroupRole)
        u.pushButton_ss_remove_group_role_cardinality.clicked.connect(self.onRemoveGroupRole)
        u.listView_ss_group_role_cardinality.selectionModel().currentChanged.connect(self.onGroupRoleSelected)
        u.comboBox_ss_group_role_cardinality_role.currentTextChanged.connect(self.onGroupRoleRoleChanged)
        u.spinBox_ss_group_role_cardinality_min.valueChanged.connect(self.onGroupRoleMinChanged)
        u.spinBox_ss_group_role_cardinality_max.valueChanged.connect(self.onGroupRoleMaxChanged)

    # ----- Roles -----
    def refreshRoles(self):
        # 1) remember the old selection in the list view
        view = self.ui.listView_ss_roles
        model = self.model_roles
        prev_role = None
        cur_idx = view.currentIndex()
        if cur_idx.isValid():
            prev_role = model.data(cur_idx, Qt.DisplayRole)

        # 2) remember the old "inherits" combobox value
        combo = self.ui.comboBox_ss_role_inherits
        prev_inherit = combo.currentText()

        # 3) rebuild the roles list
        roles = list(self.ui.organisation.moise_model.structural_specification.roles.keys())
        model.setStringList(roles)

        # 4) restore list selection (or default to first, or clear)
        if roles:
            if prev_role in roles:
                row = roles.index(prev_role)
            else:
                row = 0
            new_idx = model.index(row, 0)
            view.setCurrentIndex(new_idx)
        else:
            view.clearSelection()

        # 5) repopulate the "inherits" combobox
        combo.blockSignals(True)
        combo.clear()
        combo.addItems([""] + roles)

        # 6) restore its selection (or default to the empty entry)
        inherit_idx = combo.findText(prev_inherit)
        combo.setCurrentIndex(inherit_idx if inherit_idx != -1 else 0)
        combo.blockSignals(False)

        self.ui.ra_widget.refreshData()

    def onAddRole(self):
        name, ok = QInputDialog.getText(self, "Add Role", "Role name:")
        if not ok or not name:
            return
        desc, ok2 = QInputDialog.getText(self, "Add Role", "Description:")
        if not ok2:
            return
        try:
            self.ui.organisation.moise_model.structural_specification.add_role(name=name, description=desc)
            self.refreshData()

            idx = self.model_roles.stringList().index(name)
            self.ui.listView_ss_roles.setCurrentIndex(self.model_roles.index(idx))

        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def onRemoveRole(self):
        name = self.ui.listView_ss_roles.currentIndex().data()
        if not name:
            return
        try:
            self.ui.organisation.moise_model.structural_specification.remove_role(name)

            self.refreshData()

        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def onRoleSelected(self, current: QModelIndex, previous: QModelIndex):
        name = current.data()
        if not name:
            self.ui.stackedWidget_ss_role.setCurrentIndex(HIDDEN)
            # Clear fields without firing any signals
            with QSignalBlocker(self.ui.lineEdit_ss_role_description):
                self.ui.lineEdit_ss_role_description.clear()
            with QSignalBlocker(self.ui.checkBox_ss_role_abstract):
                self.ui.checkBox_ss_role_abstract.setChecked(False)
            with QSignalBlocker(self.ui.comboBox_ss_role_inherits):
                self.ui.comboBox_ss_role_inherits.setCurrentIndex(0)
            return
        # Show the detail pane
        self.ui.stackedWidget_ss_role.setCurrentIndex(VISIBLE)

        role = self.ui.organisation.moise_model.structural_specification.get_role(name)
        # Populate fields silently
        with QSignalBlocker(self.ui.lineEdit_ss_role_description):
            self.ui.lineEdit_ss_role_description.setText(role.get("description", ""))
        with QSignalBlocker(self.ui.checkBox_ss_role_abstract):
            self.ui.checkBox_ss_role_abstract.setChecked(role.get("abstract", False))
        inherits = role.get("inherits") or ""
        with QSignalBlocker(self.ui.comboBox_ss_role_inherits):
            self.ui.comboBox_ss_role_inherits.setCurrentText(inherits)

    def onRoleDescriptionChanged(self):
        name = self.ui.listView_ss_roles.currentIndex().data()
        if name:
            self.ui.organisation.moise_model.structural_specification.roles[name]["description"] = self.ui.lineEdit_ss_role_description.text()

        self.refreshData()

    def onRoleAbstractToggled(self, checked: bool):
        name = self.ui.listView_ss_roles.currentIndex().data()
        if name:
            self.ui.organisation.moise_model.structural_specification.roles[name]["abstract"] = checked

            self.refreshData()

    def onRoleInheritsChanged(self, text: str):
        name = self.ui.listView_ss_roles.currentIndex().data()
        if name:
            self.ui.organisation.moise_model.structural_specification.roles[name]["inherits"] = text or None

            self.refreshData()

    # ----- Relations -----
    def refreshRelations(self):
        view = self.ui.tableView_ss_role_relations  # adjust to the actual view name
        model = self.model_relations

        # 1) Remember the previously selected row by its full data
        prev_idx = view.currentIndex()
        prev_data = None
        if prev_idx.isValid():
            r = prev_idx.row()
            prev_data = [model.item(r, c).text() for c in range(model.columnCount())]

        # 2) Clear and refill the model
        model.removeRows(0, model.rowCount())
        for rel in self.ui.organisation.moise_model.structural_specification.role_relations:
            items = [
                QStandardItem(rel['source']),
                QStandardItem(rel['destination']),
                QStandardItem(rel['type']),
                QStandardItem(rel['scope']),
            ]
            for item in items:
                item.setEditable(False)
            model.appendRow(items)

        # 3) Restore selection if possible
        row_count = model.rowCount()
        if row_count:
            # Try to find the same row data
            target_row = None
            if prev_data is not None:
                for r in range(row_count):
                    row_data = [model.item(r, c).text() for c in range(model.columnCount())]
                    if row_data == prev_data:
                        target_row = r
                        break
            # Fallback: keep the same index if still in range, else pick first
            if target_row is None:
                if prev_idx.isValid() and prev_idx.row() < row_count:
                    target_row = prev_idx.row()
                else:
                    target_row = 0

            new_idx = model.index(target_row, 0)
            view.setCurrentIndex(new_idx)
            view.selectionModel().select(
                new_idx,
                QItemSelectionModel.Select | QItemSelectionModel.Rows
            )
        else:
            view.clearSelection()

        # 4) Update the "detail" combo-boxes
        roles = list(self.ui.organisation.moise_model.structural_specification.roles.keys())
        for cb in (
                self.ui.comboBox_ss_relation_source,
                self.ui.comboBox_ss_relation_destination
        ):
            cb.blockSignals(True)
            cb.clear()
            cb.addItems(roles)
            cb.blockSignals(False)

        self.ui.comboBox_ss_relation_type.blockSignals(True)
        self.ui.comboBox_ss_relation_type.clear()
        self.ui.comboBox_ss_relation_type.addItems(RELATIONS)
        self.ui.comboBox_ss_relation_type.blockSignals(False)

        self.ui.comboBox_ss_relation_scope.blockSignals(True)
        self.ui.comboBox_ss_relation_scope.clear()
        self.ui.comboBox_ss_relation_scope.addItems(SCOPES)
        self.ui.comboBox_ss_relation_scope.blockSignals(False)

    def onAddRelation(self):
        if not self.ui.organisation.moise_model.structural_specification.roles:
            QMessageBox.warning(self, "Error", "No Roles defined")
            return
        elif len(self.ui.organisation.moise_model.structural_specification.roles) < 2:
            QMessageBox.warning(self, "Error", "At least two Roles must be defined")
            return

        src, ok1 = QInputDialog.getItem(self, "Add Relation", "Source Role:", self.ui.organisation.moise_model.structural_specification.roles_names, 0, False)
        if not ok1: return

        dst, ok2 = QInputDialog.getItem(self, "Add Relation", "Destination Role:", set(self.ui.organisation.moise_model.structural_specification.roles_names) - set([src]), 0, False)
        if not ok2: return
        typ, ok3 = QInputDialog.getItem(self, "Add Relation", "Type:", RELATIONS, 0, False)
        if not ok3: return
        scope, ok4 = QInputDialog.getItem(self, "Add Relation", "Scope:", SCOPES, 0, False)
        if not ok4: return
        try:
            self.ui.organisation.moise_model.structural_specification.add_role_relation(src, dst, typ, scope)

            self.refreshData()

            last_row = self.model_relations.rowCount() - 1
            if last_row >= 0:
                idx = self.model_relations.index(last_row, 0)
                self.ui.tableView_ss_role_relations.setCurrentIndex(idx)

        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def onRemoveRelation(self):
        idx = self.ui.tableView_ss_role_relations.currentIndex().row()
        if idx < 0:
            return
        rel = self.ui.organisation.moise_model.structural_specification.role_relations[idx]
        try:
            self.ui.organisation.moise_model.structural_specification.remove_role_relation(rel['source'], rel['destination'], rel['type'], rel['scope'])

            self.refreshData()

        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def onRelationSelected(self, current: QModelIndex, previous: QModelIndex):
        row = current.row()
        if row < 0:
            # hide detail pane…
            self.ui.stackedWidget_ss_relation.setCurrentIndex(HIDDEN)
            return

        self.ui.stackedWidget_ss_relation.setCurrentIndex(VISIBLE)
        rel = self.ui.organisation.moise_model.structural_specification.role_relations[row]
        with QSignalBlocker(self.ui.comboBox_ss_relation_source):
            self.ui.comboBox_ss_relation_source.setCurrentText(rel['source'])
        with QSignalBlocker(self.ui.comboBox_ss_relation_destination):
            self.ui.comboBox_ss_relation_destination.setCurrentText(rel['destination'])
        with QSignalBlocker(self.ui.comboBox_ss_relation_type):
            self.ui.comboBox_ss_relation_type.setCurrentText(rel['type'])
        with QSignalBlocker(self.ui.comboBox_ss_relation_scope):
            self.ui.comboBox_ss_relation_scope.setCurrentText(rel['scope'])

    def onRelationSourceChanged(self, text: str):
        idx = self.ui.tableView_ss_role_relations.currentIndex()
        row = idx.row()
        if row < 0: return

        # 1) update data
        rel = self.ui.organisation.moise_model.structural_specification.role_relations[row]
        rel['source'] = text
        # 2) update table cell
        self.model_relations.item(row, 0).setText(text)
        # 3) reselect to avoid jumping
        self.ui.tableView_ss_role_relations.selectRow(row)

        self.refreshData()

    def onRelationDestinationChanged(self, text: str):
        idx = self.ui.tableView_ss_role_relations.currentIndex()
        row = idx.row()
        if row < 0:
            return
        rel = self.ui.organisation.moise_model.structural_specification.role_relations[row]
        rel['destination'] = text
        self.model_relations.item(row, 1).setText(text)
        self.ui.tableView_ss_role_relations.selectRow(row)

        self.refreshData()

    def onRelationTypeChanged(self, text: str):
        idx = self.ui.tableView_ss_role_relations.currentIndex()
        row = idx.row()
        if row < 0:
            return
        rel = self.ui.organisation.moise_model.structural_specification.role_relations[row]
        rel['type'] = text
        self.model_relations.item(row, 2).setText(text)
        self.ui.tableView_ss_role_relations.selectRow(row)

        self.refreshData()

    def onRelationScopeChanged(self, text: str):
        idx = self.ui.tableView_ss_role_relations.currentIndex()
        row = idx.row()
        if row < 0:
            return
        rel = self.ui.organisation.moise_model.structural_specification.role_relations[row]
        rel['scope'] = text
        self.model_relations.item(row, 3).setText(text)
        self.ui.tableView_ss_role_relations.selectRow(row)

        self.refreshData()

    # ----- Groups -----
    def refreshGroups(self):
        view = self.ui.listView_ss_groups
        model = self.model_groups

        # 1) remember the old selection text (if any)
        prev_text = None
        cur_idx = view.currentIndex()
        if cur_idx.isValid():
            prev_text = model.data(cur_idx, Qt.DisplayRole)

        # 2) rebuild the list
        names = list(self.ui.organisation.moise_model.structural_specification.groups.keys())
        model.setStringList(names)

        # 3) restore selection if possible, else first row, else clear
        if names:
            if prev_text in names:
                row = names.index(prev_text)
            else:
                row = 0
            new_idx = model.index(row, 0)
            view.setCurrentIndex(new_idx)
        else:
            view.clearSelection()

    def onAddGroup(self):
        name, ok1 = QInputDialog.getText(self, "Add Group", "Group name:")
        if not ok1 or not name:
            return
        desc, ok2 = QInputDialog.getText(self, "Add Group", "Description:")
        if not ok2:
            return

        try:
            self.ui.organisation.moise_model.structural_specification.add_group(name=name, description=desc)

            self.refreshData()

            # auto-select the new row
            row = self.model_groups.stringList().index(name)
            idx = self.model_groups.index(row, 0)
            self.ui.listView_ss_groups.setCurrentIndex(idx)

        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def onRemoveGroup(self):
        name = self.ui.listView_ss_groups.currentIndex().data()
        if not name:
            return
        try:
            self.ui.organisation.moise_model.structural_specification.remove_group(name)

            self.refreshData()

        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def onGroupSelected(self, current: QModelIndex, previous: QModelIndex):
        name = current.data()
        u = self.ui

        # suppress dirty‐marking during UI rebuild
        self._suppress_dirty = True
        try:
            # no group selected → clear everything
            if not name:
                u.stackedWidget_ss_group.setCurrentIndex(HIDDEN)
                with QSignalBlocker(u.lineEdit_ss_group_description), \
                        QSignalBlocker(u.spinBox_ss_subgroup_min), \
                        QSignalBlocker(u.spinBox_ss_subgroup_max):
                    u.lineEdit_ss_group_description.clear()
                    self.model_subgroups.setStringList([])
                    self.model_group_roles.setStringList([])
                return

            # show the group editor
            u.stackedWidget_ss_group.setCurrentIndex(VISIBLE)

            # 1) description
            group = self.ui.organisation.moise_model.structural_specification.get_group(name)
            with QSignalBlocker(u.lineEdit_ss_group_description):
                u.lineEdit_ss_group_description.setText(group.get('description', ''))

            # 2) subgroups
            subs = list(group.get('subgroups', {}).keys())
            self.model_subgroups.setStringList(subs)
            if subs:
                idx = self.model_subgroups.index(0)
                u.listView_ss_group_subgroups.setCurrentIndex(idx)
            else:
                u.listView_ss_group_subgroups.selectionModel().clearSelection()
                u.stackedWidget_ss_subgroup.setCurrentIndex(HIDDEN)
                with QSignalBlocker(u.spinBox_ss_subgroup_min), \
                        QSignalBlocker(u.spinBox_ss_subgroup_max):
                    u.spinBox_ss_subgroup_min.setValue(0)
                    u.spinBox_ss_subgroup_max.setValue(0)

            # 3) group‐role cardinalities
            cards = list(group.get('role_cardinality', {}).keys())
            self.model_group_roles.setStringList(cards)
            if cards:
                idx2 = self.model_group_roles.index(0)
                u.listView_ss_group_role_cardinality.setCurrentIndex(idx2)

        finally:
            # re-enable dirty‐tracking
            self._suppress_dirty = False

    def onGroupDescriptionChanged(self):
        name = self.ui.listView_ss_groups.currentIndex().data()
        if name:
            self.ui.organisation.moise_model.structural_specification.groups[name]['description'] = self.ui.lineEdit_ss_group_description.text()

            self.refreshData()

    def onAddSubgroup(self):
        group_name = self.ui.listView_ss_groups.currentIndex().data()

        all_groups = set(self.ui.organisation.moise_model.structural_specification.groups_names)
        existing_subs = set(self.ui.organisation.moise_model.structural_specification.groups[group_name].get('subgroups', {}).keys())
        candidates = sorted(all_groups - existing_subs - {group_name})

        # 2) if nothing left to add, inform the user and bail out
        if not candidates:
            QMessageBox.information(
                self,
                "Add Subgroup",
                f"No more groups available to add as subgroups to “{group_name}.”"
            )
            return

        sub, ok = QInputDialog.getItem(self, "Add Subgroup", "Select subgroup:", candidates, 0, False)
        if not (ok and sub): return

        self.ui.organisation.moise_model.structural_specification.groups[group_name].setdefault('subgroups', {})[sub] = {'min': 0, 'max': None}

        self.refreshData()

        self.onGroupSelected(self.ui.listView_ss_groups.currentIndex(), None)
        subs = self.model_subgroups.stringList()
        row = subs.index(sub)
        idx = self.model_subgroups.index(row, 0)
        self.ui.listView_ss_group_subgroups.setCurrentIndex(idx)

    def onRemoveSubgroup(self):
        group_name = self.ui.listView_ss_groups.currentIndex().data()
        sub = self.ui.listView_ss_group_subgroups.currentIndex().data()
        if group_name and sub:
            self.ui.organisation.moise_model.structural_specification.groups[group_name]['subgroups'].pop(sub, None)
            self.onGroupSelected(self.ui.listView_ss_groups.currentIndex(), None)

        self.refreshData()

    def onSubgroupSelected(self, current: QModelIndex, previous: QModelIndex):
        group_name = self.ui.listView_ss_groups.currentIndex().data()
        sub = current.data()

        # suppress dirty‐marking while we adjust the UI
        self._suppress_dirty = True
        try:
            if group_name and sub:
                self.ui.stackedWidget_ss_subgroup.setCurrentIndex(VISIBLE)
                card = self.ui.organisation.moise_model.structural_specification.groups[group_name]['subgroups'][sub]

                # block spin‐box signals while setting values
                with QSignalBlocker(self.ui.spinBox_ss_subgroup_min), \
                     QSignalBlocker(self.ui.spinBox_ss_subgroup_max):
                    self.ui.spinBox_ss_subgroup_min.setValue(card.get('min', 0))
                    self.ui.spinBox_ss_subgroup_max.setValue(card.get('max') or 0)
            else:
                self.ui.stackedWidget_ss_subgroup.setCurrentIndex(HIDDEN)
                # reset spin‐boxes under blocker
                with QSignalBlocker(self.ui.spinBox_ss_subgroup_min), \
                     QSignalBlocker(self.ui.spinBox_ss_subgroup_max):
                    self.ui.spinBox_ss_subgroup_min.setValue(0)
                    self.ui.spinBox_ss_subgroup_max.setValue(0)
        finally:
            # re-enable dirty‐tracking
            self._suppress_dirty = False

    def onSubgroupMinChanged(self, val: int):
        grp = self.ui.listView_ss_groups.currentIndex().data()
        sub = self.ui.listView_ss_group_subgroups.currentIndex().data()
        if not (grp and sub):
            return

        card = self.ui.organisation.moise_model.structural_specification.groups[grp]['subgroups'][sub]
        old_max = card.get('max', None)

        # If the last max value is not zero or None and new min exceeds last_max, bump max
        if old_max is not None and old_max != 0 and val > self.last_subgroup_max_value:
            card['max'] = val
            self.ui.spinBox_ss_subgroup_max.setValue(val)

        # Update the last known min value and store it
        self.last_subgroup_min_value = val
        card['min'] = val

        # If max is None (“Unlimited”) or zero, leave it as “Unlimited” in the UI
        if old_max is None or old_max == 0:
            # Represent unlimited as 0 internally, with suffix
            self.ui.spinBox_ss_subgroup_max.setValue(0)
            self.ui.spinBox_ss_subgroup_max.setSuffix(" (Unlimited)")

        self.refreshData()

    def onSubgroupMaxChanged(self, val: int):
        grp = self.ui.listView_ss_groups.currentIndex().data()
        sub = self.ui.listView_ss_group_subgroups.currentIndex().data()
        if not (grp and sub):
            return

        card = self.ui.organisation.moise_model.structural_specification.groups[grp]['subgroups'][sub]
        min_val = card.get('min', 0)

        # 0 ⇒ unlimited
        if val == 0:
            card['max'] = None
            self.ui.spinBox_ss_subgroup_max.setSuffix(" (Unlimited)")
            self.last_subgroup_max_value = 0

        elif val >= min_val:
            # OK, max ≥ min
            card['max'] = val
            self.ui.spinBox_ss_subgroup_max.setSuffix("")
            self.last_subgroup_max_value = val

        elif self.last_subgroup_max_value == 0:
            # previously unlimited, now clamped to min
            card['max'] = min_val
            self.ui.spinBox_ss_subgroup_max.setSuffix("")
            self.last_subgroup_max_value = min_val

        else:
            # too small and previously finite: reset to “Unlimited”
            card['max'] = 0
            self.ui.spinBox_ss_subgroup_max.setValue(0)
            self.ui.spinBox_ss_subgroup_max.setSuffix(" (Unlimited)")
            self.last_subgroup_max_value = 0

        # Finally, reflect the actual max (if not None) back into the spinbox
        real_max = card.get('max', 0)
        if real_max is not None:
            self.ui.spinBox_ss_subgroup_max.setValue(real_max)

        self.refreshData()

    def onAddGroupRole(self):
        if not self.ui.organisation.moise_model.structural_specification.roles:
            QMessageBox.warning(self, "Error", "No Roles defined")
            return

        grp_name = self.ui.listView_ss_groups.currentIndex().data()
        if not grp_name:
            return

        all_roles = set(self.ui.organisation.moise_model.structural_specification.roles_names)
        existing = set(self.ui.organisation.moise_model.structural_specification.groups[grp_name].get('role_cardinality', {}).keys())
        candidates = sorted(all_roles - existing)

        # 4) if nothing left to add, inform & bail
        if not candidates:
            QMessageBox.information(
                self,
                "Add Group Role",
                f"No more roles available to add to “{grp_name}.”"
            )
            return

        role_name, ok = QInputDialog.getItem(self, "Add Group Role", "Enter role name:", candidates, 0, False)

        if ok and role_name:
            # Ensure you add the role to the group
            self.ui.organisation.moise_model.structural_specification.groups[grp_name].setdefault('role_cardinality', {})[role_name] = {'min': 0, 'max': None}

            self.refreshData()

            self.onGroupSelected(self.ui.listView_ss_groups.currentIndex(), None)

            roles = self.model_group_roles.stringList()
            row = roles.index(role_name)
            idx = self.model_group_roles.index(row, 0)
            self.ui.listView_ss_group_role_cardinality.setCurrentIndex(idx)

    def onRemoveGroupRole(self):
        grp_name = self.ui.listView_ss_groups.currentIndex().data()
        role_name = self.ui.listView_ss_group_role_cardinality.currentIndex().data()
        if not grp_name or not role_name:
            return
        try:
            # Remove the role from the group's role_cardinality
            del self.ui.organisation.moise_model.structural_specification.groups[grp_name]['role_cardinality'][role_name]
            # Refresh the group details to reflect the changes
            self.onGroupSelected(self.ui.listView_ss_groups.currentIndex(), None)

            self.refreshData()

        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to remove group role: {e}")

    def onGroupRoleSelected(self, current, previous):
        grp = self.ui.listView_ss_groups.currentIndex().data()
        role = current.data()
        if not (grp and role):
            self.ui.stackedWidget_ss_group_role_cardinality_detail.setCurrentIndex(HIDDEN)
            return
        else:
            self.ui.stackedWidget_ss_group_role_cardinality_detail.setCurrentIndex(VISIBLE)

        card = self.ui.organisation.moise_model.structural_specification.groups[grp]['role_cardinality'][role]

        roles = list(self.ui.organisation.moise_model.structural_specification.roles.keys())
        self.ui.comboBox_ss_group_role_cardinality_role.blockSignals(True)
        self.ui.comboBox_ss_group_role_cardinality_role.clear()
        self.ui.comboBox_ss_group_role_cardinality_role.addItems(roles)
        self.ui.comboBox_ss_group_role_cardinality_role.blockSignals(False)

        # 1) Block the role‐combo signals while we set it
        with QSignalBlocker(self.ui.comboBox_ss_group_role_cardinality_role):
            self.ui.comboBox_ss_group_role_cardinality_role.setCurrentText(role)

        # 2) Block the spin‐boxes
        with QSignalBlocker(self.ui.spinBox_ss_group_role_cardinality_min):
            self.ui.spinBox_ss_group_role_cardinality_min.setValue(card.get('min', 0))
        with QSignalBlocker(self.ui.spinBox_ss_group_role_cardinality_max):
            val = card.get('max')
            self.ui.spinBox_ss_group_role_cardinality_max.setValue(val or 0)

        # 3) make sure the “(Unlimited)” suffix matches the actual stored value
        if card.get('max') is None:
            self.ui.spinBox_ss_group_role_cardinality_max.setSuffix(" (Unlimited)")
        else:
            self.ui.spinBox_ss_group_role_cardinality_max.setSuffix("")

        # 3) Now sync your trackers (no slots will fire)
        self.last_group_role_min_value = card.get('min', 0)
        self.last_group_role_max_value = card.get('max') or 0

    def onGroupRoleRoleChanged(self, text: str):
        grp_name = self.ui.listView_ss_groups.currentIndex().data()
        old_role_name = self.ui.listView_ss_group_role_cardinality.currentIndex().data()
        if grp_name and old_role_name and text:
            # Update the role name in the group’s role_cardinality
            role_cardinality = self.ui.organisation.moise_model.structural_specification.groups[grp_name]['role_cardinality'].pop(old_role_name)
            self.ui.organisation.moise_model.structural_specification.groups[grp_name]['role_cardinality'][text] = role_cardinality
            self.onGroupSelected(self.ui.listView_ss_groups.currentIndex(), None)

            self.refreshData()

    def onGroupRoleMinChanged(self, val: int):
        grp_name = self.ui.listView_ss_groups.currentIndex().data()
        role_name = self.ui.listView_ss_group_role_cardinality.currentIndex().data()
        if not (grp_name and role_name):
            return

        card = self.ui.organisation.moise_model.structural_specification.groups[grp_name]['role_cardinality'][role_name]
        old_max = card.get('max', None)

        # If the last max was finite and new min exceeds it, bump max to match
        if old_max is not None and old_max != 0 and val > self.last_group_role_max_value:
            card['max'] = val
            self.ui.spinBox_ss_group_role_cardinality_max.setValue(val)

        # Store the new min
        self.last_group_role_min_value = val
        card['min'] = val

        # If max was None (Unlimited) or zero, show “0 (Unlimited)” in the UI
        if old_max is None or old_max == 0:
            self.ui.spinBox_ss_group_role_cardinality_max.setValue(0)
            self.ui.spinBox_ss_group_role_cardinality_max.setSuffix(" (Unlimited)")

        self.refreshData()

    def onGroupRoleMaxChanged(self, val: int):
        grp = self.ui.listView_ss_groups.currentIndex().data()
        role_name = self.ui.listView_ss_group_role_cardinality.currentIndex().data()
        if not (grp and role_name):
            return

        card = self.ui.organisation.moise_model.structural_specification.groups[grp]['role_cardinality'][role_name]
        min_val = card.get('min', 0)

        if val == 0:
            # 0 ⇒ Unlimited
            card['max'] = None
            self.ui.spinBox_ss_group_role_cardinality_max.setSuffix(" (Unlimited)")
            self.last_group_role_max_value = 0

        elif val >= min_val:
            # Legitimate new max ≥ min
            card['max'] = val
            self.ui.spinBox_ss_group_role_cardinality_max.setSuffix("")
            self.last_group_role_max_value = val

        elif self.last_group_role_max_value == 0:
            # Was unlimited → clamp up to min
            card['max'] = min_val
            self.ui.spinBox_ss_group_role_cardinality_max.setSuffix("")
            self.last_group_role_max_value = min_val

        else:
            # Tried to shrink below previous finite max → reset to Unlimited
            card['max'] = 0
            self.ui.spinBox_ss_group_role_cardinality_max.setValue(0)
            self.ui.spinBox_ss_group_role_cardinality_max.setSuffix(" (Unlimited)")
            self.last_group_role_max_value = 0

        # Finally mirror the stored max (or 0) back into the spinbox
        real_max = card.get('max', 0)
        if real_max is not None:
            self.ui.spinBox_ss_group_role_cardinality_max.setValue(real_max)

        self.refreshData()

    # --- Verify & inspect ---
    def onVerify(self):
        errors = self.ui.organisation.moise_model.structural_specification.check_specification_definition(self.ui.organisation.moise_model.structural_specification, stop_at_first_error=False, verbose=0, return_errors=True)
        if not errors:
            QMessageBox.information(self, "Verify", "Specification is valid.")
        else:
            QMessageBox.information(self, "Verify", "Specification has errors:\n" + "\n".join(errors))

    def refreshInspection(self, user_triggered=False):
        #self.update_plot_window()

        # If user triggered it, update current_raw_view
        if user_triggered:
            self.ui.current_raw_view = "ss"

        if not user_triggered and self.ui.current_raw_view != "ss":
            return  # Don't execute if triggered by signal and not in "ss" view

        raw = json.dumps(self.ui.organisation.moise_model.structural_specification.asdict(), indent=2)
        self.ui.plainTextEdit_raw.setPlainText(raw)

    def switchTab(self, index):
        if self.ui.tabWidget_moise.indexOf(self.ui.tab_ss) == index:
            self.refreshInspection(user_triggered=True)

    def onPlotStructure(self):
        """
        Opens or updates a modeless window showing the structure graph.
        """
        # create dialog+label on first click
        if self.plot_window is None:
            self.plot_window = QDialog(self)
            self.plot_window.setWindowTitle("Structure Graph")
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
            fig = self.ui.organisation.moise_model.structural_specification.plot_structure_graph(display_plot=False)

        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to plot Structure:\n{e}")
            return

        # 2) Render to a PNG in memory
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150)
        plt.close(fig)
        buf.seek(0)
        img_data = buf.read()
        buf.close()
        fig.clf()

        # 3) Load into a QPixmap
        pix = QPixmap()
        pix.loadFromData(img_data)

        # 4) Update pixmap and show
        self.plot_label.setPixmap(pix)

    # ---------- File I/O & Dirty State ----------
    def setup_dirty_tracking(self):
        u = self.ui
        # Structural edits
        buttons = [
            u.pushButton_ss_add_role, u.pushButton_ss_remove_role,
            u.pushButton_ss_add_relation, u.pushButton_ss_remove_relation,
            u.pushButton_ss_add_group, u.pushButton_ss_remove_group,
            u.pushButton_ss_add_subgroup, u.pushButton_ss_remove_subgroup,
            u.pushButton_ss_add_group_role_cardinality, u.pushButton_ss_remove_group_role_cardinality
        ]
        for btn in buttons:
            btn.clicked.connect(self.mark_dirty)

        # Content edits
        u.lineEdit_ss_role_description.editingFinished.connect(self.mark_dirty)
        u.checkBox_ss_role_abstract.toggled.connect(self.mark_dirty)
        u.comboBox_ss_role_inherits.currentTextChanged.connect(self.mark_dirty)
        u.comboBox_ss_relation_source.currentTextChanged.connect(self.mark_dirty)
        u.comboBox_ss_relation_destination.currentTextChanged.connect(self.mark_dirty)
        u.comboBox_ss_relation_type.currentTextChanged.connect(self.mark_dirty)
        u.comboBox_ss_relation_scope.currentTextChanged.connect(self.mark_dirty)
        u.lineEdit_ss_group_description.editingFinished.connect(self.mark_dirty)
        u.spinBox_ss_subgroup_min.valueChanged.connect(self.mark_dirty)
        u.spinBox_ss_subgroup_max.valueChanged.connect(self.mark_dirty)
        u.comboBox_ss_group_role_cardinality_role.currentTextChanged.connect(self.mark_dirty)
        u.spinBox_ss_group_role_cardinality_min.valueChanged.connect(self.mark_dirty)
        u.spinBox_ss_group_role_cardinality_max.valueChanged.connect(self.mark_dirty)

    def mark_dirty(self):
        if self._suppress_dirty:
            return
        if not self.dirty:
            self.dirty = True

        if len(self.ui.organisation.moise_model.structural_specification.roles) < 2:
            self.ui.stackedWidget_ss_role_relations.setCurrentIndex(HIDDEN)
        else:
            self.ui.stackedWidget_ss_role_relations.setCurrentIndex(VISIBLE)

    def update_title(self):
        suffix = "*" if self.dirty else ""
        idx = self.ui.tabWidget_moise.indexOf(self.ui.tab_ss)
        self.ui.tabWidget_moise.setTabText(idx, f"{self._orig_fs_tab_title}{suffix}")

        if self.ui.current_file:
            # if we've opened or saved to a real path, show it
            self.ui.label_ss_file_name.setText(self.ui.current_file)
        else:
            # never saved yet → just show an ellipsis
            self.ui.label_ss_file_name.setText("…")

    def _reset_all_detail_panels(self):
        pairs = [
            (self.ui.listView_ss_roles, self.onRoleSelected),
            (self.ui.tableView_ss_role_relations, self.onRelationSelected),
            (self.ui.listView_ss_groups, self.onGroupSelected),
            (self.ui.listView_ss_group_subgroups, self.onSubgroupSelected),
            (self.ui.listView_ss_group_role_cardinality, self.onGroupRoleSelected),
        ]
        for view, handler in pairs:
            view.clearSelection()
            handler(QModelIndex(), QModelIndex())

    def new_file(self):
        # if there are unsaved edits, offer to save first
        if self.dirty:
            resp = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Save before creating new?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            if resp == QMessageBox.Yes and not self.ui.saveModel():
                return
            if resp == QMessageBox.Cancel:
                return

        # suppress any mark_dirty() until the new file is fully loaded
        self._suppress_dirty = True
        try:
            # create fresh spec
            self.ui.organisation.moise_model.structural_specification = StructuralSpecification()
            self.ui.current_file = None

            # clear dirty flag & rebuild UI
            self.dirty = False
            self.refreshData(user_triggered=True)
            self._reset_all_detail_panels()

            idx = self.ui.tabWidget_moise.indexOf(self.ui.tab_ss)
            if idx != -1:
                self.ui.tabWidget_moise.setCurrentIndex(idx)


        finally:
            # re-enable dirty tracking
            self._suppress_dirty = False

    def open_file(self):
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
            self, "Open Structural Specification", "", "Structural Specification Files (*.ss);;JSON Files (*.json);;All Files (*)"
        )
        if not path:
            return

        try:
            # suppress *all* mark_dirty() calls until we're done
            self._suppress_dirty = True

            # load file
            with open(path, 'r') as f:
                data = json.load(f)

            self.ui.organisation.moise_model.structural_specification = StructuralSpecification(data)
            self.ui.current_file = path

            # reset dirty state & update UI models
            self.dirty = False
            self.refreshData(user_triggered=True)

            # Reset deontic specification
            self.ui.ds_widget.new_file(user_triggered=False)

            idx = self.ui.tabWidget_moise.indexOf(self.ui.tab_ss)
            if idx != -1:
                self.ui.tabWidget_moise.setCurrentIndex(idx)

        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to open file:\n{e}")

        finally:
            # re-enable dirty tracking
            self._suppress_dirty = False

    def save_file(self) -> bool:
        path = deepcopy(self.ui.current_file)

        if not path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Structural Specification As", "", "Structural Specification Files (*.ss);;JSON Files (*.json);;All Files (*)"
            )
            if not path:
                return False

        try:
            self.ui.organisation.save_to_file(
                filename=path,
                organisation=False,
                role_allocation=False,
                model=False,
                structural_specification=True,
                functional_specification=False,
                deontic_specification=False,
                allocation_specification=False
            )

            self.dirty = False
            self.refreshData()  # Update title to reflect the saved state
            return True

        except Exception as e:
            QMessageBox.warning(self, "Error", f"Save failed:\n{e}")
            return False

    # ---------- UI Refresh ----------
    def refreshData(self, user_triggered=False):
        """Refresh all lists to ensure the data is loaded properly."""
        print("Refresh SS")
        self._suppress_dirty = True
        try:
            self.refreshRoles()
            self.refreshRelations()
            self.refreshGroups()

            if len(self.ui.organisation.moise_model.structural_specification.roles) < 2:
                self.ui.stackedWidget_ss_role_relations.setCurrentIndex(HIDDEN)
            else:
                self.ui.stackedWidget_ss_role_relations.setCurrentIndex(VISIBLE)

            self.refreshInspection(user_triggered=user_triggered)
            self.update_title()
            self.update_plot_window()

            self.ui.ds_widget.refreshData()
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

    def minimumSizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(0, 0)
