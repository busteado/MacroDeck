import json
import time
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import customtkinter as ctk

# ============================
# Campos soportados
# ============================
AXES = ["throttle", "steer", "pitch", "yaw", "roll"]
BUTTONS = ["jump", "boost", "handbrake", "airRollL", "airRollR"]

ALL_KEYS = AXES + BUTTONS  # lo básico; extras permitidos en JSON


def clamp01(x: float) -> float:
    return max(-1.0, min(1.0, x))


# ============================
# Modelo interno
# ============================
@dataclass
class MacroFrame:
    dt_ms: int
    inputs: Dict[str, Any]


@dataclass
class Macro:
    name: str
    type: str
    description: str
    enabled: bool = True
    frames: List[MacroFrame] = None
    # meta
    source_has_stages: bool = False
    stages: Optional[List[Tuple[str, List[MacroFrame]]]] = None  # (stage_name, frames)


# ============================
# Import/Export formato JSON del usuario
# ============================
def parse_user_json(payload: Dict[str, Any]) -> Tuple[str, List[Macro]]:
    """
    Formato esperado:
    {
      "version": 1,
      "notes": "...",
      "macros": [
        { "name":..., "type":..., "description":..., "sequence":[{"dt":..,"in":{...}}, ...] }
        OR
        { ..., "stages":[{"name":"Stage 1", "sequence":[...]} , ...] }
      ]
    }
    """
    notes = str(payload.get("notes", "") or "")
    macros_raw = payload.get("macros", [])
    if not isinstance(macros_raw, list):
        raise ValueError("JSON inválido: 'macros' debe ser una lista")

    macros: List[Macro] = []

    for m in macros_raw:
        if not isinstance(m, dict):
            continue
        name = str(m.get("name", "Macro") or "Macro")
        mtype = str(m.get("type", "Single-Stage") or "Single-Stage")
        desc = str(m.get("description", "") or "")

        if "sequence" in m:
            frames = _parse_sequence(m.get("sequence"))
            macros.append(Macro(name=name, type=mtype, description=desc, frames=frames))
            continue

        if "stages" in m:
            stages_raw = m.get("stages", [])
            if not isinstance(stages_raw, list):
                raise ValueError(f"Macro '{name}': 'stages' debe ser una lista")
            stages: List[Tuple[str, List[MacroFrame]]] = []
            flat: List[MacroFrame] = []
            for st in stages_raw:
                if not isinstance(st, dict):
                    continue
                st_name = str(st.get("name", "Stage") or "Stage")
                st_frames = _parse_sequence(st.get("sequence"))
                stages.append((st_name, st_frames))
                # aplanamos para vista simple (añadimos marca stage)
                flat.append(MacroFrame(dt_ms=1, inputs={"__note__": f"[{st_name}]"}))
                flat.extend(st_frames)
            macros.append(Macro(
                name=name, type=mtype, description=desc,
                frames=flat, source_has_stages=True, stages=stages
            ))
            continue

        # si no hay sequence ni stages
        macros.append(Macro(name=name, type=mtype, description=desc, frames=[]))

    return notes, macros


def _parse_sequence(seq: Any) -> List[MacroFrame]:
    if not isinstance(seq, list):
        return []
    out: List[MacroFrame] = []
    for item in seq:
        if not isinstance(item, dict):
            continue
        dt = int(item.get("dt", item.get("dt_ms", 80)) or 80)
        dt = max(1, dt)
        inp = item.get("in", item.get("inputs", {}))
        if not isinstance(inp, dict):
            inp = {}
        clean = _normalize_inputs(inp)
        out.append(MacroFrame(dt_ms=dt, inputs=clean))
    return out


def _normalize_inputs(inp: Dict[str, Any]) -> Dict[str, Any]:
    """
    - Clampa ejes [-1..1]
    - Convierte botones a bool
    - Mantiene extras tal cual
    """
    out: Dict[str, Any] = {}
    for k, v in inp.items():
        if k in AXES:
            try:
                out[k] = clamp01(float(v))
            except Exception:
                out[k] = 0.0
        elif k in BUTTONS:
            out[k] = bool(v)
        else:
            out[k] = v
    return out


def export_user_json(notes: str, macros: List[Macro]) -> Dict[str, Any]:
    """
    Exporta en el formato del usuario:
    - Si macro.source_has_stages y macro.stages existe -> usa "stages"
    - Si no -> usa "sequence"
    """
    payload = {"version": 1, "notes": notes or "", "macros": []}
    for m in macros:
        base = {
            "name": m.name,
            "type": m.type,
            "description": m.description,
        }
        if m.source_has_stages and m.stages:
            stages_out = []
            for st_name, st_frames in m.stages:
                stages_out.append({
                    "name": st_name,
                    "sequence": [{"dt": fr.dt_ms, "in": fr.inputs} for fr in st_frames]
                })
            base["stages"] = stages_out
        else:
            base["sequence"] = [{"dt": fr.dt_ms, "in": fr.inputs} for fr in (m.frames or []) if "__note__" not in fr.inputs]
        payload["macros"].append(base)
    return payload


