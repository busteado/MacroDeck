import json
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

import customtkinter as ctk

# ----------------------------
# Data model
# ----------------------------
AXES = ["throttle", "steer", "pitch", "yaw", "roll"]
BUTTONS = ["jump", "boost", "handbrake", "airRollL", "airRollR"]


def _clamp_float(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


@dataclass
class MacroFrame:
    dt_ms: int
    inputs: Dict[str, Any]


@dataclass
class Macro:
    name: str
    type: str = "Single-Stage"   # Single-Stage | Multi-Stage
    description: str = ""
    trigger: Optional[str] = None
    enabled: bool = True
    frames: List[MacroFrame] = None


# ----------------------------
# Persistence
# ----------------------------
def save_macros(path: str, macros: List[Macro]) -> None:
    payload = []
    for m in macros:
        payload.append({
            "name": m.name,
            "type": m.type,
            "description": m.description,
            "trigger": m.trigger,
            "enabled": m.enabled,
            "frames": [asdict(f) for f in (m.frames or [])],
        })
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def load_macros(path: str) -> List[Macro]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        out: List[Macro] = []
        for item in payload:
            frames = []
            for fr in item.get("frames", []):
                frames.append(MacroFrame(
                    dt_ms=int(fr.get("dt_ms", 80)),
                    inputs=dict(fr.get("inputs", {})),
                ))
            out.append(Macro(
                name=item.get("name", "Macro"),
                type=item.get("type", "Single-Stage"),
                description=item.get("description", ""),
                trigger=item.get("trigger"),
                enabled=bool(item.get("enabled", True)),
                frames=frames,
            ))
        return out
    except FileNotFoundError:
        return []
    except Exception:
        return []


# ----------------------------
# Helpers
# ----------------------------
def frame_to_F_line(fr: MacroFrame) -> str:
    parts = [f"F({int(fr.dt_ms)}"]
    # floats first
    for k in AXES:
        if k in fr.inputs:
            parts.append(f"{k}={float(fr.inputs[k]):.3f}")
    # bools
    for k in BUTTONS:
        if k in fr.inputs:
            parts.append(f"{k}={bool(fr.inputs[k])}")
    # any extras
    for k, v in fr.inputs.items():
        if k in AXES or k in BUTTONS:
            continue
        parts.append(f"{k}={repr(v)}")
    return ", ".join(parts) + ")"


def macro_to_snippet(m: Macro) -> str:
    lines = []
    lines.append(f"# {m.name} ({m.type})")
    if m.description:
        lines.append(f"# {m.description}")
    lines.append("frames = [")
    for fr in (m.frames or []):
        lines.append(f"    {frame_to_F_line(fr)},")
    lines.append("]")
    return "\n".join(lines)


def new_empty_frame() -> MacroFrame:
    return MacroFrame(dt_ms=80, inputs={
        "throttle": 0.0,
        "steer": 0.0,
        "pitch": 0.0,
        "yaw": 0.0,
        "roll": 0.0,
        "jump": False,
        "boost": False,
        "handbrake": False,
        "airRollL": False,
        "airRollR": False,
    })


# ----------------------------
# UI
# ----------------------------
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class FrameEditor(ctk.CTkToplevel):
    """Popup editor for one MacroFrame."""
    def __init__(self, master, frame: MacroFrame, on_apply):
        super().__init__(master)
        self.title("Editar frame")
        self.geometry("520x520")
        self.resizable(False, False)

        self.frame_obj = frame
        self.on_apply = on_apply

        container = ctk.CTkFrame(self, corner_radius=16)
        container.pack(fill="both", expand=True, padx=14, pady=14)
        container.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(container, text="Duración (ms)", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=12, pady=(12, 8), sticky="w"
        )
        self.dt_entry = ctk.CTkEntry(container)
        self.dt_entry.grid(row=0, column=1, padx=12, pady=(12, 8), sticky="ew")
        self.dt_entry.insert(0, str(frame.dt_ms))

        # Axes
        ctk.CTkLabel(container, text="Ejes (-1..1)", font=ctk.CTkFont(weight="bold")).grid(
            row=1, column=0, padx=12, pady=(12, 6), sticky="w"
        )

        self.axis_entries: Dict[str, ctk.CTkEntry] = {}
        r = 2
        for k in AXES:
            ctk.CTkLabel(container, text=k).grid(row=r, column=0, padx=12, pady=6, sticky="w")
            e = ctk.CTkEntry(container)
            e.grid(row=r, column=1, padx=12, pady=6, sticky="ew")
            e.insert(0, str(float(frame.inputs.get(k, 0.0))))
            self.axis_entries[k] = e
            r += 1

        # Buttons
        ctk.CTkLabel(container, text="Botones", font=ctk.CTkFont(weight="bold")).grid(
            row=r, column=0, padx=12, pady=(14, 6), sticky="w"
        )
        r += 1

        self.button_vars: Dict[str, ctk.BooleanVar] = {}
        btn_grid = ctk.CTkFrame(container, fg_color="transparent")
        btn_grid.grid(row=r, column=0, columnspan=2, padx=12, pady=(0, 6), sticky="ew")
        btn_grid.grid_columnconfigure((0, 1), weight=1)

        for i, k in enumerate(BUTTONS):
            var = ctk.BooleanVar(value=bool(frame.inputs.get(k, False)))
            self.button_vars[k] = var
            sw = ctk.CTkSwitch(btn_grid, text=k, variable=var)
            sw.grid(row=i // 2, column=i % 2, padx=8, pady=6, sticky="w")

        r += 1

        # Extras (JSON dict)
        ctk.CTkLabel(container, text="Extras (JSON opcional)", font=ctk.CTkFont(weight="bold")).grid(
            row=r, column=0, padx=12, pady=(14, 6), sticky="w"
        )
        r += 1

        self.extras = ctk.CTkTextbox(container, height=110)
        self.extras.grid(row=r, column=0, columnspan=2, padx=12, pady=(0, 12), sticky="nsew")

        extras_dict = {
            k: v for k, v in frame.inputs.items()
            if k not in AXES and k not in BUTTONS
        }
        self.extras.insert("1.0", json.dumps(extras_dict, indent=2, ensure_ascii=False))

        # Actions
        actions = ctk.CTkFrame(container, corner_radius=14)
        actions.grid(row=r+1, column=0, columnspan=2, padx=12, pady=(6, 12), sticky="ew")
        actions.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(actions, text="Cancelar", fg_color="#4A4A4A", hover_color="#3A3A3A",
                      command=self.destroy).grid(row=0, column=0, padx=10, pady=12, sticky="ew")
        ctk.CTkButton(actions, text="Aplicar", command=self._apply).grid(
            row=0, column=1, padx=10, pady=12, sticky="ew"
        )

    def _apply(self):
        # dt
        try:
            dt = int(float(self.dt_entry.get().strip()))
        except ValueError:
            dt = 80
        dt = max(1, dt)

        new_inputs: Dict[str, Any] = {}

        # axes
        for k, e in self.axis_entries.items():
            try:
                v = float(e.get().strip())
            except ValueError:
                v = 0.0
            new_inputs[k] = _clamp_float(v)

        # buttons
        for k, var in self.button_vars.items():
            new_inputs[k] = bool(var.get())

        # extras
        try:
            extras_dict = json.loads(self.extras.get("1.0", "end").strip() or "{}")
            if isinstance(extras_dict, dict):
                for k, v in extras_dict.items():
                    new_inputs[k] = v
        except Exception:
            pass

        self.frame_obj.dt_ms = dt
        self.frame_obj.inputs = new_inputs
        self.on_apply()
        self.destroy()


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Macro Creator — Frames (F(dt, ...))")
        self.geometry("1120x660")
        self.minsize(980, 600)

        self.data_path = "macros.json"
        self.macros: List[Macro] = load_macros(self.data_path)
        if not self.macros:
            self.macros = [Macro(name="Nueva macro", frames=[new_empty_frame()])]

        self.selected_index: Optional[int] = None

        self._build_ui()
        self._refresh_list()
        self._load_macro(0)

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Left panel
        left = ctk.CTkFrame(self, corner_radius=16)
        left.grid(row=0, column=0, padx=14, pady=14, sticky="nsw")
        left.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(left, text="Macros", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, padx=14, pady=(14, 8), sticky="w"
        )

        btns = ctk.CTkFrame(left, fg_color="transparent")
        btns.grid(row=1, column=0, padx=14, pady=(0, 10), sticky="ew")
        btns.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(btns, text="Nueva", command=self._new_macro).grid(
            row=0, column=0, padx=(0, 8), sticky="ew"
        )
        ctk.CTkButton(btns, text="Borrar", fg_color="#B23B3B", hover_color="#8E2F2F",
                      command=self._delete_macro).grid(
            row=0, column=1, padx=(8, 0), sticky="ew"
        )

        self.listbox = ctk.CTkScrollableFrame(left, width=320, corner_radius=16)
        self.listbox.grid(row=2, column=0, padx=14, pady=(0, 14), sticky="nsew")

        # Right panel
        right = ctk.CTkFrame(self, corner_radius=16)
        right.grid(row=0, column=1, padx=(0, 14), pady=14, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(3, weight=1)

        self.lbl = ctk.CTkLabel(right, text="Editor", font=ctk.CTkFont(size=18, weight="bold"))
        self.lbl.grid(row=0, column=0, padx=18, pady=(16, 6), sticky="w")

        form = ctk.CTkFrame(right, corner_radius=14)
        form.grid(row=1, column=0, padx=18, pady=(0, 10), sticky="ew")
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text="Nombre").grid(row=0, column=0, padx=12, pady=10, sticky="w")
        self.entry_name = ctk.CTkEntry(form)
        self.entry_name.grid(row=0, column=1, padx=12, pady=10, sticky="ew")

        ctk.CTkLabel(form, text="Tipo").grid(row=1, column=0, padx=12, pady=10, sticky="w")
        self.entry_type = ctk.CTkEntry(form)
        self.entry_type.grid(row=1, column=1, padx=12, pady=10, sticky="ew")

        ctk.CTkLabel(form, text="Descripción").grid(row=2, column=0, padx=12, pady=10, sticky="w")
        self.entry_desc = ctk.CTkEntry(form)
        self.entry_desc.grid(row=2, column=1, padx=12, pady=10, sticky="ew")

        self.sw_enabled = ctk.CTkSwitch(form, text="Enabled")
        self.sw_enabled.grid(row=3, column=1, padx=12, pady=(4, 10), sticky="e")

        # Frames toolbar
        frame_bar = ctk.CTkFrame(right, fg_color="transparent")
        frame_bar.grid(row=2, column=0, padx=18, pady=(0, 10), sticky="ew")
        frame_bar.grid_columnconfigure((0, 1, 2, 3), weight=1)

        ctk.CTkButton(frame_bar, text="Añadir frame", command=self._add_frame).grid(
            row=0, column=0, padx=(0, 8), sticky="ew"
        )
        ctk.CTkButton(frame_bar, text="Duplicar frame", command=self._duplicate_frame).grid(
            row=0, column=1, padx=8, sticky="ew"
        )
        ctk.CTkButton(frame_bar, text="Move Up", command=lambda: self._move_frame(-1)).grid(
            row=0, column=2, padx=8, sticky="ew"
        )
        ctk.CTkButton(frame_bar, text="Move Down", command=lambda: self._move_frame(1)).grid(
            row=0, column=3, padx=(8, 0), sticky="ew"
        )

        # Frames list
        self.frames_view = ctk.CTkScrollableFrame(right, corner_radius=16)
        self.frames_view.grid(row=3, column=0, padx=18, pady=(0, 10), sticky="nsew")

        # Snippet + actions
        bottom = ctk.CTkFrame(right, corner_radius=14)
        bottom.grid(row=4, column=0, padx=18, pady=(0, 14), sticky="ew")
        bottom.grid_columnconfigure(0, weight=1)

        self.snip = ctk.CTkTextbox(bottom, height=140)
        self.snip.grid(row=0, column=0, padx=12, pady=(12, 10), sticky="ew")

        actions = ctk.CTkFrame(bottom, fg_color="transparent")
        actions.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="ew")
        actions.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkButton(actions, text="Guardar JSON", command=self._save).grid(
            row=0, column=0, padx=(0, 8), sticky="ew"
        )
        ctk.CTkButton(actions, text="Copiar snippet", command=self._copy_snippet).grid(
            row=0, column=1, padx=8, sticky="ew"
        )
        ctk.CTkButton(actions, text="Exportar .py", command=self._export_py).grid(
            row=0, column=2, padx=(8, 0), sticky="ew"
        )

        self.status = ctk.CTkLabel(right, text="Listo.", anchor="w")
        self.status.grid(row=5, column=0, padx=18, pady=(0, 10), sticky="ew")

        # selection state
        self.selected_frame_index: Optional[int] = None

    # -------- Macros list (left)
    def _refresh_list(self):
        for w in self.listbox.winfo_children():
            w.destroy()

        for idx, m in enumerate(self.macros):
            enabled = "✓" if m.enabled else "✗"
            nframes = len(m.frames or [])
            btn = ctk.CTkButton(
                self.listbox,
                text=f"{enabled} {m.name}\nFrames: {nframes}",
                anchor="w",
                height=56,
                command=lambda i=idx: self._load_macro(i),
            )
            btn.pack(fill="x", padx=10, pady=8)

    def _new_macro(self):
        self.macros.append(Macro(name="Nueva macro", frames=[new_empty_frame()]))
        self._refresh_list()
        self._load_macro(len(self.macros) - 1)
        self._set_status("Macro creada.")

    def _delete_macro(self):
        if self.selected_index is None:
            return
        self.macros.pop(self.selected_index)
        self.selected_index = None
        self._refresh_list()
        if self.macros:
            self._load_macro(0)
        else:
            self.macros = [Macro(name="Nueva macro", frames=[new_empty_frame()])]
            self._load_macro(0)
        self._save()
        self._set_status("Macro borrada.")

    # -------- Editor (right)
    def _load_macro(self, idx: int):
        self.selected_index = idx
        self.selected_frame_index = None

        m = self.macros[idx]
        self.lbl.configure(text=f"Editor — {m.name}")

        self.entry_name.delete(0, "end")
        self.entry_name.insert(0, m.name)

        self.entry_type.delete(0, "end")
        self.entry_type.insert(0, m.type)

        self.entry_desc.delete(0, "end")
        self.entry_desc.insert(0, m.description)

        if m.enabled:
            self.sw_enabled.select()
        else:
            self.sw_enabled.deselect()

        self._render_frames()
        self._render_snippet()

    def _render_frames(self):
        for w in self.frames_view.winfo_children():
            w.destroy()

        m = self._cur()
        if not m:
            return

        if not m.frames:
            ctk.CTkLabel(self.frames_view, text="No hay frames. Añade uno.").pack(padx=12, pady=12)
            return

        for i, fr in enumerate(m.frames):
            row = ctk.CTkFrame(self.frames_view, corner_radius=14)
            row.pack(fill="x", padx=10, pady=8)
            row.grid_columnconfigure(1, weight=1)

            badge = ctk.CTkLabel(row, text=f"{i+1}", width=30, font=ctk.CTkFont(weight="bold"))
            badge.grid(row=0, column=0, padx=10, pady=10)

            summary = ", ".join([f"{k}={fr.inputs.get(k)}" for k in list(fr.inputs.keys())[:6]])
            txt = f"dt={fr.dt_ms}ms  |  {summary}" + (" ..." if len(fr.inputs) > 6 else "")
            lab = ctk.CTkLabel(row, text=txt, anchor="w")
            lab.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

            btn_edit = ctk.CTkButton(row, text="Editar", width=90,
                                     command=lambda j=i: self._edit_frame(j))
            btn_edit.grid(row=0, column=2, padx=8, pady=10)

            btn_sel = ctk.CTkButton(row, text="Sel", width=60, fg_color="#4A4A4A", hover_color="#3A3A3A",
                                    command=lambda j=i: self._select_frame(j))
            btn_sel.grid(row=0, column=3, padx=8, pady=10)

            btn_del = ctk.CTkButton(row, text="✕", width=46, fg_color="#B23B3B", hover_color="#8E2F2F",
                                    command=lambda j=i: self._delete_frame(j))
            btn_del.grid(row=0, column=4, padx=8, pady=10)

    def _select_frame(self, idx: int):
        self.selected_frame_index = idx
        self._set_status(f"Frame seleccionado: {idx+1}")

    def _edit_frame(self, idx: int):
        m = self._cur()
        if not m:
            return

        def on_apply():
            self._render_frames()
            self._render_snippet()
            self._set_status("Frame actualizado.")

        FrameEditor(self, m.frames[idx], on_apply)

    def _delete_frame(self, idx: int):
        m = self._cur()
        if not m:
            return
        if idx < 0 or idx >= len(m.frames):
            return
        m.frames.pop(idx)
        if self.selected_frame_index == idx:
            self.selected_frame_index = None
        self._render_frames()
        self._render_snippet()
        self._set_status("Frame eliminado.")

    def _add_frame(self):
        m = self._cur()
        if not m:
            return
        m.frames.append(new_empty_frame())
        self._render_frames()
        self._render_snippet()
        self._set_status("Frame añadido.")

    def _duplicate_frame(self):
        m = self._cur()
        if not m:
            return
        idx = self.selected_frame_index
        if idx is None:
            self._set_status("Selecciona un frame con 'Sel' para duplicar.")
            return
        fr = m.frames[idx]
        m.frames.insert(idx + 1, MacroFrame(dt_ms=fr.dt_ms, inputs=dict(fr.inputs)))
        self._render_frames()
        self._render_snippet()
        self._set_status("Frame duplicado.")

    def _move_frame(self, direction: int):
        m = self._cur()
        if not m:
            return
        idx = self.selected_frame_index
        if idx is None:
            self._set_status("Selecciona un frame con 'Sel' para mover.")
            return
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(m.frames):
            return
        m.frames[idx], m.frames[new_idx] = m.frames[new_idx], m.frames[idx]
        self.selected_frame_index = new_idx
        self._render_frames()
        self._render_snippet()
        self._set_status(f"Movido a posición {new_idx+1}.")

    def _render_snippet(self):
        m = self._cur()
        if not m:
            return

        # sync header fields before render
        m.name = self.entry_name.get().strip() or m.name
        m.type = self.entry_type.get().strip() or m.type
        m.description = self.entry_desc.get().strip() or m.description
        m.enabled = bool(self.sw_enabled.get())

        self.snip.delete("1.0", "end")
        self.snip.insert("1.0", macro_to_snippet(m))

    # -------- Save / export
    def _save(self):
        m = self._cur()
        if m:
            m.name = self.entry_name.get().strip() or m.name
            m.type = self.entry_type.get().strip() or m.type
            m.description = self.entry_desc.get().strip() or m.description
            m.enabled = bool(self.sw_enabled.get())
        save_macros(self.data_path, self.macros)
        self._refresh_list()
        self._render_snippet()
        self._set_status("Guardado en macros.json")

    def _copy_snippet(self):
        txt = self.snip.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(txt)
        self._set_status("Snippet copiado al portapapeles.")

    def _export_py(self):
        m = self._cur()
        if not m:
            return
        code = [
            "def F(dt, **inputs):",
            "    return {'dt_ms': dt, 'inputs': inputs}",
            "",
            macro_to_snippet(m),
            "",
        ]
        fname = f"{m.name.strip().replace(' ', '_') or 'macro'}.py"
        try:
            with open(fname, "w", encoding="utf-8") as f:
                f.write("\n".join(code))
            self._set_status(f"Exportado: {fname}")
        except Exception as e:
            self._set_status(f"Error exportando: {e}")

    # -------- misc
    def _cur(self) -> Optional[Macro]:
        if self.selected_index is None:
            return None
        if self.selected_index < 0 or self.selected_index >= len(self.macros):
            return None
        return self.macros[self.selected_index]

    def _set_status(self, msg: str):
        self.status.configure(text=msg)


if __name__ == "__main__":
    app = App()
    app.mainloop()
