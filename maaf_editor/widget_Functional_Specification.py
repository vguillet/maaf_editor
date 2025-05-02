import json
import sys
import io
import os
from copy import deepcopy

import matplotlib.pyplot as plt

from PySide6.QtCore import Qt, QStringListModel, QModelIndex, QSignalBlocker, QItemSelectionModel
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QInputDialog, QMessageBox,
    QApplication, QFileDialog, QDialog, QLabel, QSizePolicy
)
from PySide6.QtGui import QPixmap

try:
    from maaf_editor.ui_singleton import UiSingleton
    from maaf_tools.datastructures.organisation.MOISEPlus.FunctionalSpecification import FunctionalSpecification

except:
    from maaf_editor.maaf_editor.ui_singleton import UiSingleton
    from maaf_tools.maaf_tools.datastructures.organisation.MOISEPlus.FunctionalSpecification import FunctionalSpecification

HIDDEN = 1
VISIBLE = 0

class FunctionalSpecWidget(QWidget):
    def __init__(self):
        super().__init__()

        # Load UI singleton
        self.ui = UiSingleton().interface

        # File state
        self.ui.current_file = None
        self.dirty = False
        self._suppress_dirty = True
        self.last_min_value = 0
        self.last_max_value = 0

        # Cache original tab title
        idx = self.ui.tabWidget_moise.indexOf(self.ui.tab_fs)
        self._orig_fs_tab_title = self.ui.tabWidget_moise.tabText(idx)

        # Initialize specification
        # Models
        self.model_schemes = QStringListModel(self)
        self.model_goals = QStringListModel(self)
        self.model_plans = QStringListModel(self)
        self.model_missions = QStringListModel(self)
        self.model_goal_specs = QStringListModel(self)
        self.model_plan_steps = QStringListModel(self)
        self.model_mission_goals = QStringListModel(self)

        # Assign models
        u = self.ui
        u.comboBox_fs_social_scheme.setModel(self.model_schemes)
        u.listView_fs_goals.setModel(self.model_goals)
        u.listView_fs_plans.setModel(self.model_plans)
        u.listView_fs_missions.setModel(self.model_missions)
        u.listView_fs_goal_specs.setModel(self.model_goal_specs)
        u.listView_fs_plan_goal_sequence.setModel(self.model_plan_steps)
        u.listView_fs_mission_goals.setModel(self.model_mission_goals)

        # File menu actions
        u.action_new_Functional_Specification.triggered.connect(self.new_file)
        u.action_open_Functional_Specification.triggered.connect(self.open_file)

        # Connect scheme signals
        u.pushButton_fs_add_social_scheme.clicked.connect(self.onAddScheme)
        u.pushButton_fs_remove_social_scheme.clicked.connect(self.onRemoveScheme)
        u.comboBox_fs_social_scheme.currentIndexChanged.connect(self.onSchemeChanged)
        u.lineEdit_fs_social_scheme_description.editingFinished.connect(self.onSchemeDescriptionChanged)
        u.pushButton_fs_verify.clicked.connect(self.onVerify)

        # Connect goal signals
        u.pushButton_fs_add_goal.clicked.connect(self.onAddGoal)
        u.pushButton_fs_remove_goal.clicked.connect(self.onRemoveGoal)
        u.listView_fs_goals.selectionModel().currentChanged.connect(self.onGoalSelected)
        u.pushButton_fs_goal_spec_add.clicked.connect(self.onAddGoalSpec)
        u.pushButton_fs_goal_spec_remove.clicked.connect(self.onRemoveGoalSpec)
        u.listView_fs_goal_specs.selectionModel().currentChanged.connect(self.onGoalSpecSelected)

        # Connect plan signals
        u.pushButton_fs_add_plan.clicked.connect(self.onAddPlan)
        u.pushButton_fs_remove_plan.clicked.connect(self.onRemovePlan)
        u.listView_fs_plans.selectionModel().currentChanged.connect(self.onPlanSelected)
        u.pushButton_fs_plan_goal_sequence_step_add.clicked.connect(self.onAddPlanStep)
        u.pushButton_fs_plan_goal_sequence_step_remove.clicked.connect(self.onRemovePlanStep)
        u.listView_fs_plan_goal_sequence.selectionModel().currentChanged.connect(self.onPlanStepSelected)
        u.comboBox_fs_plan_goal_sequence_step_goal.currentTextChanged.connect(self.onPlanStepGoalChanged)
        u.comboBox_fs_plan_goal_sequence_step_bidding_logic.currentTextChanged.connect(self.onPlanStepLogicChanged)

        # Connect mission signals
        u.pushButton_fs_add_mission.clicked.connect(self.onAddMission)
        u.pushButton_fs_remove_mission.clicked.connect(self.onRemoveMission)
        u.listView_fs_missions.selectionModel().currentChanged.connect(self.onMissionSelected)
        u.pushButton_fs_mission_goal_add.clicked.connect(self.onAddMissionGoal)
        u.pushButton_fs_mission_goal_remove.clicked.connect(self.onRemoveMissionGoal)
        u.listView_fs_mission_goals.selectionModel().currentChanged.connect(self.onMissionGoalSelected)
        u.comboBox_fs_mission_goal_select.currentTextChanged.connect(self.onMissionGoalComboBoxChanged)

        # Connect inspection signals
        u.toolButton_fs_refresh_inspection.clicked.connect(lambda: self.refreshInspection(user_triggered=True))
        u.tabWidget_moise.currentChanged.connect(self.switchTab)

        # Connect detail edits for goals
        u.lineEdit_fs_goal_description.editingFinished.connect(self.onGoalDescriptionChanged)
        u.plainTextEdit_fs_goal_skill_requirements.textChanged.connect(self.onGoalSkillReqChanged)
        u.checkBox_fs_goal_abstract.toggled.connect(self.onGoalAbstractToggled)

        # Connect detail edits for plans
        u.lineEdit_fs_plan_description.editingFinished.connect(self.onPlanDescriptionChanged)

        # Connect detail edits for missions
        u.lineEdit_fs_mission_description.editingFinished.connect(self.onMissionDescriptionChanged)
        u.spinBox_fs_mission_assignment_cardinality_min.valueChanged.connect(self.onMissionCardMinChanged)
        u.spinBox_fs_mission_assignment_cardinality_max.valueChanged.connect(self.onMissionCardMaxChanged)

        # Connect spec detail edits
        u.lineEdit_fs_goal_spec_type.editingFinished.connect(self.onSpecTypeChanged)
        u.plainTextEdit_fs_goal_spec_description.textChanged.connect(self.onSpecDescriptionChanged)

        # Connect plot button to open/update non-blocking plot window
        u.pushButton_fs_plans_plot.clicked.connect(self.onPlotPlans)
        u.action_plot_Plan_Structure.triggered.connect(self.onPlotPlans)

        # Setup dirty tracking signals
        self.setup_dirty_tracking()

        # Modeless plot window placeholders
        self.plot_window = None
        self.plot_label = None

        # Initialize view data
        self.refreshSchemeList()
        self.onSchemeChanged()

        # Final reset of dirty flag
        self._suppress_dirty = False
        self.dirty = False
        self.update_title()

    # Refresh list models
    def refreshSchemeList(self):
        combo = self.ui.comboBox_fs_social_scheme
        model = self.model_schemes
        prev = combo.currentText()
        schemes = list(self.ui.organisation.moise_model.functional_specification.social_schemes_names)
        model.setStringList(schemes)

        # restore selection
        combo.blockSignals(True)
        if schemes:
            idx = schemes.index(prev) if prev in schemes else 0
            combo.setCurrentIndex(idx)
        else:
            combo.setCurrentIndex(-1)
        combo.blockSignals(False)

        # propagate change
        self.onSchemeChanged()

    # Scheme handlers
    def onAddScheme(self):
        name, ok = QInputDialog.getText(self, "Add Scheme", "Scheme name:")
        if ok and name:
            try:
                self.ui.organisation.moise_model.functional_specification.add_social_scheme(name)

                self.refreshData()

                idx = self.model_schemes.stringList().index(name)
                self.ui.comboBox_fs_social_scheme.setCurrentIndex(idx)

            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    def onRemoveScheme(self):
        name = self.ui.comboBox_fs_social_scheme.currentText()
        if name:
            self.ui.organisation.moise_model.functional_specification.remove_social_scheme(name)

            self.refreshData()

    def onSchemeChanged(self):
        scheme = self.ui.comboBox_fs_social_scheme.currentText()

        # switch the stacked‐widget page
        if not scheme:
            # no scheme → show the "empty/hidden" page
            self.ui.stackedWidget_fs_social_scheme.setCurrentIndex(HIDDEN)
            self.clearDetailViews()
            self.ui.lineEdit_fs_social_scheme_description.clear()
            # you can early-return here if you don't want to populate anything
            return
        else:
            # scheme exists → show the real UI
            self.ui.stackedWidget_fs_social_scheme.setCurrentIndex(VISIBLE)

        # now populate the fields for the selected scheme…
        ss = self.ui.organisation.moise_model.functional_specification.get_social_scheme(scheme)
        desc = ss.get("description", "")
        self.ui.lineEdit_fs_social_scheme_description.setText(desc)

    def onSchemeDescriptionChanged(self):
        """
        Save edits to the current scheme's description,
        and mark the document modified.
        """
        scheme = self.ui.comboBox_fs_social_scheme.currentText()
        if not scheme:
            return

        self.refreshData()

        new_desc = self.ui.lineEdit_fs_social_scheme_description.text()
        # write it back into your FS data model
        self.ui.organisation.moise_model.functional_specification.get_social_scheme(scheme)["description"] = new_desc

    # Clear detail view fields
    def clearDetailViews(self):
        u = self.ui
        # Goals
        u.lineEdit_fs_goal_description.clear()
        u.plainTextEdit_fs_goal_skill_requirements.clear()
        u.checkBox_fs_goal_abstract.setChecked(False)
        self.model_goal_specs.setStringList([])
        u.lineEdit_fs_goal_spec_type.clear()
        u.plainTextEdit_fs_goal_spec_description.clear()
        # Plans
        u.lineEdit_fs_plan_description.clear()
        self.model_plan_steps.setStringList([])
        # Missions
        u.lineEdit_fs_mission_description.clear()
        u.spinBox_fs_mission_assignment_cardinality_min.setValue(0)
        u.spinBox_fs_mission_assignment_cardinality_max.setValue(0)
        self.model_mission_goals.setStringList([])

    # --- Goal handlers ---
    def refreshGoals(self):
        scheme = self.ui.comboBox_fs_social_scheme.currentText()
        if not scheme:
            return

        goals = list(
            self.ui.organisation.moise_model.functional_specification.get_social_scheme(scheme)
            .get("goals", {})
            .keys()
        )
        view = self.ui.listView_fs_goals
        model = self.model_goals

        # remember old selection
        prev = view.currentIndex().data()

        # reset
        model.setStringList(goals)
        self.ui.stackedWidget_fs_goal.setCurrentIndex(VISIBLE if goals else HIDDEN)

        # restore or clear
        if goals:
            idx_val = goals.index(prev) if prev in goals else 0
            new_idx = model.index(idx_val, 0)
            sel = view.selectionModel()
            sel.clearSelection()
            view.setCurrentIndex(new_idx)
            sel.select(new_idx, QItemSelectionModel.Select | QItemSelectionModel.Rows)
            view.scrollTo(new_idx)

        else:
            view.selectionModel().clearSelection()

    def onAddGoal(self):
        text, ok = QInputDialog.getText(self, "Add Goal", "Goal name:")
        if not (ok and text):
            return

        try:
            scheme = self.ui.comboBox_fs_social_scheme.currentText()
            self.ui.organisation.moise_model.functional_specification.add_goal(
                scheme, text,
                description="", skill_requirements=[],
                abstract=False, instance_generation_logic="",
                specs={}
            )

            self.refreshData()

            # now select the newly added goal
            goals = self.model_goals.stringList()
            row = goals.index(text) if text in goals else 0
            idx = self.model_goals.index(row, 0)
            view = self.ui.listView_fs_goals
            sel_model = view.selectionModel()

            sel_model.clearSelection()
            view.setCurrentIndex(idx)
            sel_model.select(
                idx,
                QItemSelectionModel.Select | QItemSelectionModel.Rows
            )
            view.scrollTo(idx)
            view.setFocus()

        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def onRemoveGoal(self):
        name = self.ui.listView_fs_goals.currentIndex().data()
        if name:
            self.ui.organisation.moise_model.functional_specification.remove_goal(name)
            self.refreshData()

    def onGoalSelected(self, current: QModelIndex, previous: QModelIndex):
        name = current.data()
        u = self.ui

        # suppress all dirty signalling while we reshape the UI
        self._suppress_dirty = True
        try:
            # ① if nothing selected, clear and hide
            if not name:
                u.stackedWidget_fs_goal.setCurrentIndex(HIDDEN)
                # block every widget that could fire mark_dirty()
                with QSignalBlocker(u.lineEdit_fs_goal_description), \
                        QSignalBlocker(u.plainTextEdit_fs_goal_skill_requirements), \
                        QSignalBlocker(u.checkBox_fs_goal_abstract), \
                        QSignalBlocker(u.lineEdit_fs_goal_spec_type), \
                        QSignalBlocker(u.plainTextEdit_fs_goal_spec_description):
                    u.lineEdit_fs_goal_description.clear()
                    u.plainTextEdit_fs_goal_skill_requirements.clear()
                    # clear specs list
                    self.model_goal_specs.setStringList([])
                    u.lineEdit_fs_goal_spec_type.clear()
                    u.plainTextEdit_fs_goal_spec_description.clear()
                return

            u.stackedWidget_fs_goal.setCurrentIndex(VISIBLE)
            g = self.ui.organisation.moise_model.functional_specification.get_goal(name)

            # ⑤ clear skill-detail fields under blocker
            with QSignalBlocker(u.lineEdit_fs_goal_description), \
                    QSignalBlocker(u.plainTextEdit_fs_goal_skill_requirements), \
                    QSignalBlocker(u.checkBox_fs_goal_abstract):

                u.lineEdit_fs_goal_description.setText(g.get("description", ""))
                u.plainTextEdit_fs_goal_skill_requirements.setPlainText(
                    ",".join(g.get("skill_requirements", []))
                )
                u.checkBox_fs_goal_abstract.setChecked(g.get("abstract", False))

            # ⑤ clear spec-detail fields under blocker
            with QSignalBlocker(u.lineEdit_fs_goal_spec_type), \
                    QSignalBlocker(u.plainTextEdit_fs_goal_spec_description):

                u.lineEdit_fs_goal_spec_type.clear()
                u.plainTextEdit_fs_goal_spec_description.clear()

                self.refreshGoalSpecs()

        finally:
            # turn dirty-watching back on
            self._suppress_dirty = False

    # --- Goal spec handlers ---
    def refreshGoalSpecs(self):
        view = self.ui.listView_fs_goal_specs
        model = self.model_goal_specs

        # determine new and old
        prev_key = view.currentIndex().data()
        gname = self.ui.listView_fs_goals.currentIndex().data()
        new_specs = (
            list(
                self.ui.organisation.moise_model.functional_specification
                .get_goal(gname)
                .get("specs", {})
                .keys()
            )
            if gname else []
        )

        # reset
        model.setStringList(new_specs)
        self.ui.stackedWidget_fs_goal_spec.setCurrentIndex(
            VISIBLE if new_specs else HIDDEN
        )

        # select
        if new_specs:
            if prev_key in new_specs:
                row = new_specs.index(prev_key)
            else:
                row = 0

            idx = model.index(row, 0)
            sel = view.selectionModel()
            sel.clearSelection()
            view.setCurrentIndex(idx)
            sel.select(idx, QItemSelectionModel.Select | QItemSelectionModel.Rows)
            view.scrollTo(idx)

        else:
            view.selectionModel().clearSelection()

    def onAddGoalSpec(self):
        btn = self.ui.pushButton_fs_goal_spec_add

        # 1) Temporarily remove the auto-mark_dirty connection
        try:
            btn.clicked.disconnect(self.mark_dirty)
        except (TypeError, RuntimeError):
            pass

        # 2) Prompt for key/type/description
        key, ok1 = QInputDialog.getText(self, "Add Spec Key", "Key:")
        if not (ok1 and key):
            btn.clicked.connect(self.mark_dirty)
            return
        typ, ok2 = QInputDialog.getText(self, "Add Spec Type", "Type (str,int,...):")
        if not (ok2 and typ):
            btn.clicked.connect(self.mark_dirty)
            return
        desc, ok3 = QInputDialog.getText(self, "Add Spec Description", "Description:")
        if not (ok3 and desc):
            btn.clicked.connect(self.mark_dirty)
            return

        # 3) Update the data model
        gname = self.ui.listView_fs_goals.currentIndex().data()
        if not gname:
            btn.clicked.connect(self.mark_dirty)
            return
        goal = self.ui.organisation.moise_model.functional_specification.get_goal(gname)
        specs = goal.setdefault("specs", {})
        specs[key] = {"type": typ, "description": desc}

        # 4) Rebuild the list model
        spec_keys = list(specs.keys())
        self.model_goal_specs.setStringList(spec_keys)

        # 5) Clear the detail fields WITHOUT firing textChanged
        with QSignalBlocker(self.ui.lineEdit_fs_goal_spec_type), \
                QSignalBlocker(self.ui.plainTextEdit_fs_goal_spec_description):
            self.ui.lineEdit_fs_goal_spec_type.clear()
            self.ui.plainTextEdit_fs_goal_spec_description.clear()

        self.refreshData()

        # 7) Now explicitly select the newly-added spec (last row)
        view = self.ui.listView_fs_goal_specs
        sel = view.selectionModel()
        sel.clearSelection()
        last = len(spec_keys) - 1
        idx = self.model_goal_specs.index(last, 0)
        view.setCurrentIndex(idx)
        sel.select(idx, QItemSelectionModel.Select | QItemSelectionModel.Rows)
        view.scrollTo(idx)
        view.setFocus()

        # 8) Restore the auto-mark_dirty connection
        btn.clicked.connect(self.mark_dirty)

    def onRemoveGoalSpec(self):
        gname = self.ui.listView_fs_goals.currentIndex().data()
        key   = self.ui.listView_fs_goal_specs.currentIndex().data()
        if not (gname and key):
            return

        # Update the model
        goal = self.ui.organisation.moise_model.functional_specification.get_goal(gname)
        goal.get("specs", {}).pop(key, None)

        # Refresh UI
        remaining = list(goal.get("specs", {}).keys())
        self.model_goal_specs.setStringList(remaining)
        self.ui.lineEdit_fs_goal_spec_type.clear()
        self.ui.plainTextEdit_fs_goal_spec_description.clear()

        self.refreshData()

        # Reselect (or clear) the listView
        if remaining:
            newKey = remaining[min(self.ui.listView_fs_goal_specs.currentIndex().row(), len(remaining)-1)]
            idx = self.model_goal_specs.stringList().index(newKey)
            self.ui.listView_fs_goal_specs.setCurrentIndex(self.model_goal_specs.index(idx))
        else:
            self.ui.listView_fs_goal_spec_type.clear()
            self.ui.plainTextEdit_fs_goal_spec_description.clear()

    def onGoalSpecSelected(self, current: QModelIndex, previous: QModelIndex):
        # 1) suppress any mark_dirty() while we rebuild the UI
        self._suppress_dirty = True
        try:
            key = current.data()
            if not key:
                self.ui.stackedWidget_fs_goal_spec.setCurrentIndex(HIDDEN)
                with QSignalBlocker(self.ui.lineEdit_fs_goal_spec_type), \
                        QSignalBlocker(self.ui.plainTextEdit_fs_goal_spec_description):
                    self.ui.lineEdit_fs_goal_spec_type.clear()
                    self.ui.plainTextEdit_fs_goal_spec_description.clear()
                return

            # 2) show the detail page
            self.ui.stackedWidget_fs_goal_spec.setCurrentIndex(VISIBLE)

            # 3) fetch the spec from the model
            gname = self.ui.listView_fs_goals.currentIndex().data()
            spec = self.ui.organisation.moise_model.functional_specification \
                .get_goal(gname) \
                .get("specs", {}) \
                .get(key, {})

            # 4) block the widgets’ signals while setting them
            with QSignalBlocker(self.ui.lineEdit_fs_goal_spec_type), \
                    QSignalBlocker(self.ui.plainTextEdit_fs_goal_spec_description):
                self.ui.lineEdit_fs_goal_spec_type.setText(spec.get("type", ""))
                self.ui.plainTextEdit_fs_goal_spec_description.setPlainText(
                    spec.get("description", "")
                )

        finally:
            # 5) turn dirty-tracking back on
            self._suppress_dirty = False

    def onSpecTypeChanged(self):
        key = self.ui.listView_fs_goal_specs.currentIndex().data()
        gname = self.ui.listView_fs_goals.currentIndex().data()
        if key and gname:
            val = self.ui.lineEdit_fs_goal_spec_type.text()
            self.ui.organisation.moise_model.functional_specification.get_goal(gname)["specs"][key]["type"] = val

            self.refreshData()

    def onSpecDescriptionChanged(self):
        key = self.ui.listView_fs_goal_specs.currentIndex().data()
        gname = self.ui.listView_fs_goals.currentIndex().data()
        if key and gname:
            val = self.ui.plainTextEdit_fs_goal_spec_description.toPlainText()
            self.ui.organisation.moise_model.functional_specification.get_goal(gname)["specs"][key]["description"] = val

            self.refreshData()

    # Goal detail edits
    def onGoalDescriptionChanged(self):
        name = self.ui.listView_fs_goals.currentIndex().data()
        if name:
            self.ui.organisation.moise_model.functional_specification.get_goal(name)["description"] = self.ui.lineEdit_fs_goal_description.text()

            self.refreshData()

    def onGoalSkillReqChanged(self):
        name = self.ui.listView_fs_goals.currentIndex().data()
        if name:
            text = self.ui.plainTextEdit_fs_goal_skill_requirements.toPlainText()
            skills = [s.strip() for s in text.split(',') if s.strip()]
            self.ui.organisation.moise_model.functional_specification.get_goal(name)["skill_requirements"] = skills

            self.refreshData()

    def onGoalAbstractToggled(self, checked: bool):
        name = self.ui.listView_fs_goals.currentIndex().data()
        if name:
            self.ui.organisation.moise_model.functional_specification.get_goal(name)["abstract"] = checked

            self.refreshData()

    # --- Plan handlers ---
    def refreshPlans(self):
        scheme = self.ui.comboBox_fs_social_scheme.currentText()
        if not scheme:
            return

        plans = list(
            self.ui.organisation.moise_model.functional_specification
            .get_social_scheme(scheme)
            .get("plans", {})
            .keys()
        )
        view = self.ui.listView_fs_plans
        model = self.model_plans

        # remember old
        prev = view.currentIndex().data()

        # reset
        model.setStringList(plans)
        self.ui.stackedWidget_fs_plan.setCurrentIndex(VISIBLE if plans else HIDDEN)

        # restore
        if plans:
            idx_val = plans.index(prev) if prev in plans else 0
            new_idx = model.index(idx_val, 0)
            sel = view.selectionModel()
            sel.clearSelection()
            view.setCurrentIndex(new_idx)
            sel.select(new_idx, QItemSelectionModel.Select | QItemSelectionModel.Rows)
            view.scrollTo(new_idx)

        else:
            view.selectionModel().clearSelection()

    def onAddPlan(self):
        text, ok = QInputDialog.getText(self, "Add Plan", "Plan name:")
        if not (ok and text):
            return
        try:
            scheme = self.ui.comboBox_fs_social_scheme.currentText()
            self.ui.organisation.moise_model.functional_specification.add_plan(
                scheme, text, goal_sequence=[], description=""
            )

            self.refreshData()

            # 2) select the newly added plan
            plans = self.model_plans.stringList()
            row = plans.index(text)
            idx = self.model_plans.index(row, 0)
            view = self.ui.listView_fs_plans
            sel = view.selectionModel()
            sel.clearSelection()
            view.setCurrentIndex(idx)
            sel.select(idx, QItemSelectionModel.Select | QItemSelectionModel.Rows)
            view.scrollTo(idx)
            view.setFocus()
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def onRemovePlan(self):
        name = self.ui.listView_fs_plans.currentIndex().data()
        if name:
            self.ui.organisation.moise_model.functional_specification.remove_plan(name)
            self.refreshData()

    def onPlanSelected(self, current: QModelIndex, previous: QModelIndex):
        name = current.data()
        u = self.ui

        # suppress dirty‐marking while we rebuild the UI
        self._suppress_dirty = True
        try:
            # ① nothing selected → clear & hide everything
            if not name:
                u.stackedWidget_fs_plan.setCurrentIndex(HIDDEN)
                with QSignalBlocker(u.lineEdit_fs_plan_description), \
                        QSignalBlocker(u.comboBox_fs_plan_goal_sequence_step_goal), \
                        QSignalBlocker(u.comboBox_fs_plan_goal_sequence_step_bidding_logic):
                    u.lineEdit_fs_plan_description.clear()
                    self.model_plan_steps.setStringList([])
                    u.stackedWidget_fs_plan_goal_sequence_goal.setCurrentIndex(HIDDEN)
                    u.comboBox_fs_plan_goal_sequence_step_goal.clear()
                    u.comboBox_fs_plan_goal_sequence_step_bidding_logic.clear()
                return

            # ② show the plan editor
            u.stackedWidget_fs_plan.setCurrentIndex(VISIBLE)

            # ③ populate description under blocker
            p = self.ui.organisation.moise_model.functional_specification.get_plan(name)
            with QSignalBlocker(u.lineEdit_fs_plan_description):
                u.lineEdit_fs_plan_description.setText(p.get("description", ""))

                self.refreshPlanSteps()

        finally:
            # re‐enable dirty‐tracking
            self._suppress_dirty = False

    # --- Plan step handlers ---
    def refreshPlanSteps(self):
        view = self.ui.listView_fs_plan_goal_sequence
        model = self.model_plan_steps

        # determine new and old
        prev_key = view.currentIndex().data()
        sname = self.ui.listView_fs_plans.currentIndex().data()
        new_steps = [
            step['goal'] for step in
            self.ui.organisation.moise_model.functional_specification
                .get_plan(sname)
                .get('goal_sequence', [])
        ] if sname else []

        # reset
        model.setStringList(new_steps)
        self.ui.stackedWidget_fs_plan_goal_sequence_goal.setCurrentIndex(
            VISIBLE if new_steps else HIDDEN
        )

        # select
        if new_steps:
            if prev_key in new_steps:
                row = new_steps.index(prev_key)
            else:
                row = 0

            idx = model.index(row, 0)
            sel = view.selectionModel()
            sel.clearSelection()
            view.setCurrentIndex(idx)
            sel.select(idx, QItemSelectionModel.Select | QItemSelectionModel.Rows)
            view.scrollTo(idx)

        else:
            view.selectionModel().clearSelection()

    def onAddPlanStep(self):
        goals = self.ui.organisation.moise_model.functional_specification.goal_names
        if not goals:
            QMessageBox.warning(self, "No Goals Defined", "Please add at least one goal before adding a plan step.")
            return

        goal, ok = QInputDialog.getItem(
            self, "Add Plan Step", "Select Goal:", goals, 0, False
        )
        if not (ok and goal):
            return
        logic, ok2 = QInputDialog.getText(self, "Bidding Logic", "Logic (optional):")
        if not ok2:
            return

        plan_name = self.ui.listView_fs_plans.currentIndex().data()
        if plan_name:
            p = self.ui.organisation.moise_model.functional_specification.get_plan(plan_name)
            p.setdefault("goal_sequence", []).append({"goal": goal, "bidding_logic": logic or None})

            self.refreshData()

            # 2) select the newly added step (last row)
            row = self.model_plan_steps.rowCount() - 1
            idx = self.model_plan_steps.index(row, 0)
            view = self.ui.listView_fs_plan_goal_sequence
            sel = view.selectionModel()
            sel.clearSelection()
            view.setCurrentIndex(idx)
            sel.select(idx, QItemSelectionModel.Select | QItemSelectionModel.Rows)
            view.scrollTo(idx)
            view.setFocus()

    def onRemovePlanStep(self):
        idx = self.ui.listView_fs_plan_goal_sequence.currentIndex().row()
        name = self.ui.listView_fs_plans.currentIndex().data()
        if name:
            p = self.ui.organisation.moise_model.functional_specification.get_plan(name)
            try:
                p.get("goal_sequence", []).pop(idx)

                self.refreshData()

            except:
                pass
            self.onPlanSelected(self.ui.listView_fs_plans.currentIndex(), None)

    def onPlanStepGoalChanged(self, new_goal):
        plan_name = self.ui.listView_fs_plans.currentIndex().data()
        idx = self.ui.listView_fs_plan_goal_sequence.currentIndex().row()
        if plan_name is not None and idx >= 0:
            self.ui.organisation.moise_model.functional_specification.get_plan(plan_name)["goal_sequence"][idx]["goal"] = new_goal

            self.refreshData()

            self.onPlanSelected(self.ui.listView_fs_plans.currentIndex(), None)

    def onPlanStepLogicChanged(self, new_logic):
        plan_name = self.ui.listView_fs_plans.currentIndex().data()
        idx = self.ui.listView_fs_plan_goal_sequence.currentIndex().row()
        if plan_name is not None and idx >= 0:
            self.ui.organisation.moise_model.functional_specification.get_plan(plan_name)["goal_sequence"][idx]["bidding_logic"] = new_logic or None

            self.refreshData()


    def onPlanStepSelected(self, current: QModelIndex, previous: QModelIndex):
        self._suppress_dirty = True
        try:
            row = current.row()
            if row < 0:
                self.ui.stackedWidget_fs_plan_goal_sequence_goal.setCurrentIndex(HIDDEN)
                self.ui.comboBox_fs_plan_goal_sequence_step_goal.clear()
                self.ui.comboBox_fs_plan_goal_sequence_step_bidding_logic.clear()
                return

            self.ui.stackedWidget_fs_plan_goal_sequence_goal.setCurrentIndex(VISIBLE)
            plan_name = self.ui.listView_fs_plans.currentIndex().data()
            step = self.ui.organisation.moise_model.functional_specification.get_plan(plan_name)["goal_sequence"][row]

            # block & refill the “goal” combo
            with QSignalBlocker(self.ui.comboBox_fs_plan_goal_sequence_step_goal):
                self.ui.comboBox_fs_plan_goal_sequence_step_goal.clear()
                self.ui.comboBox_fs_plan_goal_sequence_step_goal.addItems(
                    self.ui.organisation.moise_model.functional_specification.goal_names
                )
                self.ui.comboBox_fs_plan_goal_sequence_step_goal.setCurrentText(step["goal"])

            # block & refill the “logic” combo
            logic_options = ["", "greedy", "random", "priority", "custom"]
            with QSignalBlocker(self.ui.comboBox_fs_plan_goal_sequence_step_bidding_logic):
                self.ui.comboBox_fs_plan_goal_sequence_step_bidding_logic.clear()
                self.ui.comboBox_fs_plan_goal_sequence_step_bidding_logic.addItems(logic_options)
                self.ui.comboBox_fs_plan_goal_sequence_step_bidding_logic.setCurrentText(
                    step.get("bidding_logic") or ""
                )
        finally:
            self._suppress_dirty = False

    def onPlanDescriptionChanged(self):
        name = self.ui.listView_fs_plans.currentIndex().data()
        if name:
            self.ui.organisation.moise_model.functional_specification.get_plan(name)["description"] = self.ui.lineEdit_fs_plan_description.text()

            self.refreshData()

    # --- Mission handlers ---
    def refreshMissions(self):
        scheme = self.ui.comboBox_fs_social_scheme.currentText()
        if not scheme:
            return

        missions = list(
            self.ui.organisation.moise_model.functional_specification
            .get_social_scheme(scheme)
            .get("missions", {})
            .keys()
        )
        view = self.ui.listView_fs_missions
        model = self.model_missions

        # remember old
        prev = view.currentIndex().data()

        # reset
        model.setStringList(missions)
        self.ui.stackedWidget_fs_mission.setCurrentIndex(VISIBLE if missions else HIDDEN)

        # restore
        if missions:
            idx_val = missions.index(prev) if prev in missions else 0
            new_idx = model.index(idx_val, 0)
            sel = view.selectionModel()
            sel.clearSelection()
            view.setCurrentIndex(new_idx)
            sel.select(new_idx, QItemSelectionModel.Select | QItemSelectionModel.Rows)
            view.scrollTo(new_idx)

        else:
            view.selectionModel().clearSelection()

    def onAddMission(self):
        text, ok = QInputDialog.getText(self, "Add Mission", "Mission name:")
        if not (ok and text):
            return
        try:
            scheme = self.ui.comboBox_fs_social_scheme.currentText()
            self.ui.organisation.moise_model.functional_specification.add_mission(
                scheme, text, description="", goals=[], assignment_cardinality={"min": 0, "max": None}
            )

            self.refreshData()

            # 2) select the newly added mission
            missions = self.model_missions.stringList()
            row = missions.index(text)
            idx = self.model_missions.index(row, 0)
            view = self.ui.listView_fs_missions
            sel = view.selectionModel()
            sel.clearSelection()
            view.setCurrentIndex(idx)
            sel.select(idx, QItemSelectionModel.Select | QItemSelectionModel.Rows)
            view.scrollTo(idx)
            view.setFocus()
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def onRemoveMission(self):
        name = self.ui.listView_fs_missions.currentIndex().data()
        if name:
            self.ui.organisation.moise_model.functional_specification.remove_mission(name)

            self.refreshData()

    def onMissionSelected(self, current: QModelIndex, previous: QModelIndex):
        name = current.data()
        u = self.ui

        # suppress dirty‐marking while we rebuild the UI
        self._suppress_dirty = True
        try:
            # ① nothing selected → clear & hide
            if not name:
                u.stackedWidget_fs_mission.setCurrentIndex(HIDDEN)
                with QSignalBlocker(u.lineEdit_fs_mission_description), \
                        QSignalBlocker(u.spinBox_fs_mission_assignment_cardinality_min), \
                        QSignalBlocker(u.spinBox_fs_mission_assignment_cardinality_max), \
                        QSignalBlocker(u.comboBox_fs_mission_goal_select):
                    u.lineEdit_fs_mission_description.clear()
                    u.spinBox_fs_mission_assignment_cardinality_min.setValue(0)
                    u.spinBox_fs_mission_assignment_cardinality_max.setValue(0)
                    self.model_mission_goals.setStringList([])
                    u.stackedWidget_fs_mission_goals_goal.setCurrentIndex(HIDDEN)
                    u.comboBox_fs_mission_goal_select.clear()
                return

            u.stackedWidget_fs_mission.setCurrentIndex(VISIBLE)
            m = self.ui.organisation.moise_model.functional_specification.get_mission(name)

            with QSignalBlocker(u.lineEdit_fs_mission_description), \
                    QSignalBlocker(u.spinBox_fs_mission_assignment_cardinality_min), \
                        QSignalBlocker(u.spinBox_fs_mission_assignment_cardinality_max):
                u.lineEdit_fs_mission_description.setText(m.get("description", ""))
                u.spinBox_fs_mission_assignment_cardinality_min.setValue(m.get("assignment_cardinality", {}).get("min", 0))
                u.spinBox_fs_mission_assignment_cardinality_max.setValue(m.get("assignment_cardinality", {}).get("max") or 0)

                self.refreshMissionGoals()

        finally:
            # re-enable dirty‐tracking
            self._suppress_dirty = False

    # Mission goal handlers
    def refreshMissionGoals(self):
        view = self.ui.listView_fs_mission_goals
        model = self.model_mission_goals

        # determine new and old
        prev_key = view.currentIndex().data()
        name = self.ui.listView_fs_missions.currentIndex().data()
        new_goals = (
            self.ui.organisation.moise_model.functional_specification.get_mission(name)
            .get('goals', [])
        ) if name else []

        # reset
        model.setStringList(new_goals)
        self.ui.stackedWidget_fs_mission_goals_goal.setCurrentIndex(
            VISIBLE if new_goals else HIDDEN
        )

        # restore or clear
        if new_goals:
            if prev_key in new_goals:
                row = new_goals.index(prev_key)
            else:
                row = 0

            idx = model.index(row, 0)
            sel = view.selectionModel()
            sel.clearSelection()
            view.setCurrentIndex(idx)
            sel.select(idx, QItemSelectionModel.Select | QItemSelectionModel.Rows)
            view.scrollTo(idx)

        else:
            view.selectionModel().clearSelection()

    def onMissionGoalSelected(self, current: QModelIndex, previous: QModelIndex):
        self._suppress_dirty = True
        try:
            goal = current.data()
            combobox = self.ui.comboBox_fs_mission_goal_select

            if not goal:
                self.ui.stackedWidget_fs_mission_goals_goal.setCurrentIndex(HIDDEN)
                combobox.clear()
                return

            self.ui.stackedWidget_fs_mission_goals_goal.setCurrentIndex(VISIBLE)
            with QSignalBlocker(combobox):
                combobox.clear()
                combobox.addItems(self.ui.organisation.moise_model.functional_specification.goal_names)
                combobox.setCurrentText(goal)
        finally:
            self._suppress_dirty = False

    def onMissionGoalComboBoxChanged(self, new_goal):
        mission_name = self.ui.listView_fs_missions.currentIndex().data()
        goal_index = self.ui.listView_fs_mission_goals.currentIndex().row()

        if mission_name and goal_index >= 0:
            mission = self.ui.organisation.moise_model.functional_specification.get_mission(mission_name)

            self.refreshData()

            mission_goals = mission.get("goals", [])
            if 0 <= goal_index < len(mission_goals):
                mission_goals[goal_index] = new_goal
                self.onMissionSelected(self.ui.listView_fs_missions.currentIndex(), None)  # Refresh

    def onAddMissionGoal(self):
        goals = self.ui.organisation.moise_model.functional_specification.goal_names
        if not goals:
            QMessageBox.warning(self, "No Goals Defined", "Please add at least one goal before adding to a mission.")
            return

        goal, ok = QInputDialog.getItem(
            self, "Add Mission Goal", "Select Goal:", goals, 0, False
        )
        if not (ok and goal):
            return

        mission_name = self.ui.listView_fs_missions.currentIndex().data()
        if mission_name:
            m = self.ui.organisation.moise_model.functional_specification.get_mission(mission_name)
            m.setdefault("goals", []).append(goal)

            self.refreshData()

            # 2) select the newly added mission goal (last row)
            row = self.model_mission_goals.rowCount() - 1
            idx = self.model_mission_goals.index(row, 0)
            view = self.ui.listView_fs_mission_goals
            sel = view.selectionModel()
            sel.clearSelection()
            view.setCurrentIndex(idx)
            sel.select(idx, QItemSelectionModel.Select | QItemSelectionModel.Rows)
            view.scrollTo(idx)
            view.setFocus()

    def onRemoveMissionGoal(self):
        idx = self.ui.listView_fs_mission_goals.currentIndex().row()
        name = self.ui.listView_fs_missions.currentIndex().data()
        if name:
            m = self.ui.organisation.moise_model.functional_specification.get_mission(name)
            try:
                m.get("goals",[]).pop(idx)

                self.refreshData()

            except:
                pass
            self.onMissionSelected(self.ui.listView_fs_missions.currentIndex(), None)

    # Mission detail edits
    def onMissionDescriptionChanged(self):
        name = self.ui.listView_fs_missions.currentIndex().data()
        if name:
            self.ui.organisation.moise_model.functional_specification.get_mission(name)["description"] = self.ui.lineEdit_fs_mission_description.text()

            self.refreshData()

    def onMissionCardMinChanged(self, val: int):
        name = self.ui.listView_fs_missions.currentIndex().data()
        if name:
            mission = self.ui.organisation.moise_model.functional_specification.get_mission(name)
            max_val = mission["assignment_cardinality"].get("max", None)

            # If the last max value is not zero or None and min exceeds max, adjust max
            if max_val is not None and max_val != 0 and val > self.last_max_value:
                mission["assignment_cardinality"]["max"] = val
                self.ui.spinBox_fs_mission_assignment_cardinality_max.setValue(val)

            # Update the last known min value
            self.last_min_value = val
            mission["assignment_cardinality"]["min"] = val

            # If max is None or zero, leave max unchanged
            if max_val is None or max_val == 0:
                self.ui.spinBox_fs_mission_assignment_cardinality_max.setValue(0)  # Or any default value you'd like

            self.refreshData()

    def onMissionCardMaxChanged(self, val: int):
        name = self.ui.listView_fs_missions.currentIndex().data()
        if name:
            mission = self.ui.organisation.moise_model.functional_specification.get_mission(name)
            min_val = mission["assignment_cardinality"].get("min", 0)

            # If max is set to 0, reset to None (Unlimited)
            if val == 0:
                mission["assignment_cardinality"]["max"] = None
                self.ui.spinBox_fs_mission_assignment_cardinality_max.setSuffix(" (Unlimited)")
                self.last_max_value = 0

            elif val >= min_val:
                # If max is increased, ensure it is at least as high as the min
                mission["assignment_cardinality"]["max"] = val
                self.ui.spinBox_fs_mission_assignment_cardinality_max.setSuffix("")  # Clear the suffix
                self.last_max_value = val

            elif self.last_max_value == 0:
                # If max is increased, ensure it is at least as high as the min
                mission["assignment_cardinality"]["max"] = min_val
                self.ui.spinBox_fs_mission_assignment_cardinality_max.setSuffix("")  # Clear the suffix
                self.last_max_value = min_val

            else:
                mission["assignment_cardinality"]["max"] = 0
                self.ui.spinBox_fs_mission_assignment_cardinality_max.setValue(0)
                self.last_max_value = 0

            # Only set the value if max is not None
            max_value = mission["assignment_cardinality"].get("max", 0)
            if max_value is not None:
                self.ui.spinBox_fs_mission_assignment_cardinality_max.setValue(max_value)

            self.refreshData()

    # --- Verify & inspect ---
    def onVerify(self):
        errors = self.ui.organisation.moise_model.functional_specification.check_specification_definition(self.ui.organisation.moise_model.functional_specification, stop_at_first_error=False, verbose=0, return_errors=True)
        if not errors:
            QMessageBox.information(self, "Verify", "Specification is valid.")
        else:
            QMessageBox.information(self, "Verify", "Specification has errors:\n" + "\n".join(errors))

    def refreshInspection(self, user_triggered=False):
        #self.update_plot_window()

        # If user triggered it, update current_raw_view
        if user_triggered:
            self.ui.current_raw_view = "fs"

        if self.ui.current_raw_view != "fs":
            return  # Don't execute if triggered by signal and not in "ss" view

        raw = json.dumps(self.ui.organisation.moise_model.functional_specification.asdict(), indent=2)
        self.ui.plainTextEdit_raw.setPlainText(raw)

    def switchTab(self, index):
        if self.ui.tabWidget_moise.indexOf(self.ui.tab_fs) == index:
            self.refreshInspection(user_triggered=True)

    def onPlotPlans(self):
        """
        Opens or updates a modeless window showing the plan graph.
        """
        # create dialog+label on first click
        if self.plot_window is None:
            self.plot_window = QDialog(self)
            self.plot_window.setWindowTitle("Plan Graph")
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
            fig = self.ui.organisation.moise_model.functional_specification.plot_plan_graph(display_plot=False)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to plot plan structure:\n{e}")
            return

        # 2) Render to a PNG in memory
        buf = io.BytesIO()
        fig.savefig(buf, forQmat="png", dpi=150)
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
            u.pushButton_fs_add_social_scheme, u.pushButton_fs_remove_social_scheme,
            u.pushButton_fs_add_goal, u.pushButton_fs_remove_goal,
            u.pushButton_fs_goal_spec_add, u.pushButton_fs_goal_spec_remove,
            u.pushButton_fs_add_plan, u.pushButton_fs_remove_plan,
            u.pushButton_fs_plan_goal_sequence_step_add, u.pushButton_fs_plan_goal_sequence_step_remove,
            u.pushButton_fs_add_mission, u.pushButton_fs_remove_mission,
            u.pushButton_fs_mission_goal_add, u.pushButton_fs_mission_goal_remove
        ]
        for btn in buttons:
            btn.clicked.connect(self.mark_dirty)

        # Content edits
        u.lineEdit_fs_social_scheme_description.editingFinished.connect(self.mark_dirty)
        u.lineEdit_fs_goal_description.editingFinished.connect(self.mark_dirty)
        u.checkBox_fs_goal_abstract.toggled.connect(self.mark_dirty)
        u.lineEdit_fs_goal_spec_type.editingFinished.connect(self.mark_dirty)
        u.lineEdit_fs_plan_description.editingFinished.connect(self.mark_dirty)
        u.lineEdit_fs_mission_description.editingFinished.connect(self.mark_dirty)
        u.spinBox_fs_mission_assignment_cardinality_min.valueChanged.connect(self.mark_dirty)
        u.spinBox_fs_mission_assignment_cardinality_max.valueChanged.connect(self.mark_dirty)

    def mark_dirty(self):
        if self._suppress_dirty:
            return
        if not self.dirty:
            self.dirty = True

    def update_title(self):
        suffix = "*" if self.dirty else ""
        idx = self.ui.tabWidget_moise.indexOf(self.ui.tab_fs)
        self.ui.tabWidget_moise.setTabText(idx, f"{self._orig_fs_tab_title}{suffix}")

        if self.ui.current_file:
            # if we've opened or saved to a real path, show it
            self.ui.label_fs_file_name.setText(self.ui.current_file)
        else:
            # never saved yet → just show an ellipsis
            self.ui.label_fs_file_name.setText("…")

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

        # suppress any mark_dirty() until the new file is fully initialized
        self._suppress_dirty = True
        try:
            # create a fresh FunctionalSpecification
            self.ui.organisation.moise_model.functional_specification = FunctionalSpecification()
            self.ui.current_file = None

            # clear dirty flag & rebuild UI
            self.dirty = False
            self.refreshData(user_triggered=True)

            idx = self.ui.tabWidget_moise.indexOf(self.ui.tab_fs)
            if idx != -1:
                self.ui.tabWidget_moise.setCurrentIndex(idx)

        finally:
            # re-enable dirty-tracking so the next user edit marks dirty
            self._suppress_dirty = False

    def open_file(self):
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
            self, "Open Functional Specification", "", "Functional Specification Files (*.fs);;JSON Files (*.json);;All Files (*)"
        )
        if not path:
            return

        try:
            # suppress dirty-tracking during load & UI init
            self._suppress_dirty = True

            # load the JSON and replace your FS object
            with open(path, 'r') as f:
                data = json.load(f)

            self.ui.organisation.moise_model.functional_specification = FunctionalSpecification(data)
            self.ui.current_file = path

            # clear dirty flag & rebuild UI
            self.dirty = False
            self.refreshData(user_triggered=True)

            # Reset deontic specification
            self.ui.ds_widget.new_file(user_triggered=False)

            idx = self.ui.tabWidget_moise.indexOf(self.ui.tab_fs)
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
                self, "Save Functional Specification As", "", "Functional Specification Files (*.fs);;JSON Files (*.json);;All Files (*)"
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
                functional_specification=True,
                deontic_specification=False,
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
        """Refresh all lists to ensure the data is loaded properly."""
        print("Refresh FS")
        self._suppress_dirty = True
        try:
            self.refreshSchemeList()

            self.refreshGoals()
            self.refreshGoalSpecs()

            self.refreshPlans()
            self.refreshPlanSteps()

            self.refreshMissions()
            self.refreshMissionGoals()

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
