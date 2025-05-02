import json
import io
import os

import matplotlib.pyplot as plt

from PySide6.QtCore import Qt, QStringListModel, QModelIndex, QItemSelectionModel, QSignalBlocker, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QInputDialog, QMessageBox,
    QFileDialog, QDialog, QLabel, QSizePolicy, QAbstractItemView, QPlainTextEdit, QHeaderView
)
from PySide6.QtGui import QStandardItemModel, QStandardItem, QPixmap, QIcon


try:
    from maaf_editor.ui_singleton import UiSingleton

    from maaf_tools.datastructures.agent.Agent import Agent
    from maaf_tools.datastructures.agent.Fleet import Fleet

except:
    from maaf_editor.maaf_editor.ui_singleton import UiSingleton

    from maaf_tools.maaf_tools.datastructures.agent.Agent import Agent
    from maaf_tools.maaf_tools.datastructures.agent.Fleet import Fleet

VISIBLE = 0
HIDDEN = 1

class FleetConfigWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.ui = UiSingleton().interface

        # file and dirty state
        self.ui.current_file = None
        self.dirty = False
        self._suppress_dirty = True
        idx = self.ui.tabWidget_moise.indexOf(self.ui.tab_fc)
        self._orig_tab_title = self.ui.tabWidget_moise.tabText(idx)

        # Modeless plot window placeholders
        self.plot_window = None
        self.plot_label = None

        # Assets
        self.class_image_dir = "maaf_editor/maaf_editor/Assets"
        self.default_image = os.path.join(self.class_image_dir, "wall-e.png")
        self.max_image_size = QSize(200, 200)
        self.ui.label_fc_class_image.setMaximumSize(self.max_image_size)

        self.classes_icon_size = QSize(48, 48)
        self.ui.tableView_fc_classes.setIconSize(self.classes_icon_size)

        self.instances_icon_size = QSize(28, 28)
        self.ui.tableView_fc_agent_instances.setIconSize(self.instances_icon_size)

        # models
        self.model_classes = QStandardItemModel(self)
        self.model_skills = QStringListModel(self)
        self.model_instances = QStandardItemModel(self)
        self.model_specs = QStandardItemModel(self)
        self.model_overview = QStandardItemModel(self)

        # wire up list views and tables
        u = self.ui
        u.tableView_fc_classes.setModel(self.model_classes)
        u.listView_fc_class_skills.setModel(self.model_skills)
        u.tableView_fc_class_specs.setModel(self.model_specs)
        u.tableView_fc_agent_instances.setModel(self.model_instances)
        u.tableView_fc_fleet_overview.setModel(self.model_overview)

        for view in (
                u.tableView_fc_class_specs,
                u.tableView_fc_agent_instances,
                u.tableView_fc_fleet_overview
        ):
            # Horizontal header: disable resizing & moving
            h = view.horizontalHeader()
            h.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            h.setSectionsMovable(False)

            # Vertical header: disable resizing & moving
            v = view.verticalHeader()
            v.setVisible(True)
            v.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            v.setSectionsMovable(False)

        # wire class-instance combo
        u.comboBox_fc_agent_instance_class.currentTextChanged.connect(self.onAgentClassChanged)

        # file actions
        u.action_new_Fleet_Configuration.triggered.connect(self.new_file)
        u.action_open_Fleet_Configuration.triggered.connect(self.open_file)
        u.toolButton_fc_refresh_inspection.clicked.connect(lambda: self.refreshInspection(user_triggered=True))
        u.pushButton_fc_verify.clicked.connect(self.onVerify)
        u.tabWidget_moise.currentChanged.connect(self.switchTab)

        # class signals
        u.plainTextEdit_fc_class_description.textChanged.connect(self.onClassDescriptionChanged)
        u.pushButton_fc_add_class.clicked.connect(self.onAddClass)
        u.pushButton_fc_remove_class.clicked.connect(self.onRemoveClass)
        u.tableView_fc_classes.selectionModel().currentChanged.connect(self.onClassSelected)
        u.pushButton_fc_class_add_skill.clicked.connect(self.onAddSkill)
        u.pushButton_fc_class_remove_skill.clicked.connect(self.onRemoveSkill)
        u.pushButton_fc_class_add_spec.clicked.connect(self.onAddSpec)
        u.pushButton_fc_class_remove_spec.clicked.connect(self.onRemoveSpec)

        # agent instance signals
        u.pushButton_fc_add_agent.clicked.connect(self.onAddAgent)
        u.pushButton_fc_remove_agent.clicked.connect(self.onRemoveAgent)
        u.tableView_fc_agent_instances.selectionModel().currentChanged.connect(self.onAgentSelected)

        # Connect plot button to open/update non-blocking plot window
        u.pushButton_fc_plot_fleet_configuration.clicked.connect(self.onPlotFleetConfig)
        u.action_plot_Fleet_Configuration.triggered.connect(self.onPlotFleetConfig)

        # dirty tracking
        self.setup_dirty_tracking()

        # initial load
        if not hasattr(self.ui, 'organisation'):
            QMessageBox.warning(self, "Error", "No organisation loaded for fleet config.")
            return

        # initial refresh
        self._suppress_dirty = False
        self.refreshData()

    # --- Class handlers ---
    def refreshClasses(self):
        # — remember old selection from the *name* column
        view = self.ui.tableView_fc_classes
        prev_name = None
        cur = view.currentIndex()
        if cur.isValid():
            # column 1 holds the class name
            prev_name = self.model_classes.item(cur.row(), 1).text()

        # — rebuild a 2-col model: [icon, class]
        M = self.model_classes
        M.clear()
        M.setHorizontalHeaderLabels(["", "Class"])

        for cls_name in self.ui.organisation.fleet.fleet_classes:
            # choose image file or default
            norm = cls_name.lower().replace(" ", "_")
            path = os.path.join(self.class_image_dir, f"{norm}.png")
            img = path if os.path.exists(path) else self.default_image

            # make icon item
            pix = QPixmap(img).scaled(self.classes_icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_item = QStandardItem()
            icon_item.setData(QIcon(pix), Qt.DecorationRole)
            icon_item.setEditable(False)

            # make text item
            text_item = QStandardItem(cls_name)
            text_item.setEditable(False)

            M.appendRow([icon_item, text_item])

        view.resizeColumnsToContents()
        view.resizeRowsToContents()

        # — restore selection (or default to row 0)
        row_count = M.rowCount()
        if row_count:
            if prev_name in [M.item(r, 1).text() for r in range(row_count)]:
                row = [M.item(r, 1).text() for r in range(row_count)].index(prev_name)
            else:
                row = 0
            view.selectRow(row)
            view.setCurrentIndex(M.index(row, 1))
        else:
            view.clearSelection()

        # — repopulate the agent-class combo
        cmb = self.ui.comboBox_fc_agent_instance_class
        old = cmb.currentText()
        with QSignalBlocker(cmb):
            cmb.clear()
            cmb.addItems([M.item(r, 1).text() for r in range(row_count)])
            current_items = [cmb.itemText(i) for i in range(cmb.count())]
            if old and old in current_items:
                cmb.setCurrentText(old)

        # — show/hide the class-properties pane
        if not self.ui.organisation.fleet.fleet_classes:
            self.ui.stackedWidget_fc_class_properties.setCurrentIndex(HIDDEN)
        else:
            self.ui.stackedWidget_fc_class_properties.setCurrentIndex(VISIBLE)

    def onAddClass(self):
        name, ok = QInputDialog.getText(self, "Add Class", "Class name:")
        if not (ok and name):
            return
        if name in self.ui.organisation.fleet.fleet_classes:
            QMessageBox.warning(self, "Error", "Class already exists.")
            return

        # 1) Update your data model
        self.ui.organisation.fleet.fleet_classes[name] = {'skillset': [], 'specs': {}}

        # 2) Rebuild the list
        self.refreshClasses()

        # 3) **Select the newly added class**:
        classes = [self.model_classes.item(row, 1).text() for row in range(self.model_classes.rowCount())]
        row = classes.index(name)
        idx = self.model_classes.index(row, 0)
        view = self.ui.tableView_fc_classes
        sel = view.selectionModel()
        sel.clearSelection()
        view.setCurrentIndex(idx)
        sel.select(idx, QItemSelectionModel.Select | QItemSelectionModel.Rows)
        view.scrollTo(idx)
        view.setFocus()

        self.refreshData(user_triggered=False)

    def onRemoveClass(self):
        idx = self.ui.tableView_fc_classes.currentIndex().row()
        if idx < 0:
            return
        name = [self.model_classes.item(row, 1).text() for row in range(self.model_classes.rowCount())][idx]
        del self.ui.organisation.fleet.fleet_classes[name]

        self.refreshData(user_triggered=False)

    def onClassSelected(self, current: QModelIndex, previous: QModelIndex):
        idx = current.row()
        u = self.ui
        self._suppress_dirty = True
        if idx < 0:
            with QSignalBlocker(u.listView_fc_class_skills), \
                    QSignalBlocker(u.tableView_fc_class_specs), \
                    QSignalBlocker(u.plainTextEdit_fc_class_description):
                u.listView_fc_class_skills.clearSelection()
                u.tableView_fc_class_specs.model().clear()
                u.plainTextEdit_fc_class_description.clear()

        else:
            name = [self.model_classes.item(row, 1).text() for row in range(self.model_classes.rowCount())][idx]
            info = self.ui.organisation.fleet.fleet_classes[name]

            # description
            with QSignalBlocker(u.plainTextEdit_fc_class_description):
                u.plainTextEdit_fc_class_description.setPlainText(info.get("description", ""))

            # skills
            self.model_skills.setStringList(info.get('skillset', []))

            # specs
            specs = info.get('specs', {})
            model = self.model_specs
            model.clear()
            model.setHorizontalHeaderLabels(['Key', 'Value'])
            for key, val in specs.items():
                items = [QStandardItem(str(key)), QStandardItem(str(val))]
                model.appendRow(items)

            # --- display class image (or default) ---
            norm = name.lower().replace(" ", "_")
            cls_img = os.path.join(self.class_image_dir, f"{norm}.png")
            img_path = cls_img if os.path.exists(cls_img) else self.default_image

            pix = QPixmap(img_path)

            if not pix.isNull():
                scaled = pix.scaled(
                                self.max_image_size,
                                Qt.KeepAspectRatio,
                                Qt.SmoothTransformation
                )
                self.ui.label_fc_class_image.setPixmap(scaled)
            else:
                self.ui.label_fc_class_image.clear()

        self._suppress_dirty = False

    def onClassDescriptionChanged(self):
        row = self.ui.tableView_fc_classes.currentIndex().row()
        if row >= 0:
            name = self.model_classes.item(row, 1).text()
            self.ui.organisation.fleet.fleet_classes[name]['description'] = self.ui.plainTextEdit_fc_class_description.toPlainText()

    def onAddSkill(self):
        cls_idx = self.ui.tableView_fc_classes.currentIndex().row()
        if cls_idx < 0:
            return
        name = [self.model_classes.item(row, 1).text() for row in range(self.model_classes.rowCount())][cls_idx]
        skill, ok = QInputDialog.getText(self, "Add Skill", "Skill:")
        if not (ok and skill):
            return

        # 1) update the data model
        self.ui.organisation.fleet.fleet_classes[name]['skillset'].append(skill)

        # 2) rebuild the skill list
        self.onClassSelected(self.model_classes.index(cls_idx, 0), None)

        # 3) select the newly added skill
        skills = self.model_skills.stringList()
        row = skills.index(skill)
        idx_skill = self.model_skills.index(row, 0)
        view_skill = self.ui.listView_fc_class_skills
        sel = view_skill.selectionModel()
        sel.select(idx_skill, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
        view_skill.scrollTo(idx_skill)
        view_skill.setCurrentIndex(idx_skill)
        view_skill.setFocus()

        self.refreshData(user_triggered=False)

    def onRemoveSkill(self):
        cls_idx = self.ui.tableView_fc_classes.currentIndex().row()
        skl_idx = self.ui.listView_fc_class_skills.currentIndex().row()
        if cls_idx < 0 or skl_idx < 0:
            return
        name = [self.model_classes.item(row, 1).text() for row in range(self.model_classes.rowCount())][cls_idx]
        skills = self.ui.organisation.fleet.fleet_classes[name]['skillset']
        del skills[skl_idx]
        self.onClassSelected(self.model_classes.index(cls_idx, 0), None)

        self.refreshData(user_triggered=False)

    def onAddSpec(self):
        cls_idx = self.ui.tableView_fc_classes.currentIndex().row()
        if cls_idx < 0:
            return
        name = [self.model_classes.item(row, 1).text() for row in range(self.model_classes.rowCount())][cls_idx]
        key, ok1 = QInputDialog.getText(self, "Add Spec", "Key:")
        if not (ok1 and key):
            return
        val, ok2 = QInputDialog.getText(self, "Add Spec", "Value:")
        if not (ok2 and val):
            return

        # 1) update the data model
        self.ui.organisation.fleet.fleet_classes[name]['specs'][key] = val

        # 2) rebuild the specs table
        self.onClassSelected(self.model_classes.index(cls_idx, 0), None)

        # 3) select the newly added spec by matching the Key in column 0
        model = self.model_specs
        view_spec = self.ui.tableView_fc_class_specs
        sel = view_spec.selectionModel()
        for r in range(model.rowCount()):
            if model.item(r, 0).text() == key:
                idx_spec = model.index(r, 0)
                sel.select(idx_spec, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
                view_spec.scrollTo(idx_spec)
                view_spec.setCurrentIndex(idx_spec)
                view_spec.setFocus()
                break

        self.refreshData(user_triggered=False)

    def onRemoveSpec(self):
        cls_idx = self.ui.tableView_fc_classes.currentIndex().row()
        spec_idx = self.ui.tableView_fc_class_specs.currentIndex().row()
        if cls_idx < 0 or spec_idx < 0:
            return
        name = [self.model_classes.item(row, 1).text() for row in range(self.model_classes.rowCount())][cls_idx]
        key = self.model_specs.item(spec_idx, 0).text()
        del self.ui.organisation.fleet.fleet_classes[name]['specs'][key]
        self.onClassSelected(self.model_classes.index(cls_idx, 0), None)

        self.refreshData(user_triggered=False)

    # --- Agent handlers ---
    def refreshInstances(self):
        view = self.ui.tableView_fc_agent_instances
        M = self.model_instances

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

        # 4) same show/hide logic as before:
        if not self.ui.organisation.fleet.fleet_classes:
            self.ui.tabWidget_fc_instances_editor.setCurrentIndex(HIDDEN)
        else:
            self.ui.tabWidget_fc_instances_editor.setCurrentIndex(VISIBLE)

        if not self.ui.organisation.fleet:
            self.ui.stackedWidget_fc_agent_instance.setCurrentIndex(HIDDEN)
        else:
            self.ui.stackedWidget_fc_agent_instance.setCurrentIndex(VISIBLE)

    def onAddAgent(self):
        if len(self.ui.organisation.fleet.fleet_classes) < 1:
            QMessageBox.warning(self, "Error", "At least one class must be defined")
            return

        agent_id, ok1 = QInputDialog.getText(self, "Add Agent", "Agent ID:")
        if not (ok1 and agent_id):
            return
        cls, ok2 = QInputDialog.getItem(
            self, "Add Agent", "Class:",
            list(self.ui.organisation.fleet.fleet_classes.keys()), 0, False
        )
        if not (ok2 and cls):
            return

        # 1) update data
        agent = Agent(id=agent_id, agent_class=cls, specs={}, skillset=[])
        self.ui.organisation.fleet.add_agent(agent=agent)

        # 2) rebuild the instances list
        self.refreshInstances()

        # 3) select the newly added agent
        ids = [self.model_instances.item(row, 1).text() for row in range(self.model_instances.rowCount())]
        row = ids.index(agent_id)
        idx_agent = self.model_instances.index(row, 0)
        view_agents = self.ui.tableView_fc_agent_instances
        sel = view_agents.selectionModel()
        sel.clearSelection()
        view_agents.setCurrentIndex(idx_agent)
        sel.select(idx_agent, QItemSelectionModel.Select | QItemSelectionModel.Rows)
        view_agents.scrollTo(idx_agent)
        view_agents.setFocus()

        # 4) update overview
        self.refreshData(user_triggered=False)
        self.ui.ra_widget.refreshData()

    def onRemoveAgent(self):
        idx = self.ui.tableView_fc_agent_instances.currentIndex().row()
        if idx < 0:
            return
        aid = [self.model_instances.item(row, 1).text() for row in range(self.model_instances.rowCount())][idx]
        self.ui.organisation.fleet.remove_agent(aid)

        self.refreshData(user_triggered=False)

    def onAgentSelected(self, current: QModelIndex, previous: QModelIndex):
        idx = current.row()
        if idx < 0:
            self.ui.stackedWidget_fc_agent_instance.setCurrentIndex(HIDDEN)
            return

        # show instance editor
        aid = [self.model_instances.item(row, 1).text() for row in range(self.model_instances.rowCount())][idx]
        agent = next((a for a in self.ui.organisation.fleet.items if str(a.id) == aid), None)
        if not agent:
            return

        # populate comboBox with classes and select this agent's class
        cmb = self.ui.comboBox_fc_agent_instance_class
        cmb.blockSignals(True)
        cmb.setCurrentText(agent.agent_class)
        cmb.blockSignals(False)
        self.ui.stackedWidget_fc_agent_instance.setCurrentIndex(VISIBLE)

    def onAgentClassChanged(self, new_class: str):
        view = self.ui.tableView_fc_agent_instances
        idx = view.currentIndex().row()
        if idx < 0:
            return

        aid = [self.model_instances.item(row, 1).text() for row in range(self.model_instances.rowCount())][idx]
        agent = next((a for a in self.ui.organisation.fleet.items if str(a.id) == aid), None)
        if not agent:
            return

        # 1) update data model
        agent.agent_class = new_class

        # 2) update overview table cell directly
        for r in range(self.model_overview.rowCount()):
            if self.model_overview.item(r, 0).text() == aid:
                self.model_overview.setItem(r, 1, QStandardItem(new_class))
                break

        # 3) refresh
        self.refreshData(user_triggered=False)

    def refreshOverview(self):
        # Build the overview table: columns = skills + "spec:value" headers
        fleet = self.ui.organisation.fleet
        stats = fleet.get_fleet_statistics()
        skill_counts = stats["skill_counts"]

        # Sort skills alphabetically
        skills = sorted(skill_counts.keys())

        headers = skills

        M = self.model_overview
        M.clear()
        M.setColumnCount(len(headers))
        M.setHorizontalHeaderLabels(headers)

        # Single row: the counts
        row_items = []
        # skill counts
        for sk in skills:
            row_items.append(QStandardItem(str(skill_counts.get(sk, 0))))

        M.appendRow(row_items)
        # Label the row as 'Counts'
        M.setRowCount(1)
        M.setVerticalHeaderLabels(["Counts"])

        # Resize to fit contents
        self.ui.tableView_fc_fleet_overview.resizeColumnsToContents()

    # --- Verify & Raw Inspection ---
    def onVerify(self):
        errors = []
        classes = set(self.ui.organisation.fleet.fleet_classes.keys())
        for agent in self.ui.organisation.fleet.items:
            if agent.agent_class not in classes:
                errors.append(f"Agent {agent.id} has unknown class {agent.agent_class}")
        if errors:
            QMessageBox.information(self, "Verify", "Errors:\n" + "\n".join(errors))
        else:
            QMessageBox.information(self, "Verify", "Fleet configuration is valid.")

    def refreshInspection(self, user_triggered=False):
        if user_triggered:
            self.ui.current_raw_view = 'fc'
        if self.ui.current_raw_view != 'fc':
            return
        raw = json.dumps(self.ui.organisation.fleet.asdict(), indent=2)
        self.ui.plainTextEdit_raw.setPlainText(raw)

    def switchTab(self, index):
        if self.ui.tabWidget_moise.indexOf(self.ui.tab_fc) == index:
            self.refreshInspection(user_triggered=True)

    def onPlotFleetConfig(self):
        """
        Opens or updates a modeless window showing the plan graph.
        """
        # create dialog+label on first click
        if self.plot_window is None:
            self.plot_window = QDialog(self)
            self.plot_window.setWindowTitle("Fleet Structure")
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
            fig = self.ui.organisation.fleet.plot_fleet_configuration(display_plot=False)
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
            self.ui.pushButton_fc_add_class,
            self.ui.pushButton_fc_remove_class,
            self.ui.pushButton_fc_class_add_skill,
            self.ui.pushButton_fc_class_remove_skill,
            self.ui.pushButton_fc_class_add_spec,
            self.ui.pushButton_fc_class_remove_spec,
            self.ui.pushButton_fc_add_agent,
            self.ui.pushButton_fc_remove_agent
        ):
            btn.clicked.connect(self.mark_dirty)

    def mark_dirty(self):
        if self._suppress_dirty:
            return
        if not self.dirty:
            self.dirty = True

    def update_title(self):
        suffix = '*' if self.dirty else ''
        idx = self.ui.tabWidget_moise.indexOf(self.ui.tab_fc)
        self.ui.tabWidget_moise.setTabText(idx, f"{self._orig_tab_title}{suffix}")
        self.ui.label_fc_file_name.setText(self.ui.current_file or '…')

    def new_file(self, user_triggered=True):
        # prompt to save if dirty
        if self.dirty:
            resp = QMessageBox.question(
                self, "Unsaved Changes",
                "Save before creating new fleet configuration?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            if resp == QMessageBox.Cancel:
                return
            if resp == QMessageBox.Yes and not self.save_file():
                return

        # reset fleet data
        self._suppress_dirty = True
        try:
            # create fresh Fleet instance
            self.ui.organisation.fleet = Fleet()
            self.ui.current_file = None
            self.dirty = False
            self.refreshData(user_triggered=True)

            self.ui.tabWidget_moise.setCurrentIndex(self.ui.tabWidget_moise.indexOf(self.ui.tab_fc))

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
        fleet_agent_classes_path, _ = QFileDialog.getOpenFileName(
            self, "Open Fleet Agent Classes", "", "Fleet JSON (*.json);;All Files (*)"
        )

        fleet_agents_path, _ = QFileDialog.getOpenFileName(
            self, "Open Fleet Agents", "", "Fleet JSON (*.json);;All Files (*)"
        )
        if not fleet_agent_classes_path:
            return

        try:
            self._suppress_dirty = True

            with open(fleet_agent_classes_path, 'r') as f:
                fleet_classes = json.load(f)

            fleet_agents = {}
            if fleet_agents_path:
                with open(fleet_agents_path, 'r') as f:
                    fleet_agents = json.load(f)

            # load into Fleet
            self.ui.organisation.fleet = Fleet.from_config_files(
                fleet_agents=fleet_agents,
                fleet_classes=fleet_classes
            )

            self.ui.current_file = fleet_agent_classes_path
            self.dirty = False

            self.refreshData(user_triggered=True)

            # switch to fleet config tab
            idx = self.ui.tabWidget_moise.indexOf(self.ui.tab_fc)
            if idx != -1:
                self.ui.tabWidget_moise.setCurrentIndex(idx)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to open fleet file:\n{e}")
        finally:
            self._suppress_dirty = False

    def save_file(self) -> bool:
        # determine save path
        path = self.ui.current_file
        if not path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Fleet Configuration As", "", "Fleet Configuration (*.fc);;All Files (*)"
            )
            if not path:
                return False
            if not path.lower().endswith('.fc'):
                path += '.fc'
            self.ui.current_file = path

        # write JSON
        try:
            with open(self.ui.current_file, 'w') as f:
                json.dump(self.ui.organisation.fleet.asdict(), f, indent=2)
            self.dirty = False
            self.update_title()
            return True
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Save failed:\n{e}")
            return False

    # ---------- UI Refresh ----------
    def refreshData(self, user_triggered=False):
        print("Refresh FC")
        self._suppress_dirty = True
        try:
            self.refreshClasses()
            self.refreshInstances()
            self.refreshOverview()

            self.refreshInspection(user_triggered=user_triggered)
            self.update_title()
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

    def minimumSizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(0, 0)
