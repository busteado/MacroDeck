import json
import time
import threading
from dataclasses import dataclass, asdict
from typing import List, Optional

import customtkinter as ctk
from pynput import keyboard


# ----------------------------
# Modelo de datos
# ----------------------------
@dataclass
class MacroStep:
    # type: "key" o "wait"
    type: str
    key: Optional[str] = None      # ejemplo: "a", "space", "shift"
    action: Optional[str] = None   # "press" o "release"
    seconds: Optional[float] = None


@dataclass
class Macro:
    name: str
    steps: List[MacroStep]
    hotkey: Optional[str] = None   # ejemplo: "f6"


# ----------------------------
# Motor de ejecución
# ----------------------------
class MacroEngine:
    def __init__(self):
        self._kb = keyboard.Controller()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self):
        self._stop_event.set()

    def run(self, macro: Macro):
        if self.is_running():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_blocking, args=(macro,), daemon=True)
        self._thread.start()

    def _run_blocking(self, macro: Macro):
        for step in macro.steps:
            if self._stop_event.is_set():
                break

            if step.type == "wait":
                time.sleep(float(step.seconds or 0))
                continue

            if step.type == "key":
                key_obj = self._parse_key(step.key or "")
                if step.action == "press":
                    self._kb.press(key_obj)
                elif step.action == "release":
                    self._kb.release(key_obj)

    @staticmethod
    def _parse_key(k: str):
        k = k.strip().lower()
        special = {
            "space": keyboard.Key.space,
            "enter": keyboard.Key.enter,
            "tab": keyboard.Key.tab,
            "esc": keyboard.Key.esc,
            "escape": keyboard.Key.esc,
            "shift": keyboard.Key.shift,
            "ctrl": keyboard.Key.ctrl,
            "control": keyboard.Key.ctrl,
            "alt": keyboard.Key.alt,
            "cmd": keyboard.Key.cmd,
            "win": keyboard.Key.cmd,
            "up": keyboard.Key.up,
            "down": keyboard.Key.down,
            "left": keyboard.Key.left,
            "right": keyboard.Key.right,
            "backspace": keyboard.Key.backspace,
            "delete": keyboard.Key.delete,
        }
        if k in special:
            return special[k]
        # teclas tipo f1..f12
        if k.startswith("f") and k[1:].isdigit():
            n = int(k[1:])
            return getattr(keyboard.Key, f"f{n}")
        # caracter normal
        return k


# ----------------------------
# Persistencia
# ----------------------------
def save_macros(path: str, macros: List[Macro]):
    payload = []
    for m in macros:
        payload.append({
            "name": m.name,
            "hotkey": m.hotkey,
            "steps": [asdict(s) for s in m.steps],
        })
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def load_macros(path: str) -> List[Macro]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        macros = []
        for item in payload:
            steps = [MacroStep(**s) for s in item.get("steps", [])]
            macros.append(Macro(name=item.get("name", "Macro"), steps=steps, hotkey=item.get("hotkey")))
        return macros
    except FileNotFoundError:
        return []
    except Exception:
        return []


