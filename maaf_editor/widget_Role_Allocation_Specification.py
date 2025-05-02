import json
import io
import os

import matplotlib.pyplot as plt

from PySide6.QtCore import Qt, QStringListModel, QModelIndex, QItemSelectionModel, QSignalBlocker, QSize, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QInputDialog, QMessageBox, QToolTip,
    QFileDialog, QDialog, QLabel, QSizePolicy, QAbstractItemView, QHeaderView
)
from PySide6.QtGui import QStandardItemModel, QStandardItem, QPixmap, QIcon, QCursor

try:
    from maaf_editor.ui_singleton import UiSingleton
    from maaf_tools.datastructures.organisation.RoleAllocation import RoleAllocation

except:
    from maaf_editor.maaf_editor.ui_singleton import UiSingleton
    from maaf_tools.maaf_tools.datastructures.organisation.RoleAllocation import RoleAllocation


VISIBLE = 0
HIDDEN = 1

class RoleAllocationWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.ui = UiSingleton().interface

        # file & dirty state
        self.ui.current_file = None
        self.dirty = False
        self._suppress_dirty = True
        idx = self.ui.tabWidget_moise.indexOf(self.ui.tab_ra)
        self._orig_tab_title = self.ui.tabWidget_moise.tabText(idx)

        # modeless plot placeholders
        self.plot_window = None
        self.plot_label = None

        # Assets
        self.class_image_dir = "maaf_editor/maaf_editor/Assets"
        self.default_image = os.path.join(self.class_image_dir, "wall-e.png")
        self.max_image_size = QSize(200, 200)
        self.ui.label_fc_class_image.setMaximumSize(self.max_image_size)

        self.instances_icon_size = QSize(28, 28)
        self.ui.tableView_ra_agents.setIconSize(self.instances_icon_size)

        # models
        self.model_groups      = QStandardItemModel(self)
        self.model_overview    = QStandardItemModel(self)
        self.model_agents      = QStandardItemModel(self)
        self.model_assignments = QStringListModel(self)
        self.model_roles       = QStringListModel(self)

        # wire up views & tables
        u = self.ui
        u.tableView_ra_groups.setModel(self.model_groups)
        u.tableView_ra_fleet_overview.setModel(self.model_overview)
        u.tableView_ra_agents.setModel(self.model_agents)
        u.listView_ra_assignments.setModel(self.model_assignments)
        u.listView_ra_assignment_roles.setModel(self.model_roles)

        for view in (
                u.tableView_ra_groups,
                u.tableView_ra_fleet_overview,
                u.tableView_ra_agents
        ):
            # Horizontal header: disable resizing & moving
            h = view.horizontalHeader()
            h.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            h.setSectionsMovable(False)

            # Vertical header: disable resizing & moving
            v = view.verticalHeader()
            v.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            v.setSectionsMovable(False)

        # file actions
        u.action_new_Role_Allocation.triggered.connect(self.new_file)
        u.action_open_Role_Allocation.triggered.connect(self.open_file)
        u.toolButton_ra_refresh_inspection.clicked.connect(lambda: self.refreshInspection(user_triggered=True))
        u.pushButton_2.clicked.connect(self.onVerify)  # "Verify" button
        u.tabWidget_moise.currentChanged.connect(self.switchTab)

        # group signals
        u.pushButton_ra_add_group.clicked.connect(self.onAddGroup)
        u.pushButton_ra_remove_group.clicked.connect(self.onRemoveGroup)
        u.tableView_ra_groups.selectionModel().currentChanged.connect(self.onGroupSelected)
        u.comboBox_ra_group_type.currentTextChanged.connect(self.onGroupTypeChanged)
        u.comboBox_ra_group_parent.currentTextChanged.connect(self.onGroupParentChanged)

        u.tableView_ra_fleet_overview.selectionModel().currentChanged.connect(self.onOverviewSelected)

        # agent signals
        u.tableView_ra_agents.selectionModel().currentChanged.connect(self.onAgentSelected)

        # assignment signals
        u.listView_ra_assignments.selectionModel().currentChanged.connect(self.onAssignmentSelected)
        u.pushButton_ra_add_assignment.clicked.connect(self.onAddAssignment)
        u.pushButton_ra_remove_assignment.clicked.connect(self.onRemoveAssignment)

        # role‐within‐assignment signals
        u.pushButton_ra_assignment_add_role.clicked.connect(self.onAddRole)
        u.pushButton_ra_assignment_remove_role.clicked.connect(self.onRemoveRole)

        # plot
        u.pushButton_ra_plot_fleet_organisation.clicked.connect(self.onPlotFleetOrganisation)
        u.action_plot_Fleet_Organisation.triggered.connect(self.onPlotFleetOrganisation)

        # dirty tracking
        self.setup_dirty_tracking()

        # initial load
        if not hasattr(self.ui, 'organisation') or not hasattr(self.ui.organisation, 'role_allocation'):
            QMessageBox.warning(self, "Error", "No organisation loaded for role allocation.")
            return

        self._suppress_dirty = False
        self.refreshData()

    def refreshOverview(self):
        # (re-)enable mouse tracking in case this is called later
        tv = self.ui.tableView_ra_fleet_overview
        tv.setMouseTracking(True)
        tv.viewport().setMouseTracking(True)

        overview = self.ui.organisation.role_allocation.get_overview()
        per_group = overview["groups"]
        global_counts = overview["global_role_counts"]
        global_agents = overview["global_role_agents"]

        roles   = sorted(global_counts.keys())
        headers = ["Type", "Parent", "Num. Agents"] + roles

        M = self.model_overview
        M.clear()
        M.setColumnCount(len(headers))
        M.setHorizontalHeaderLabels(headers)

        row_labels = []

        # --- per‐group rows ---
        for group_id, stats in per_group.items():
            row_labels.append(group_id)
            grp_info = self.ui.organisation.role_allocation.groups[group_id]
            group_type = grp_info.get("group_type", "")
            parent     = grp_info.get("parent") or ""

            # Build the Num. Agents item **with** tooltip
            agent_ids = stats.get("agents",
                                  self.ui.organisation.role_allocation.get_agents_in_group(group_id))
            num_item = QStandardItem(str(stats["num_agents"]))
            if agent_ids:
                num_item.setToolTip("\n".join(agent_ids))

            items = [
                QStandardItem(group_type),
                QStandardItem(parent),
                num_item
            ]

            # Role‐count cells (as before)
            for role in roles:
                count     = stats["role_counts"].get(role, 0)
                role_item = QStandardItem(str(count))

                agent_list = stats["role_agents"].get(role, [])
                if agent_list:
                    role_item.setToolTip("\n".join(agent_list))

                items.append(role_item)

            M.appendRow(items)

        # --- TOTAL row ---
        row_labels.append("TOTAL")

        all_agent_ids = self.ui.organisation.role_allocation.agents_names
        total_num_item = QStandardItem(str(overview["num_agents"]))
        if all_agent_ids:
            total_num_item.setToolTip("\n".join(all_agent_ids))

        total_items = [
            QStandardItem(""),  # blank Type
            QStandardItem(""),  # blank Parent
            total_num_item
        ]
        for role in roles:
            cnt  = global_counts.get(role, 0)
            item = QStandardItem(str(cnt))
            agents = global_agents.get(role, [])
            if agents:
                item.setToolTip("\n".join(agents))
            total_items.append(item)

        M.appendRow(total_items)

        M.setRowCount(len(row_labels))
        M.setVerticalHeaderLabels(row_labels)
        tv.resizeColumnsToContents()

    def onOverviewSelected(self, current: QModelIndex, previous: QModelIndex):
        if not current.isValid():
            return

        # --- your existing group-selection logic ---
        group_id = self.model_overview.verticalHeaderItem(current.row()).text()
        if group_id != "TOTAL":
            gv = self.ui.tableView_ra_groups
            for row in range(self.model_groups.rowCount()):
                if self.model_groups.item(row, 0).text() == group_id:
                    gv.selectRow(row)
                    gv.scrollTo(self.model_groups.index(row, 0))
                    gv.setFocus()
                    break

        # --- now, grab & show the tooltip for THIS cell ---
        tip = current.data(Qt.ToolTipRole)
        if tip:
            # figure out a global position in the middle of that cell
            cell_rect = self.ui.tableView_ra_fleet_overview.visualRect(current)
            cell_center = cell_rect.center()
            global_pt = self.ui.tableView_ra_fleet_overview.viewport().mapToGlobal(cell_center)
            QToolTip.showText(global_pt, tip, self.ui.tableView_ra_fleet_overview)

    # --- Group handlers ---
    def refreshGroups(self):
        view = self.ui.tableView_ra_groups
        M = self.model_groups

        # — 1) Remember old selection from the *name* column (col 0)
        prev_name = None
        cur = view.currentIndex()
        if cur.isValid():
            prev_name = M.item(cur.row(), 0).text()

        # — 2) Grab the up-to-date dict of groups
        groups = self.ui.organisation.role_allocation.groups

        # — 3) Rebuild a 2-col model: [Group Name, Type]
        M.clear()
        M.setHorizontalHeaderLabels(['Group Name', 'Type'])
        for row, (name, vals) in enumerate(groups.items()):
            name_item = QStandardItem(name)
            name_item.setEditable(False)
            type_item = QStandardItem(vals['group_type'])
            type_item.setEditable(False)
            M.setItem(row, 0, name_item)
            M.setItem(row, 1, type_item)

        # — 4) Attach it (harmless if it was already set)
        view.setModel(M)
        view.resizeColumnsToContents()
        view.resizeRowsToContents()

        # — 5) Restore selection by *name* (or default to row 0)
        row_count = M.rowCount()
        if row_count:
            names = [M.item(r, 0).text() for r in range(row_count)]
            if prev_name in names:
                row = names.index(prev_name)
            else:
                row = 0

            idx = M.index(row, 0)
            view.setCurrentIndex(idx)
            view.selectRow(row)
            view.scrollTo(idx)
            view.setFocus()
        else:
            view.clearSelection()

        # — 6) Show or hide the groups-pane & properties-pane
        has_structural = bool(self.ui.organisation.moise_model.structural_specification.groups)
        self.ui.stackedWidget_ra_groups.setCurrentIndex(VISIBLE if has_structural else HIDDEN)

        has_groups = bool(groups)
        self.ui.stackedWidget_ra_group_properties.setCurrentIndex(
            VISIBLE if has_groups else HIDDEN
        )

    def onAddGroup(self):
        # 1) Ask for name & type
        group_name, ok = QInputDialog.getText(self, "Add Group", "Group name:")
        if not (ok and group_name):
            return

        group_type, ok1 = QInputDialog.getItem(
            self,
            "Group instance type",
            "Group types:",
            self.ui.organisation.moise_model.structural_specification.groups_names,
            0, False
        )
        if not (ok1 and group_type):
            return

        # 2) Optionally ask for a parent
        parent = None
        existing = self.ui.organisation.role_allocation.groups_names
        if existing:
            parent, ok2 = QInputDialog.getItem(
                self,
                "Group instance parent",
                "Parent group (if any):",
                [None] + existing,
                0, False
            )
            if not ok2:
                parent = None

        # 3) Add it
        self.ui.organisation.role_allocation.add_group(
            group_name=group_name,
            group_type=group_type,
            parent=parent
        )

        # 4) Refresh and select the new row
        self.refreshGroups()
        M = self.model_groups
        names = [M.item(r, 0).text() for r in range(M.rowCount())]
        row = names.index(group_name)
        idx = M.index(row, 0)

        view = self.ui.tableView_ra_groups
        view.setCurrentIndex(idx)
        view.selectRow(row)
        view.scrollTo(idx)
        view.setFocus()

        self.refreshData(user_triggered=False)

    def onRemoveGroup(self):
        idx = self.ui.tableView_ra_groups.currentIndex().row()
        if idx<0: return
        grp = self.model_groups.item(idx, 0).text()
        self.ui.organisation.role_allocation.remove_group(grp)

        self.refreshData(user_triggered=False)

    def onGroupSelected(self, current: QModelIndex, prev: QModelIndex):
        if current.row()<0:
            self.ui.stackedWidget_ra_group_properties.setCurrentIndex(HIDDEN)
            return
        self.ui.stackedWidget_ra_group_properties.setCurrentIndex(VISIBLE)

        self.refreshGroupProperties()
        self.refreshAssignments()

    def refreshGroupProperties(self):
        # 1) figure out which group is selected
        idx = self.ui.tableView_ra_groups.currentIndex().row()
        if idx < 0:
            return

        name = self.model_groups.item(idx, 0).text()
        info = self.ui.organisation.role_allocation.groups[name]

        # 2) populate the “Type” combo‐box
        cb_type = self.ui.comboBox_ra_group_type
        with QSignalBlocker(cb_type):
            cb_type.clear()
            # all possible Moise group types
            cb_type.addItems(self.ui.organisation.moise_model.structural_specification.groups_names)
            cb_type.setCurrentText(info['group_type'])

        # 3) populate the “Parent” combo‐box
        cb_parent = self.ui.comboBox_ra_group_parent
        with QSignalBlocker(cb_parent):
            cb_parent.clear()
            # first entry is “None”
            cb_parent.addItem("(none)", userData=None)
            for g in self.ui.organisation.role_allocation.groups_names:
                cb_parent.addItem(g, userData=g)
            # set to the actual parent (or None)
            parent = info.get('parent')
            cb_parent.setCurrentText(parent if parent is not None else "(none)")

    def onGroupTypeChanged(self, new_type: str):
        """When the user picks a different type in the combo-box, write it to the model."""
        idx = self.ui.tableView_ra_groups.currentIndex().row()
        if idx < 0:
            return

        name = self.model_groups.item(idx, 0).text()
        # update the underlying RoleAllocation
        self.ui.organisation.role_allocation.groups[name]['group_type'] = new_type
        self.mark_dirty()

        # refresh the table so the “Type” column shows the new value
        # (refreshGroups preserves the current row by name)
        self.refreshGroups()

    def onGroupParentChanged(self, text: str):
        """When the user picks a different parent in the combo-box, write it to the model."""
        idx = self.ui.tableView_ra_groups.currentIndex().row()
        if idx < 0:
            return

        name = self.model_groups.item(idx, 0).text()
        parent = None if text in ("", "(none)") else text
        self.ui.organisation.role_allocation.groups[name]['parent'] = parent
        self.mark_dirty()

        # No need to change the order of the table, but if you ever
        # rely on grouping by parent you might want to call refreshGroups()
        # so that any parent-based grouping or indentation updates.
        self.refreshGroups()

    # --- Agent handlers ---
    def refreshAgents(self):
        M = self.model_agents
        M.clear()
        M.setHorizontalHeaderLabels(["ID", "Class"])
        for agent in self.ui.organisation.fleet:
            row = [QStandardItem(str(agent.id)),
                   QStandardItem(agent.agent_class)]
            M.appendRow(row)
        self.ui.tableView_ra_agents.resizeColumnsToContents()

        view = self.ui.tableView_ra_agents
        M = self.model_agents

        # 1) remember old selection from column 1 (the ID)
        prev_id = None
        cur = view.currentIndex()
        if cur.isValid():
            prev_id = M.item(cur.row(), 1).text()

        # 2) rebuild 2-col model: [icon, instance-ID]
        M.clear()
        M.setHorizontalHeaderLabels(["", "Instance"])

        for agent in self.ui.organisation.fleet.items:
            aid = str(agent.id)
            # use the agent’s class icon (or default)
            norm = agent.agent_class.lower().replace(" ", "_")
            path = os.path.join(self.class_image_dir, f"{norm}.png")
            img = path if os.path.exists(path) else self.default_image

            pix = QPixmap(img).scaled(self.instances_icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_item = QStandardItem()
            icon_item.setData(QIcon(pix), Qt.DecorationRole)
            icon_item.setEditable(False)

            text_item = QStandardItem(aid)
            text_item.setEditable(False)

            M.appendRow([icon_item, text_item])

        view.resizeColumnsToContents()
        view.resizeRowsToContents()

        # 3) restore previous (or default) selection
        row_count = M.rowCount()
        if row_count:
            # build a list of all IDs in col 1
            ids = [M.item(r, 1).text() for r in range(row_count)]
            if prev_id in ids:
                row = ids.index(prev_id)
            else:
                row = 0
            view.selectRow(row)
            view.setCurrentIndex(M.index(row, 1))
        else:
            view.clearSelection()

        if not self.ui.organisation.fleet.fleet_classes:
            self.ui.stackedWidget_ra_properties.setCurrentIndex(HIDDEN)
        else:
            self.ui.stackedWidget_ra_properties.setCurrentIndex(VISIBLE)

    def onAgentSelected(self, current: QModelIndex, prev: QModelIndex):
        self.refreshAssignments()

    # --- Assignment handlers ---
    def refreshAssignments(self):
        view = self.ui.listView_ra_assignments
        M = self.model_assignments

        # 1) remember the old selection text (if any)
        prev_text = None
        cur_idx = view.currentIndex()
        if cur_idx.isValid():
            prev_text = M.data(cur_idx, Qt.DisplayRole)

        # 2) rebuild the list for the current agent
        agent_view = self.ui.tableView_ra_agents
        cur = agent_view.currentIndex()
        if not cur.isValid():
            M.setStringList([])
        else:
            agent_id = self.model_agents.item(cur.row(), 1).text()
            names = self.ui.organisation.role_allocation.get_group_affiliations(agent_id=agent_id)
            M.setStringList(names)

        # 3) restore selection if possible, else first row, else clear
        names = M.stringList()
        if names:
            if prev_text in names:
                row = names.index(prev_text)
            else:
                row = 0
            new_idx = M.index(row, 0)
            view.setCurrentIndex(new_idx)
        else:
            view.clearSelection()

        # 4) scroll into view & focus
        if names:
            view.scrollTo(view.currentIndex())
            view.setFocus()

        # 5) show/hide properties pane
        if not self.ui.organisation.role_allocation.groups:
            self.ui.stackedWidget_ra_properties.setCurrentIndex(HIDDEN)
        else:
            self.ui.stackedWidget_ra_properties.setCurrentIndex(VISIBLE)

    def onAddAssignment(self):
        # 1) which agent?
        agent_view = self.ui.tableView_ra_agents
        cur = agent_view.currentIndex()
        if not cur.isValid():
            return
        agent_id = self.model_agents.item(cur.row(), 1).text()

        # 2) compute unassigned groups
        current = self.ui.organisation.role_allocation.get_group_affiliations(agent_id=agent_id)
        all_groups = self.ui.organisation.role_allocation.groups_names
        available = [g for g in all_groups if g not in current]
        if not available:
            QMessageBox.information(
                self, "Add Assignment",
                "All groups are already assigned to this agent."
            )
            return

        # 3) ask which one
        group_id, ok = QInputDialog.getItem(
            self, "Add Assignment", "Group:", available, 0, False
        )
        if not (ok and group_id):
            return

        # 4) add
        self.ui.organisation.role_allocation.add_group_affiliation(
            agent_id=agent_id, group_id=group_id
        )

        # 5) refresh & auto-select the new row
        self.refreshAssignments()

        view = self.ui.listView_ra_assignments
        M = self.model_assignments
        names = M.stringList()
        # find the newly added one; fall back to first row
        if group_id in names:
            row = names.index(group_id)
        else:
            row = 0
        new_idx = M.index(row, 0)
        view.setCurrentIndex(new_idx)
        view.scrollTo(new_idx)
        view.setFocus()

    def onRemoveAssignment(self):
        # 1) Figure out which agent is selected
        agent_view = self.ui.tableView_ra_agents
        cur_agent = agent_view.currentIndex()
        if not cur_agent.isValid():
            return
        agent_id = self.model_agents.item(cur_agent.row(), 1).text()

        # 2) Figure out which assignment (i.e. group) is selected
        asg_view = self.ui.listView_ra_assignments
        cur_asg = asg_view.currentIndex()
        if cur_asg.row() < 0:
            return
        group_id = self.model_assignments.stringList()[cur_asg.row()]

        # 3) Remove the assignment and mark dirty
        self.ui.organisation.role_allocation.remove_group_affiliation(agent_id=agent_id, group_id=group_id)

        self.refreshData(user_triggered=False)

    def onAssignmentSelected(self, current: QModelIndex, prev: QModelIndex):
        self.refreshRoles()

    # --- Role handlers ---
    def refreshRoles(self):
        # 1) Which agent is selected?
        agent_view = self.ui.tableView_ra_agents
        cur = agent_view.currentIndex()
        if not cur.isValid():
            return

        # 2) Pull the ID from column 1 (not 0)
        agent_id = self.model_agents.item(cur.row(), 1).text()

        # 3) Which assignment (group) is selected?
        asg_view = self.ui.listView_ra_assignments
        asg_idx = asg_view.currentIndex().row()

        if asg_idx < 0:
            self.model_roles.setStringList([])
        else:
            group_id = self.model_assignments.stringList()[asg_idx]
            roles = self.ui.organisation.role_allocation.get_roles(
                agent_id=agent_id,
                group_id=group_id
            )
            self.model_roles.setStringList(roles)

        view = self.ui.listView_ra_assignment_roles
        prev = None
        cur = view.currentIndex()

        if cur.isValid():
            prev = self.model_roles.data(cur, Qt.DisplayRole)

        names = self.model_roles.stringList()
        if names:
            if prev in names:
                row = names.index(prev)
            else:
                row = 0
                idx = self.model_roles.index(row, 0)
                view.setCurrentIndex(idx)
                view.scrollTo(idx)
                view.setFocus()
        else:
            view.clearSelection()
        
        # 4) Show or hide the roles pane
        has_any_roles = (
            self.ui.organisation.moise_model.structural_specification.roles
            and self.ui.organisation.role_allocation.get_group_affiliations(agent_id=agent_id)
        )
        self.ui.stackedWidget_ra_roles.setCurrentIndex(
            VISIBLE if has_any_roles else HIDDEN
        )

    def onAddRole(self):
        # 1) Which agent & assignment?
        agent_index = self.ui.tableView_ra_agents.currentIndex().row()
        assignment_index = self.ui.listView_ra_assignments.currentIndex().row()
        if agent_index < 0 or assignment_index < 0:
            return

        agent_id = self.model_agents.item(agent_index, 1).text()
        group_id = self.model_assignments.stringList()[assignment_index]

        # 2) Compute candidate roles
        all_roles = self.ui.organisation.moise_model.structural_specification.roles_names
        assigned_roles = self.ui.organisation.role_allocation.get_roles(
            agent_id=agent_id,
            group_id=group_id
        )
        candidate_roles = [r for r in all_roles if r not in assigned_roles]

        if not candidate_roles:
            QMessageBox.information(
                self, "Add Role",
                "All roles are already assigned to this agent affiliation."
            )
            return

        # 3) Let the user pick one
        role, ok = QInputDialog.getItem(
            self, "Add Role", "Role name:", candidate_roles, 0, False
        )
        if not (ok and role):
            return

        # 4) Actually add it
        self.ui.organisation.role_allocation.add_role(
            agent_id=agent_id,
            group_id=group_id,
            role=role
        )

        # 5) Refresh everything
        self.refreshData(user_triggered=False)

        # 6) Now force-select the role we just added
        view = self.ui.listView_ra_assignment_roles
        roles = self.model_roles.stringList()
        try:
            row = roles.index(role)
        except ValueError:
            # shouldn't happen—but bail safely
            return

        idx = self.model_roles.index(row, 0)
        view.setCurrentIndex(idx)
        view.scrollTo(idx)
        view.setFocus()

    def onRemoveRole(self):
        grp_idx = self.ui.tableView_ra_groups.currentIndex().row()
        asg_idx = self.ui.listView_ra_assignments.currentIndex().row()
        agent_index = self.ui.tableView_ra_agents.currentIndex().row()
        assignment_index = self.ui.listView_ra_assignments.currentIndex().row()
        role_index = self.ui.listView_ra_assignment_roles.currentIndex().row()
        if agent_index<0 or assignment_index<0: return
        agent_id = self.model_agents.item(agent_index, 1).text()
        group_id = self.model_assignments.stringList()[assignment_index]

        role = self.model_roles.stringList()[role_index]
        self.ui.organisation.role_allocation.remove_role(
            agent_id=agent_id,
            group_id=group_id,
            role=role
        )

        self.refreshData(user_triggered=False)

    # --- Verify & Raw Inspection ---
    def onVerify(self):
        errors = self.ui.organisation.role_allocation.verify()
        if errors:
            QMessageBox.information(self, "Verify", "\n".join(errors))
        else:
            QMessageBox.information(self, "Verify", "Role allocation is valid.")

    def refreshInspection(self, user_triggered=False):
        if user_triggered:
            self.ui.current_raw_view = 'ra'
        if self.ui.current_raw_view!='ra':
            return
        raw = json.dumps(self.ui.organisation.role_allocation.asdict(), indent=2)
        self.ui.plainTextEdit_raw.setPlainText(raw)

    def switchTab(self, index):
        if self.ui.tabWidget_moise.indexOf(self.ui.tab_ra)==index:
            self.refreshInspection(user_triggered=True)

    def onPlotFleetOrganisation(self):
        """
        Opens or updates a modeless window showing the fleet organisation.
        """
        # create dialog+label on first click
        if self.plot_window is None:
            self.plot_window = QDialog(self)
            self.plot_window.setWindowTitle("Fleet Organisation")
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
            fig = self.ui.organisation.plot_fleet_organisation(display_plot=False)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to plot fleet structure:\n{e}")
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
        for btn in (
            self.ui.pushButton_ra_add_group,
            self.ui.pushButton_ra_remove_group,
            self.ui.pushButton_ra_add_group,
            self.ui.pushButton_ra_remove_group,
            self.ui.pushButton_ra_add_assignment,
            self.ui.pushButton_ra_remove_assignment,
            self.ui.pushButton_ra_assignment_add_role,
            self.ui.pushButton_ra_assignment_remove_role
        ):
            btn.clicked.connect(self.mark_dirty)

    def mark_dirty(self):
        if self._suppress_dirty: return
        if not self.dirty:
            self.dirty = True

    def update_title(self):
        suffix = '*' if self.dirty else ''
        idx = self.ui.tabWidget_moise.indexOf(self.ui.tab_ra)
        self.ui.tabWidget_moise.setTabText(idx, f"{self._orig_tab_title}{suffix}")
        self.ui.label_ra_file_name.setText(self.ui.current_file or '…')

    def new_file(self, user_triggered=True):
        # prompt to save if dirty
        if self.dirty:
            resp = QMessageBox.question(
                self, "Unsaved Changes",
                "Save before creating new role allocation?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            if resp == QMessageBox.Cancel:
                return
            if resp == QMessageBox.Yes and not self.save_file():
                return

        # reset fleet data
        self._suppress_dirty = True
        try:
            self.ui.organisation.role_allocation = RoleAllocation()
            self.ui.current_file = None
            self.dirty = False
            self.refreshData(user_triggered=True)

            self.ui.tabWidget_moise.setCurrentIndex(self.ui.tabWidget_moise.indexOf(self.ui.tab_ra))

        finally:
            self._suppress_dirty = False

    def open_file(self):
        # prompt to save if dirty
        if self.dirty:
            resp = QMessageBox.question(
                self, "Unsaved Changes",
                "Save before opening fleet file?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            if resp == QMessageBox.Cancel:
                return
            if resp == QMessageBox.Yes and not self.save_file():
                return

        # choose file
        role_allocation_path, _ = QFileDialog.getOpenFileName(
            self, "Open Role Allocation", "", "Role Allocation (*.ra);;All Files (*)"
        )

        if not role_allocation_path:
            return

        try:
            self._suppress_dirty = True

            with open(role_allocation_path, 'r') as f:
                data = json.load(f)

            # load into Fleet
            self.ui.organisation.role_allocation = RoleAllocation(role_allocation=data)

            self.ui.current_file = role_allocation_path
            self.dirty = False

            self.refreshData(user_triggered=True)

            # switch to fleet config tab
            idx = self.ui.tabWidget_moise.indexOf(self.ui.tab_ra)
            if idx != -1:
                self.ui.tabWidget_moise.setCurrentIndex(idx)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to open Role Allocation file:\n{e}")
        finally:
            self._suppress_dirty = False

    def save_file(self):
        # determine save path
        path = self.ui.current_file
        if not path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Role Allocation As", "", "Roel Allocation (*.ra);;All Files (*)"
            )
            if not path:
                return False
            if not path.lower().endswith('.ra'):
                path += '.fc'
            self.ui.current_file = path

        # write JSON
        try:
            with open(self.ui.current_file, 'w') as f:
                json.dump(self.ui.organisation.role_allocation.asdict(), f, indent=2)
            self.dirty = False
            self.update_title()
            return True
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Save failed:\n{e}")
            return False

    # ---------- UI Refresh ----------
    def refreshData(self, user_triggered=False):
        print("Refresh RA")
        self._suppress_dirty = True
        try:
            self.refreshGroups()
            self.refreshAgents()
            self.refreshAssignments()
            self.refreshRoles()
            self.refreshOverview()

            self.refreshInspection(user_triggered=user_triggered)
            self.update_plot_window()

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
