"""Bancoductos: lista y diseñador.

Métodos de la ventana principal `Main` (app_window.py), movidos TAL CUAL a esta
clase mezcla para que app_window.py no pase de unas 2 000 líneas. `Main` la hereda:
los menús, atajos y pruebas siguen usando `win.<método>` como antes.
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)


class BancoductosMixin:
    # ── Bancoductos: lista/CRUD desde la pestaña "Bancoductos" del inventario ──
    def _refresh_db_list(self):
        """Refresca la pestaña "Bancoductos" con `Tubería · Nombre · Nº conductos`.
        La fila cuya `pipe_idx` coincide con la tubería seleccionada en el canvas
        se resalta en negrita (ancla visual: "el bancoducto de la tubería que
        estoy viendo")."""
        if not hasattr(self, "db_list"):
            return
        self.db_list.blockSignals(True)
        self.db_list.clear()
        dbs = getattr(self, "duct_banks", []) or []
        cur_pipe = getattr(self, "sel_pipe", -1)
        if hasattr(self, "_db_hover"):
            self._db_hover.clear_cache()
        for db in dbs:
            # Tubería(s) asignada(s)
            pipe_lbl = self._db_pipes_label(db)
            nm = db.name or _tr("(sin nombre)")
            nc = len(db.conduits)
            unit_c = _tr("conducto(s)")
            txt = f"{pipe_lbl}  ·  {nm}  ·  {nc} {unit_c}"
            it = QtWidgets.QListWidgetItem(_icon("mdi:grid"), txt)
            it.setToolTip(f"{_tr('Bancoducto')} «{nm}»\n"
                          f"{_tr('Envolvente')}: {db.width_in:g}\" × {db.height_in:g}\"\n"
                          f"{_tr('Conductos')}: {nc}\n"
                          f"{_tr('Tubería')}: {pipe_lbl}\n\n"
                          f"{_tr('Doble-click para editar.')}")
            if cur_pipe >= 0 and cur_pipe in db.assigned():
                # Resaltar la fila del bancoducto asignado a la tubería
                # actualmente seleccionada. No cambiamos el color del texto (en
                # dark, un accent azul sobre fondo negro queda ilegible), sino
                # que aplicamos negrita + un fondo tinte del accent — se lee en
                # ambos temas y no depende de contraste marginal.
                f = it.font(); f.setBold(True); it.setFont(f)
                t = _theme.tokens()
                # Fondo tenue del accent (~15% alpha) — legible sobre bg claro y
                # oscuro sin cambiar el color del texto.
                bg = QtGui.QColor(t.accent); bg.setAlpha(45)
                it.setBackground(bg)
            self.db_list.addItem(it)
        # Estado vacío: mensaje placeholder cuando no hay filas.
        if not dbs:
            hint = QtWidgets.QListWidgetItem(
                _tr("Aún no hay bancoductos.\n"
                    "Crea uno con «+ Nuevo» arriba, o click derecho en una tubería."))
            hint.setFlags(QtCore.Qt.NoItemFlags)   # no seleccionable
            hint.setForeground(QtGui.QColor(_theme.tokens().text_muted))
            self.db_list.addItem(hint)
        # Restaurar selección si sigue siendo válida.
        if 0 <= self.sel_db < len(dbs):
            self.db_list.setCurrentRow(self.sel_db)
        self.db_list.blockSignals(False)

    def _sel_db(self, row):
        if 0 <= row < len(getattr(self, "duct_banks", [])):
            self.sel_db = row
        else:
            self.sel_db = -1

    def _db_new(self):
        """Crear un bancoducto nuevo desde cero (sin tubería preasignada)."""
        self._open_duct_bank_designer(initial=None)

    def _db_new_for_pipe(self, pipe_idx):
        """Crear un bancoducto ya asignado a esta tubería."""
        from nucleo.duct_bank import DuctBank
        seed = DuctBank(name="", pipe_idx=pipe_idx)
        self._open_duct_bank_designer(initial=seed)

    def _db_edit(self):
        """Editar el bancoducto seleccionado en la lista."""
        dbs = getattr(self, "duct_banks", []) or []
        if not (0 <= self.sel_db < len(dbs)):
            self._info(_tr("Selecciona un bancoducto primero."))
            return
        self._open_duct_bank_designer(initial=dbs[self.sel_db])

    def _db_edit_for_pipe(self, pipe_idx):
        """Editar el bancoducto asignado a esta tubería (desde menú contextual)."""
        db = self._duct_bank_for_pipe(pipe_idx)
        if db is None:
            return
        self._open_duct_bank_designer(initial=db)

    def _db_duplicate(self):
        """Duplica el bancoducto seleccionado (sin tubería asignada — el usuario
        decide a cuál asignarlo al editar)."""
        dbs = getattr(self, "duct_banks", []) or []
        if not (0 <= self.sel_db < len(dbs)):
            self._info(_tr("Selecciona un bancoducto para duplicar."))
            return
        src = dbs[self.sel_db]
        dup = src.copy()
        dup.name = f"{src.name or 'sin nombre'} (copia)"
        dup.assign([])   # no heredamos asignación para evitar superposición
        self._push()
        self.duct_banks.append(dup)
        self.sel_db = len(self.duct_banks) - 1
        self._dirty = True
        if hasattr(self, "lbl_ductbank_count"):
            _bind(self.lbl_ductbank_count, "setText", "Duct banks guardados: {n}", fmt={"n": len(self.duct_banks)})
        self._refresh_lists()
        self._info(_tr("Bancoducto duplicado como «{nombre}».").format(nombre=dup.name))

    # Sentinel para distinguir "sin argumento" (comportamiento heredado del
    # botón viejo del toolbar) de "explícitamente None" (nuevo desde cero).
    # Sin esto, `_open_duct_bank_designer(initial=None)` caía al fallback que
    # cargaba el último bancoducto — el usuario pedía Nuevo y se le abría uno ya
    # creado.
    _DB_DEFAULT = object()

    def _open_duct_bank_designer(self, initial=_DB_DEFAULT):
        # Delegador delgado: la UI del diseñador vive en duct_bank_dialog.py.
        # Al aceptar, guarda el diseño en self.duct_banks (colección del proyecto)
        # sobreescribiendo por identidad de objeto O por pipe_idx (para evitar
        # sólidos superpuestos cuando se rediseña el bancoducto de una tubería).
        #
        # `initial` explícito manda:
        #   - Un DuctBank existente → editarlo en-place
        #   - Un DuctBank nuevo con pipe_idx puesto → crear preasignado
        #   - None → crear desde cero (BOTÓN "Nuevo")
        # Sin `initial` (sentinel _DB_DEFAULT), cae al comportamiento heredado:
        # bancoducto de la pipe seleccionada, o el último — para no romper el
        # botón del toolbar antiguo.
        from ui.dialogos.duct_bank_dialog import open_designer
        if initial is self._DB_DEFAULT:
            current = None
            if hasattr(self, "sel_pipe") and self.sel_pipe >= 0:
                current = self._duct_bank_for_pipe(self.sel_pipe)
            if current is None and getattr(self, "duct_banks", None):
                current = self.duct_banks[-1]
        else:
            current = initial   # None aquí SÍ significa "crear desde cero"
        result = open_designer(self, initial=current)
        if result is None:
            return
        if not getattr(self, "duct_banks", None):
            self.duct_banks = []
        self._push()   # guardar/rediseñar un bancoducto se puede deshacer
        # Reemplazo:
        #   - Si `current` es un DuctBank ya guardado, sustituimos ESE objeto
        #     (identidad) — así "Editar" nunca crea duplicados aunque el usuario
        #     cambie el nombre.
        #   - Sino, cae al match por nombre (nombres únicos como convención).
        replaced = False
        if current is not None:
            for i, d in enumerate(self.duct_banks):
                if d is current:
                    self.duct_banks[i] = result
                    replaced = True
                    break
        if not replaced:
            existing = next((i for i, d in enumerate(self.duct_banks)
                             if d.name and d.name == result.name), None)
            if existing is not None:
                self.duct_banks[existing] = result
            else:
                self.duct_banks.append(result)
        # Quitar estas pipes de los otros duct banks (evita superposición).
        if result.assigned():
            self._db_take_pipes(result, result.assigned())
        self._dirty = True   # marca proyecto para pedir guardar
        asign = [i for i in result.assigned() if 0 <= i < len(self.pipes)]
        asignada = len(asign) == 1
        datos = {"n": len(self.duct_banks), "nombre": result.name or _tr("sin nombre"),
                 "k": len(asign)}
        if asignada:
            datos.update(num=asign[0] + 1, capa=self._etq(self.pipes[asign[0]]))
        if hasattr(self, "lbl_ductbank_count"):
            _bind(self.lbl_ductbank_count, "setText",
                  "Duct banks: {n} → asignado a #{num} {capa}" if asignada
                  else ("Duct banks: {n} → asignado a {k} utilidades" if asign else "Duct banks: {n}"),
                  fmt=datos)
        # Deja seleccionado el bancoducto que se acaba de editar/crear en la lista.
        try:
            self.sel_db = self.duct_banks.index(result)
        except ValueError:
            self.sel_db = -1
        self._refresh_lists()
        if len(asign) > 1:
            self._info(_tr("Duct bank «{nombre}» guardado → asignado a {k} utilidades.").format(**datos))
        else:
            self._info(_tr("Duct bank «{nombre}» guardado → asignado a #{num} {capa}." if asignada
                           else "Duct bank «{nombre}» guardado.").format(**datos))
