"""Direct utility/role assignment in the sheet layer step.

Hoja SIN capas con su leyenda legible (mapas SIG de Phoenix, 2026-10-13: `leyenda_mapa`):
al abrir, cada estilo / símbolo que la leyenda describe como línea o estructura de una
utilidad queda ya asignado (el usuario lo revisa y cambia como cualquier asignación) y
cada capa virtual muestra lo que la leyenda dice de ella («Standard Main, Fire Main…»).
"""
from PySide6 import QtWidgets
from hoja import acometidas_mapa, leyenda_mapa, pdf_layers
from reconocimiento import recognition as rec
from traduccion.i18n import t as _tr


class LayerAssignmentsMixin:
    def _init_assignments(self, roles):
        self._base_roles = {u: {k: list(v) if isinstance(v, (list, tuple, set)) else v for k, v in r.items()}
                            for u, r in (roles or {}).items()}
        self._assignments = {}
        self._assignment_name = None
        self._assignments_changed = False
        self._automatic_names = set()
        self._touched_utilities = set(self._base_roles)
        for utility, roles in self._base_roles.items():
            for role in (rec.ROLE_LINEAS, rec.ROLE_BUZONES):
                for name in roles.get(role, ()):
                    self._assignments[name] = (utility, role)
        self._map_legend = None            # (leyenda, asignadas, ambiguas) de un mapa sin capas
        self._legend_desc = {}             # capa virtual → descripciones de la leyenda
        # utilidad → capas que asignó la leyenda de ESTA hoja (None: la hoja no tiene leyenda
        # de mapa); viaja en los roles (`leyenda_mapa.CLAVE_LEYENDA`) para no llevarlas a otra hoja
        self._ley_por_utilidad = None
        self._apply_map_legend()

    def _roles_de_esta_hoja(self) -> bool:
        """¿Los roles previos se eligieron en ESTA hoja (volver de la vista previa)? Los de otra
        llegan sin lo que puso su leyenda (`leyenda_mapa.roles_de_otra_hoja`)."""
        base = self._base_roles
        return (any(leyenda_mapa.CLAVE_LEYENDA in r for r in base.values())
                and not any(r.get(leyenda_mapa.SUMAR_LEYENDA) for r in base.values()))

    def _apply_map_legend(self):
        """Mapa sin capas con leyenda legible: lo que ella dice, asignado. Con roles elegidos en
        esta misma hoja, mandan los suyos tal cual; los traídos de otra hoja (lo puesto a mano)
        van encima de lo que dice la leyenda de ésta."""
        if not any(L.get("source") == "style" for L in self._layers_raw):
            return
        page = self._doc[self._page_index]
        if not leyenda_mapa.aplica(page):
            return
        ley = leyenda_mapa.leer(self._doc, page)
        if not ley.filas:
            return
        self._legend_desc = leyenda_mapa.descripciones(ley)
        if self._roles_de_esta_hoja():
            self._ley_por_utilidad = {u: list(r.get(leyenda_mapa.CLAVE_LEYENDA) or ())
                                      for u, r in self._base_roles.items() if leyenda_mapa.CLAVE_LEYENDA in r}
            return
        en_mapa = {L['name']: int(L.get('path_count') or 0) for L in self._layers_raw}
        asig, amb = leyenda_mapa.asignaciones(ley, en_mapa)
        self._map_legend = (ley, asig, amb)
        self._ley_por_utilidad = {}
        a_mano = {n for r in self._base_roles.values()
                  for role in (rec.ROLE_LINEAS, rec.ROLE_BUZONES) for n in r.get(role) or ()}
        for name, (utility, role) in asig.items():
            self._ley_por_utilidad.setdefault(utility, []).append(name)
            if name in a_mano:
                continue
            self._assignments[name] = (utility, role)
            self._touched_utilities.add(utility)
        if asig:
            self._assignments_changed = True

    def _legend_for_new_sheet(self):
        """◀ ▶ a otra hoja de un mapa con leyenda: su leyenda decide sus estilos (lo elegido a
        mano en la anterior sigue). Sin leyenda de mapa en la nueva, todo queda como estaba."""
        page = self._doc[self._page_index]
        if not (any(L.get("source") == "style" for L in self._layers_raw) and leyenda_mapa.aplica(page)
                and leyenda_mapa.leer(self._doc, page).filas):
            return
        self._init_assignments(leyenda_mapa.roles_de_otra_hoja(self.roles_by_utility()))
        lbl = getattr(self, "lbl_map_legend", None)
        if lbl is not None:
            texto, detalle = self._map_legend_summary()
            lbl.setText(texto)
            lbl.setToolTip(detalle)
            lbl.setVisible(bool(texto))

    def _map_legend_summary(self):
        """(texto corto, detalle para el tooltip) de lo que asignó la leyenda; ("", "") sin ella."""
        if not self._map_legend:
            return "", ""
        ley, asig, amb = self._map_legend
        if not asig:
            return (_tr("Leyenda del plano leída, pero ningún estilo es solo de una red: asígnalos abajo."), "")
        utils = sorted({u for u, _r in asig.values()})
        n_aco = sum(1 for n in asig if acometidas_mapa.es_capa(n))
        n_lin = sum(1 for _u, r in asig.values() if r == rec.ROLE_LINEAS) - n_aco
        n_est = len(asig) - n_lin - n_aco
        u_txt = ", ".join(_tr(rec.utility_label(u)) for u in utils)
        if n_aco:
            texto = _tr("Leyenda del plano: {u} — {l} estilo(s) de líneas, {a} de acometidas y {e} de "
                        "estructuras ya asignados. Revísalos y cambia lo que haga falta.").format(
                u=u_txt, l=n_lin, a=n_aco, e=n_est)
        else:
            texto = _tr("Leyenda del plano: {u} — {l} estilo(s) de líneas y {e} de estructuras ya asignados. "
                        "Revísalos y cambia lo que haga falta.").format(u=u_txt, l=n_lin, e=n_est)
        rol = {rec.ROLE_LINEAS: _tr("Líneas"), rec.ROLE_BUZONES: _tr("Estructuras")}
        det = [f"{pdf_layers.short_name(n)} → {_tr(rec.utility_label(u))} · {rol[r]}: "
               + ", ".join(self._legend_desc.get(n, ())[:4]) for n, (u, r) in asig.items()]
        if amb:
            det.append(_tr("Sin asignar (la leyenda también los usa para lotes, anotaciones u otra red):"))
            det += [f"  {pdf_layers.short_name(n)}: " + ", ".join(ts[:4]) for n, ts in amb.items()]
        return texto, "\n".join(det)

    def _effective_layers(self):
        out = pdf_layers.without_letters(self._layers_raw, self._letters_off)
        out = [dict(L, legend=self._legend_desc.get(L['name'], ())) if L['name'] in self._legend_desc else L
               for L in out]
        return [dict(L, utility=self._assignments[L['name']][0],
                     assigned_role=self._assignments[L['name']][1],
                     letter_utilities=[], letter_codes={}, letter_paths={}, letters="")
                if L['name'] in self._assignments else L for L in out]

    def _build_assignment_controls(self, layout):
        texto, detalle = self._map_legend_summary()
        self.lbl_map_legend = QtWidgets.QLabel(texto)
        self.lbl_map_legend.setWordWrap(True)
        self.lbl_map_legend.setToolTip(detalle)
        self.lbl_map_legend.setVisible(bool(texto))
        layout.addWidget(self.lbl_map_legend)
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
        L = next((L for L in self._layers if L['name'] == name), None)
        label = L['short'] if L else ""
        if L and L.get("legend"):
            label += " — " + ", ".join(L["legend"])
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
            if self._ley_por_utilidad is not None:
                roles[leyenda_mapa.CLAVE_LEYENDA] = list(self._ley_por_utilidad.get(utility, ()))
            out[utility] = roles
        return out
