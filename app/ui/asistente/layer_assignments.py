"""Direct utility/role assignment in the sheet layer step."""
from PySide6 import QtWidgets
from hoja import pdf_layers
from reconocimiento import recognition as rec
from traduccion.i18n import t as _tr


class LayerAssignmentsMixin:
    def _init_assignments(self, roles):
        self._base_roles = {u: {k: list(v) for k, v in r.items()} for u, r in (roles or {}).items()}
        self._assignments = {}
        self._assignment_name = None
        self._assignments_changed = False
        self._automatic_names = set()
        self._touched_utilities = set(self._base_roles)
        for utility, roles in self._base_roles.items():
            for role in (rec.ROLE_LINEAS, rec.ROLE_BUZONES):
                for name in roles.get(role, ()):
                    self._assignments[name] = (utility, role)

    def _effective_layers(self):
        out = pdf_layers.without_letters(self._layers_raw, self._letters_off)
        return [dict(L, utility=self._assignments[L['name']][0],
                     assigned_role=self._assignments[L['name']][1],
                     letter_utilities=[], letter_codes={}, letter_paths={}, letters="")
                if L['name'] in self._assignments else L for L in out]

    def _build_assignment_controls(self, layout):
        self.assignment_label = QtWidgets.QLabel(_tr("Selecciona una capa para asignar su utilidad."))
        self.assignment_label.setWordWrap(True)
        layout.addWidget(self.assignment_label)
        form = QtWidgets.QFormLayout()
        self.assignment_utility = QtWidgets.QComboBox()
        self.assignment_utility.addItem(_tr("Automática"), "")
        for key, label in pdf_layers.UTILITIES:
            self.assignment_utility.addItem(_tr(label), key)
        self.assignment_role = QtWidgets.QComboBox()
        self.assignment_role.addItem(_tr("Líneas"), rec.ROLE_LINEAS)
        self.assignment_role.addItem(_tr("Estructuras"), rec.ROLE_BUZONES)
        form.addRow(_tr("Utilidad"), self.assignment_utility)
        form.addRow(_tr("Rol"), self.assignment_role)
        layout.addLayout(form)
        self.assignment_utility.setEnabled(False)
        self.assignment_role.setEnabled(False)
        self.assignment_utility.currentIndexChanged.connect(self._assign_selected_layer)
        self.assignment_role.currentIndexChanged.connect(self._assign_selected_layer)
        self.tree.currentItemChanged.connect(self._assignment_selection_changed)

    def _assignment_selection_changed(self, item, _previous=None):
        from ui.asistente.layer_dialog import _ROLE_NAME
        name = item.data(0, _ROLE_NAME) if item else None
        self._assignment_name = name
        for combo in (self.assignment_utility, self.assignment_role):
            combo.blockSignals(True)
        utility, role = self._assignments.get(name, ("", rec.ROLE_LINEAS))
        self.assignment_utility.setCurrentIndex(self.assignment_utility.findData(utility))
        self.assignment_role.setCurrentIndex(max(0, self.assignment_role.findData(role)))
        self.assignment_utility.setEnabled(bool(name))
        self.assignment_role.setEnabled(bool(name) and utility not in ("", pdf_layers.UTILITY_OTHER))
        label = next((L['short'] for L in self._layers if L['name'] == name), "")
        self.assignment_label.setText(label or _tr("Selecciona una capa para asignar su utilidad."))
        for combo in (self.assignment_utility, self.assignment_role):
            combo.blockSignals(False)

    def _assign_selected_layer(self, _index=0):
        name = self._assignment_name
        if not name:
            return
        utility = self.assignment_utility.currentData()
        role = self.assignment_role.currentData()
        previous = self._assignments.get(name)
        if previous:
            self._touched_utilities.add(previous[0])
        self._touched_utilities.add(utility)
        from ui.asistente.recognition_dialog import _suggest_role
        original = next((L for L in self._layers_raw if L['name'] == name), None)
        if original:
            self._touched_utilities.update(u for u in rec.SUPPORTED_UTILITIES
                if _suggest_role(original, u) != rec.ROLE_IGNORAR)
        if utility:
            self._automatic_names.discard(name)
            self._assignments[name] = (utility, rec.ROLE_IGNORAR if utility == pdf_layers.UTILITY_OTHER else role)
        else:
            self._assignments.pop(name, None)
            self._automatic_names.add(name)
        self._assignments_changed = True
        hidden = set(self.hidden_names())
        self._layers = [dict(L, on=L['name'] not in hidden) for L in self._effective_layers()]
        self._drawings = None
        self._fill_list()
        if utility in self._recog_checks:
            self._recog_checks[utility].setChecked(True)
        self._refresh_recog_checks()
        # Restore selection after regrouping the tree.
        items = self._items_by_name.get(name, ())
        if items:
            items[0].parent().setExpanded(True)
            self.tree.setCurrentItem(items[0])
        self.info.set_layers(self._layers, self._letters_off)
        self._clear_focus()
        if items:
            self._focus_lines({"layers": [name]})

    def roles_by_utility(self):
        if not self._assignments_changed:
            return self._base_roles
        from ui.asistente.recognition_dialog import _suggest_role
        out = {}
        for utility in rec.SUPPORTED_UTILITIES:
            if utility not in self._touched_utilities:
                continue
            roles = {rec.ROLE_LINEAS: [], rec.ROLE_BUZONES: []}
            for L in self._layers_raw:
                name = L['name']
                if name in self._assignments:
                    assigned, role = self._assignments[name]
                    if assigned != utility:
                        continue
                elif utility in self._base_roles and name not in self._automatic_names:
                    role = next((r for r in roles if name in self._base_roles[utility].get(r, ())), rec.ROLE_IGNORAR)
                else:
                    role = _suggest_role(L, utility)
                if role in roles:
                    roles[role].append(name)
            for name, (assigned, role) in self._assignments.items():
                if assigned == utility and role in roles and name not in roles[role]:
                    roles[role].append(name)
            out[utility] = roles
        return out