# ============================
# UI
# ============================
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Macro Creator — JSON + Preview (mando)")
        self.geometry("1180x720")
        self.minsize(1020, 640)

        self.notes: str = "Macros para un juego tipo Rocket League. Timings orientativos."
        self.macros: List[Macro] = []

        # preview engine
        self._preview_stop = threading.Event()
        self._preview_thread: Optional[threading.Thread] = None

        self.selected_index: Optional[int] = None

        self._build_ui()

        # Carga inicial con ejemplo vacío
        self._set_status("Pega tu JSON a la derecha y pulsa 'Importar JSON'.")

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # LEFT: list + editor simple
        left = ctk.CTkFrame(self, corner_radius=16)
        left.grid(row=0, column=0, padx=14, pady=14, sticky="nsw")
        left.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(left, text="Macros", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, padx=14, pady=(14, 8), sticky="w"
        )

        self.btn_run = ctk.CTkButton(left, text="▶ Preview (Ejecutar)", command=self._preview_run_current)
        self.btn_run.grid(row=1, column=0, padx=14, pady=(0, 8), sticky="ew")

        self.btn_stop = ctk.CTkButton(left, text="⏹ Stop", fg_color="#B23B3B", hover_color="#8E2F2F",
                                      command=self._preview_stop_now)
        self.btn_stop.grid(row=2, column=0, padx=14, pady=(0, 10), sticky="ew")

        self.listbox = ctk.CTkScrollableFrame(left, width=340, corner_radius=16)
        self.listbox.grid(row=3, column=0, padx=14, pady=(0, 14), sticky="nsew")

        # RIGHT: JSON + preview panel
        right = ctk.CTkFrame(self, corner_radius=16)
        right.grid(row=0, column=1, padx=(0, 14), pady=14, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(right, text="JSON (pega aquí)", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, padx=18, pady=(16, 6), sticky="w"
        )

        self.json_box = ctk.CTkTextbox(right, height=280)
        self.json_box.grid(row=1, column=0, padx=18, pady=(0, 10), sticky="nsew")

        json_actions = ctk.CTkFrame(right, corner_radius=14)
        json_actions.grid(row=2, column=0, padx=18, pady=(0, 10), sticky="ew")
        json_actions.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkButton(json_actions, text="Importar JSON", command=self._import_json).grid(
            row=0, column=0, padx=(0, 8), pady=12, sticky="ew"
        )
        ctk.CTkButton(json_actions, text="Exportar JSON", command=self._export_json_to_box).grid(
            row=0, column=1, padx=8, pady=12, sticky="ew"
        )
        ctk.CTkButton(json_actions, text="Guardar archivo macros.json", command=self._save_to_file).grid(
            row=0, column=2, padx=(8, 0), pady=12, sticky="ew"
        )

        # Preview “mando”
        preview = ctk.CTkFrame(right, corner_radius=14)
        preview.grid(row=3, column=0, padx=18, pady=(0, 10), sticky="nsew")
        preview.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(preview, text="Preview mando (inputs actuales)", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, columnspan=2, padx=12, pady=(12, 8), sticky="w"
        )

        self.lbl_macro = ctk.CTkLabel(preview, text="Macro: —  |  Frame: —  |  dt: —", anchor="w")
        self.lbl_macro.grid(row=1, column=0, columnspan=2, padx=12, pady=(0, 8), sticky="ew")

        # Ejes
        self.axis_labels: Dict[str, ctk.CTkLabel] = {}
        r = 2
        for k in AXES:
            ctk.CTkLabel(preview, text=f"{k}:").grid(row=r, column=0, padx=12, pady=6, sticky="w")
            lab = ctk.CTkLabel(preview, text="0.00", anchor="w")
            lab.grid(row=r, column=1, padx=12, pady=6, sticky="ew")
            self.axis_labels[k] = lab
            r += 1

        # Botones
        ctk.CTkLabel(preview, text="Botones:", font=ctk.CTkFont(weight="bold")).grid(
            row=r, column=0, padx=12, pady=(14, 6), sticky="w"
        )
        r += 1

        btn_frame = ctk.CTkFrame(preview, fg_color="transparent")
        btn_frame.grid(row=r, column=0, columnspan=2, padx=12, pady=(0, 12), sticky="ew")
        btn_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.btn_badges: Dict[str, ctk.CTkLabel] = {}
        for i, b in enumerate(BUTTONS):
            badge = ctk.CTkLabel(btn_frame, text=f"{b}: OFF", corner_radius=8)
            badge.grid(row=i // 3, column=i % 3, padx=8, pady=6, sticky="ew")
            self.btn_badges[b] = badge

        # Status
        self.status = ctk.CTkLabel(right, text="Listo.", anchor="w")
        self.status.grid(row=4, column=0, padx=18, pady=(0, 10), sticky="ew")

    # ============================
    # JSON import/export
    # ============================
    def _import_json(self):
        txt = self.json_box.get("1.0", "end").strip()
        if not txt:
            self._set_status("Pega un JSON primero.")
            return
        try:
            payload = json.loads(txt)
            if not isinstance(payload, dict):
                raise ValueError("El JSON debe ser un objeto")
            notes, macros = parse_user_json(payload)
        except Exception as e:
            self._set_status(f"Error importando JSON: {e}")
            return

        self.notes = notes
        self.macros = macros
        self._refresh_list()
        self.selected_index = 0 if self.macros else None
        self._set_status(f"Importado: {len(self.macros)} macros.")

    def _export_json_to_box(self):
        if not self.macros:
            self._set_status("No hay macros para exportar.")
            return
        payload = export_user_json(self.notes, self.macros)
        self.json_box.delete("1.0", "end")
        self.json_box.insert("1.0", json.dumps(payload, indent=2, ensure_ascii=False))
        self._set_status("JSON exportado al cuadro.")

    def _save_to_file(self):
        if not self.macros:
            self._set_status("No hay macros para guardar.")
            return
        payload = export_user_json(self.notes, self.macros)
        try:
            with open("macros.json", "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            self._set_status("Guardado en macros.json")
        except Exception as e:
            self._set_status(f"Error guardando: {e}")

    # ============================
    # Lista
    # ============================
    def _refresh_list(self):
        for w in self.listbox.winfo_children():
            w.destroy()

        if not self.macros:
            ctk.CTkLabel(self.listbox, text="No hay macros.\nImporta un JSON 🙂", justify="left").pack(padx=12, pady=12)
            return

        for idx, m in enumerate(self.macros):
            btn = ctk.CTkButton(
                self.listbox,
                text=f"{m.name}\nType: {m.type}  |  Frames: {len(m.frames or [])}",
                anchor="w",
                height=58,
                command=lambda i=idx: self._select_macro(i),
            )
            btn.pack(fill="x", padx=10, pady=8)

    def _select_macro(self, idx: int):
        self.selected_index = idx
        m = self.macros[idx]
        self._set_status(f"Seleccionada: {m.name}")

    def _current_macro(self) -> Optional[Macro]:
        if self.selected_index is None:
            return None
        if self.selected_index < 0 or self.selected_index >= len(self.macros):
            return None
        return self.macros[self.selected_index]

    # ============================
    # Preview playback (NO controla Windows)
    # ============================
    def _preview_run_current(self):
        m = self._current_macro()
        if not m:
            self._set_status("Selecciona una macro primero.")
            return
        if self._preview_thread and self._preview_thread.is_alive():
            self._set_status("Ya hay un preview corriendo.")
            return

        self._preview_stop.clear()
        self._preview_thread = threading.Thread(target=self._preview_loop, args=(m,), daemon=True)
        self._preview_thread.start()

    def _preview_stop_now(self):
        self._preview_stop.set()
        self._set_status("Stop enviado.")

    def _preview_loop(self, m: Macro):
        frames = m.frames or []
        if not frames:
            self._set_status_threadsafe("Macro sin frames.")
            return

        # estado acumulado: si un frame solo pone jump=false, mantiene el resto
        state: Dict[str, Any] = {k: (0.0 if k in AXES else False) for k in ALL_KEYS}

        for idx, fr in enumerate(frames):
            if self._preview_stop.is_set():
                self._set_status_threadsafe("⏹ Preview detenido.")
                return

            # notas internas (stage markers)
            if "__note__" in fr.inputs:
                self._set_status_threadsafe(str(fr.inputs["__note__"]))
                time.sleep(0.15)
                continue

            # aplica deltas del frame
            for k, v in fr.inputs.items():
                state[k] = v

            self._update_preview_threadsafe(m.name, idx + 1, fr.dt_ms, state)

            time.sleep(max(0.001, fr.dt_ms / 1000.0))

        self._set_status_threadsafe("✅ Preview finalizado.")

    def _update_preview_threadsafe(self, macro_name: str, frame_no: int, dt_ms: int, state: Dict[str, Any]):
        def ui():
            self.lbl_macro.configure(text=f"Macro: {macro_name}  |  Frame: {frame_no}  |  dt: {dt_ms}ms")
            for k in AXES:
                try:
                    val = float(state.get(k, 0.0))
                except Exception:
                    val = 0.0
                self.axis_labels[k].configure(text=f"{val:+.2f}")

            for b in BUTTONS:
                on = bool(state.get(b, False))
                self.btn_badges[b].configure(text=f"{b}: {'ON' if on else 'OFF'}")

        self.after(0, ui)

    # ============================
    # Status
    # ============================
    def _set_status(self, msg: str):
        self.status.configure(text=msg)

    def _set_status_threadsafe(self, msg: str):
        self.after(0, lambda: self._set_status(msg))


if __name__ == "__main__":
    app = App()
    app.mainloop()