# ----------------------------
# UI
# ----------------------------
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MacroDeck (genérico)")
        self.geometry("920x560")
        self.minsize(860, 520)

        self.engine = MacroEngine()
        self.data_path = "macros.json"
        self.macros: List[Macro] = load_macros(self.data_path)

        self._hotkey_listener = None
        self._start_hotkey_listener()

        self._build_ui()
        self._refresh_macro_list()

    def _build_ui(self):
        # Layout: izquierda lista / derecha editor
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(self, corner_radius=16)
        left.grid(row=0, column=0, sticky="nsw", padx=14, pady=14)
        left.grid_rowconfigure(2, weight=1)

        title = ctk.CTkLabel(left, text="Macros", font=ctk.CTkFont(size=18, weight="bold"))
        title.grid(row=0, column=0, padx=14, pady=(14, 8), sticky="w")

        btn_row = ctk.CTkFrame(left, fg_color="transparent")
        btn_row.grid(row=1, column=0, padx=14, pady=(0, 10), sticky="ew")
        btn_row.grid_columnconfigure((0, 1), weight=1)

        self.btn_new = ctk.CTkButton(btn_row, text="Nueva", command=self._new_macro)
        self.btn_new.grid(row=0, column=0, padx=(0, 8), sticky="ew")

        self.btn_delete = ctk.CTkButton(btn_row, text="Borrar", fg_color="#B23B3B", hover_color="#8E2F2F",
                                        command=self._delete_macro)
        self.btn_delete.grid(row=0, column=1, padx=(8, 0), sticky="ew")

        self.listbox = ctk.CTkScrollableFrame(left, width=260, height=420, corner_radius=16)
        self.listbox.grid(row=2, column=0, padx=14, pady=(0, 14), sticky="nsew")

        # Panel derecho
        right = ctk.CTkFrame(self, corner_radius=16)
        right.grid(row=0, column=1, sticky="nsew", padx=(0, 14), pady=14)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(4, weight=1)

        self.lbl_name = ctk.CTkLabel(right, text="Editor", font=ctk.CTkFont(size=18, weight="bold"))
        self.lbl_name.grid(row=0, column=0, padx=18, pady=(16, 6), sticky="w")

        form = ctk.CTkFrame(right, corner_radius=14)
        form.grid(row=1, column=0, padx=18, pady=(0, 10), sticky="ew")
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text="Nombre").grid(row=0, column=0, padx=12, pady=10, sticky="w")
        self.entry_name = ctk.CTkEntry(form, placeholder_text="Ej: Macro 1")
        self.entry_name.grid(row=0, column=1, padx=12, pady=10, sticky="ew")

        ctk.CTkLabel(form, text="Hotkey (opcional)").grid(row=1, column=0, padx=12, pady=10, sticky="w")
        self.entry_hotkey = ctk.CTkEntry(form, placeholder_text="Ej: f6")
        self.entry_hotkey.grid(row=1, column=1, padx=12, pady=10, sticky="ew")

        steps_bar = ctk.CTkFrame(right, fg_color="transparent")
        steps_bar.grid(row=2, column=0, padx=18, pady=(0, 10), sticky="ew")
        steps_bar.grid_columnconfigure((0, 1, 2), weight=1)

        self.btn_add_key = ctk.CTkButton(steps_bar, text="Añadir tecla", command=self._add_key_step)
        self.btn_add_key.grid(row=0, column=0, padx=(0, 8), sticky="ew")

        self.btn_add_wait = ctk.CTkButton(steps_bar, text="Añadir pausa", command=self._add_wait_step)
        self.btn_add_wait.grid(row=0, column=1, padx=8, sticky="ew")

        self.btn_clear_steps = ctk.CTkButton(steps_bar, text="Limpiar pasos", fg_color="#4A4A4A",
                                             hover_color="#3A3A3A", command=self._clear_steps)
        self.btn_clear_steps.grid(row=0, column=2, padx=(8, 0), sticky="ew")

        self.steps_frame = ctk.CTkScrollableFrame(right, corner_radius=16)
        self.steps_frame.grid(row=3, column=0, padx=18, pady=(0, 10), sticky="nsew")

        actions = ctk.CTkFrame(right, corner_radius=14)
        actions.grid(row=5, column=0, padx=18, pady=(0, 16), sticky="ew")
        actions.grid_columnconfigure((0, 1, 2), weight=1)

        self.btn_save = ctk.CTkButton(actions, text="Guardar", command=self._save_current)
        self.btn_save.grid(row=0, column=0, padx=(0, 10), pady=12, sticky="ew")

        self.btn_run = ctk.CTkButton(actions, text="Ejecutar", command=self._run_current)
        self.btn_run.grid(row=0, column=1, padx=10, pady=12, sticky="ew")

        self.btn_stop = ctk.CTkButton(actions, text="Stop", fg_color="#B23B3B", hover_color="#8E2F2F",
                                      command=self._stop_run)
        self.btn_stop.grid(row=0, column=2, padx=(10, 0), pady=12, sticky="ew")

        self.status = ctk.CTkLabel(right, text="Listo.", anchor="w")
        self.status.grid(row=6, column=0, padx=18, pady=(0, 12), sticky="ew")

        self.selected_index: Optional[int] = None
        self.current_steps_widgets = []
        self._load_into_editor(0 if self.macros else None)

    # ---- Lista izquierda ----
    def _refresh_macro_list(self):
        for w in self.listbox.winfo_children():
            w.destroy()

        if not self.macros:
            ctk.CTkLabel(self.listbox, text="No hay macros.\nCrea una nueva 🙂", justify="left").pack(padx=12, pady=12)
            return

        for idx, macro in enumerate(self.macros):
            text = macro.name if macro.name else f"Macro {idx+1}"
            sub = f"Hotkey: {macro.hotkey}" if macro.hotkey else "Hotkey: —"
            btn = ctk.CTkButton(
                self.listbox,
                text=f"{text}\n{sub}",
                anchor="w",
                height=54,
                command=lambda i=idx: self._load_into_editor(i),
            )
            btn.pack(fill="x", padx=10, pady=8)

    def _new_macro(self):
        self.macros.append(Macro(name="Nueva macro", steps=[
            MacroStep(type="wait", seconds=0.2),
            MacroStep(type="key", key="space", action="press"),
            MacroStep(type="key", key="space", action="release"),
        ]))
        self._load_into_editor(len(self.macros) - 1)
        self._refresh_macro_list()

    def _delete_macro(self):
        if self.selected_index is None or not self.macros:
            return
        i = self.selected_index
        self.macros.pop(i)
        self.selected_index = None
        self._refresh_macro_list()
        self._load_into_editor(0 if self.macros else None)
        save_macros(self.data_path, self.macros)
        self._set_status("Macro borrada y guardado.")

    # ---- Editor ----
    def _load_into_editor(self, index: Optional[int]):
        self.selected_index = index
        for w in self.steps_frame.winfo_children():
            w.destroy()

        if index is None:
            self.entry_name.delete(0, "end")
            self.entry_hotkey.delete(0, "end")
            self.lbl_name.configure(text="Editor")
            self._set_status("Crea una macro para empezar.")
            return

        m = self.macros[index]
        self.lbl_name.configure(text=f"Editor — {m.name}")
        self.entry_name.delete(0, "end")
        self.entry_name.insert(0, m.name)
        self.entry_hotkey.delete(0, "end")
        if m.hotkey:
            self.entry_hotkey.insert(0, m.hotkey)

        for s_idx, step in enumerate(m.steps):
            self._render_step_row(s_idx, step)

    def _render_step_row(self, s_idx: int, step: MacroStep):
        row = ctk.CTkFrame(self.steps_frame, corner_radius=14)
        row.pack(fill="x", padx=10, pady=8)

        row.grid_columnconfigure(1, weight=1)

        badge = ctk.CTkLabel(row, text=f"{s_idx+1}", width=28, font=ctk.CTkFont(weight="bold"))
        badge.grid(row=0, column=0, padx=10, pady=10)

        if step.type == "wait":
            label = ctk.CTkLabel(row, text="Pausa (segundos):")
            label.grid(row=0, column=1, padx=10, sticky="w")
            entry = ctk.CTkEntry(row)
            entry.grid(row=0, column=2, padx=10, sticky="ew")
            entry.insert(0, str(step.seconds or 0.1))
            btn_upd = ctk.CTkButton(row, text="OK", width=60,
                                    command=lambda e=entry, i=s_idx: self._update_wait(i, e))
            btn_upd.grid(row=0, column=3, padx=10)
        else:
            label = ctk.CTkLabel(row, text="Tecla:")
            label.grid(row=0, column=1, padx=10, sticky="w")

            entry_key = ctk.CTkEntry(row)
            entry_key.grid(row=0, column=2, padx=10, sticky="ew")
            entry_key.insert(0, step.key or "space")

            opt = ctk.CTkOptionMenu(row, values=["press", "release"])
            opt.grid(row=0, column=3, padx=10)
            opt.set(step.action or "press")

            btn_upd = ctk.CTkButton(
                row, text="OK", width=60,
                command=lambda e=entry_key, o=opt, i=s_idx: self._update_key(i, e, o)
            )
            btn_upd.grid(row=0, column=4, padx=10)

        btn_del = ctk.CTkButton(row, text="✕", width=42, fg_color="#4A4A4A", hover_color="#3A3A3A",
                                command=lambda i=s_idx: self._delete_step(i))
        btn_del.grid(row=0, column=5, padx=10)

    def _update_wait(self, step_index: int, entry: ctk.CTkEntry):
        m = self._get_current_macro()
        if not m:
            return
        try:
            val = float(entry.get().strip())
        except ValueError:
            self._set_status("Pausa inválida.")
            return
        m.steps[step_index].seconds = max(0.0, val)
        self._set_status("Paso actualizado.")

    def _update_key(self, step_index: int, entry_key: ctk.CTkEntry, opt: ctk.CTkOptionMenu):
        m = self._get_current_macro()
        if not m:
            return
        m.steps[step_index].key = entry_key.get().strip()
        m.steps[step_index].action = opt.get()
        self._set_status("Paso actualizado.")

    def _delete_step(self, step_index: int):
        m = self._get_current_macro()
        if not m:
            return
        m.steps.pop(step_index)
        self._load_into_editor(self.selected_index)
        self._set_status("Paso eliminado.")

    def _add_key_step(self):
        m = self._get_current_macro()
        if not m:
            return
        m.steps.append(MacroStep(type="key", key="space", action="press"))
        m.steps.append(MacroStep(type="key", key="space", action="release"))
        self._load_into_editor(self.selected_index)
        self._set_status("Añadido paso de tecla.")

    def _add_wait_step(self):
        m = self._get_current_macro()
        if not m:
            return
        m.steps.append(MacroStep(type="wait", seconds=0.2))
        self._load_into_editor(self.selected_index)
        self._set_status("Añadida pausa.")

    def _clear_steps(self):
        m = self._get_current_macro()
        if not m:
            return
        m.steps = []
        self._load_into_editor(self.selected_index)
        self._set_status("Pasos limpiados.")

    def _save_current(self):
        m = self._get_current_macro()
        if not m:
            return
        name = self.entry_name.get().strip() or "Macro"
        hotkey = self.entry_hotkey.get().strip().lower() or None
        m.name = name
        m.hotkey = hotkey
        save_macros(self.data_path, self.macros)
        self._refresh_macro_list()
        self._set_status("Guardado en macros.json (reinicia para refrescar hotkeys).")

    def _run_current(self):
        m = self._get_current_macro()
        if not m:
            return
        if self.engine.is_running():
            self._set_status("Ya hay una macro corriendo.")
            return
        self.engine.run(m)
        self._set_status("Ejecutando… (Stop para parar)")

    def _stop_run(self):
        self.engine.stop()
        self._set_status("Stop enviado.")

    def _get_current_macro(self) -> Optional[Macro]:
        if self.selected_index is None:
            return None
        if self.selected_index < 0 or self.selected_index >= len(self.macros):
            return None
        return self.macros[self.selected_index]

    def _set_status(self, msg: str):
        self.status.configure(text=msg)

    # ---- Hotkeys globales (simple) ----
    def _start_hotkey_listener(self):
        # Listener muy básico: si una macro tiene hotkey "f6", al pulsar f6 la ejecuta.
        def on_press(key):
            try:
                kname = key.char.lower() if hasattr(key, "char") and key.char else None
            except Exception:
                kname = None

            # especiales (f1..f12)
            if isinstance(key, keyboard.Key):
                kname = str(key).replace("Key.", "")

            if not kname:
                return

            for m in self.macros:
                if m.hotkey and m.hotkey.lower() == kname:
                    if not self.engine.is_running():
                        self.engine.run(m)
                        self._set_status(f"Hotkey: ejecutando '{m.name}'")
                    break

        self._hotkey_listener = keyboard.Listener(on_press=on_press)
        self._hotkey_listener.daemon = True
        self._hotkey_listener.start()


if __name__ == "__main__":
    app = App()
    app.mainloop()
