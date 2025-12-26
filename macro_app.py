import json
import time
import threading
import socket
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Callable, Tuple, Any

import customtkinter as ctk
import pygame


# ============================
# Config conexión con tu juego
# ============================
UDP_HOST = "127.0.0.1"
UDP_PORT = 28015  # cambia si quieres


# ============================
# Modelo de datos (MACRO INPUT)
# ============================
@dataclass
class MacroFrame:
    dt_ms: int
    inputs: Dict[str, Any]  # throttle/steer/pitch/yaw/roll/jump/boost/handbrake/airRollL/airRollR...


@dataclass
class Macro:
    name: str
    type: str  # "Single-Stage" | "Multi-Stage"
    description: str
    trigger: Optional[str] = None
    enabled: bool = True
    frames: List[MacroFrame] = None


# ============================
# Biblioteca por defecto (las de tu imagen)
# Timings orientativos: ajusta a tu física/binds.
# ============================
def default_macros() -> List[Macro]:
    def F(dt, **inp):
        return MacroFrame(dt_ms=int(dt), inputs=inp)

    return [
        Macro(
            name="Half Flip",
            type="Single-Stage",
            description="Half-flip: salto, backflip, cancel, air roll para enderezar.",
            frames=[
                F(80, jump=True), F(40, jump=False),
                F(60, pitch=1.0, jump=True), F(30, jump=False, pitch=1.0),
                F(140, pitch=-1.0),
                F(220, airRollL=True, pitch=-0.2),
                F(100, airRollL=False, pitch=0.0),
            ],
        ),
        Macro(
            name="Musty (2-Stage)",
            type="Multi-Stage",
            description="Musty: pop + pitch back + flick (2 saltos).",
            frames=[
                F(70, jump=True), F(40, jump=False),
                F(260, pitch=1.0),
                F(70, jump=True, pitch=-1.0), F(40, jump=False, pitch=-1.0),
                F(160, pitch=-0.2),
            ],
        ),
        Macro(
            name="Stall (Left side)",
            type="Single-Stage",
            description="Stall izquierda (orientativo): yaw/roll + jump breve.",
            frames=[
                F(60, yaw=-1.0, roll=-1.0),
                F(45, yaw=-1.0, roll=-1.0, jump=True),
                F(35, jump=False, yaw=0.0, roll=0.0),
            ],
        ),
        Macro(
            name="Stall (Right side)",
            type="Single-Stage",
            description="Stall derecha (orientativo): yaw/roll + jump breve.",
            frames=[
                F(60, yaw=1.0, roll=1.0),
                F(45, yaw=1.0, roll=1.0, jump=True),
                F(35, jump=False, yaw=0.0, roll=0.0),
            ],
        ),
        Macro(
            name="Speed Flip Right",
            type="Single-Stage",
            description="Speedflip derecha: boost + salto + diagonal + cancel.",
            frames=[
                F(200, throttle=1.0, boost=True),
                F(70, jump=True), F(40, jump=False),
                F(65, jump=True, pitch=-1.0, yaw=0.55), F(35, jump=False, pitch=-1.0, yaw=0.55),
                F(140, pitch=1.0, yaw=-0.15),
                F(300, throttle=1.0, boost=True),
            ],
        ),
        Macro(
            name="Speed Flip Left",
            type="Single-Stage",
            description="Speedflip izquierda: boost + salto + diagonal + cancel.",
            frames=[
                F(200, throttle=1.0, boost=True),
                F(70, jump=True), F(40, jump=False),
                F(65, jump=True, pitch=-1.0, yaw=-0.55), F(35, jump=False, pitch=-1.0, yaw=-0.55),
                F(140, pitch=1.0, yaw=0.15),
                F(300, throttle=1.0, boost=True),
            ],
        ),
        Macro(
            name="Wall Dash Right",
            type="Single-Stage",
            description="Wall dash derecha (patrón). Repite si quieres más duración.",
            frames=[
                F(120, throttle=1.0, boost=True),
                F(60, jump=True, steer=0.35), F(40, jump=False, steer=0.35),
                F(90, steer=0.35, boost=True),
                F(60, jump=True, steer=0.35), F(40, jump=False, steer=0.35),
            ],
        ),
        Macro(
            name="Wall Dash Left",
            type="Single-Stage",
            description="Wall dash izquierda (patrón). Repite si quieres más duración.",
            frames=[
                F(120, throttle=1.0, boost=True),
                F(60, jump=True, steer=-0.35), F(40, jump=False, steer=-0.35),
                F(90, steer=-0.35, boost=True),
                F(60, jump=True, steer=-0.35), F(40, jump=False, steer=-0.35),
            ],
        ),
        Macro(
            name="Wave Dash",
            type="Single-Stage",
            description="Wave dash: pequeño salto + dash al tocar suelo.",
            frames=[
                F(70, jump=True), F(50, jump=False),
                F(170, pitch=-0.6),
                F(55, pitch=-0.9, jump=True), F(40, jump=False, pitch=-0.3),
            ],
        ),
        Macro(
            name="Kuxir Pinch Setup",
            type="Single-Stage",
            description="Setup pinch: velocidad + salto + air roll para orientar.",
            frames=[
                F(160, throttle=1.0, boost=True),
                F(70, jump=True), F(40, jump=False),
                F(260, airRollR=True, yaw=0.35, pitch=-0.25),
                F(120, airRollR=False),
            ],
        ),
        Macro(
            name="Breezi Flick (2-Stage)",
            type="Multi-Stage",
            description="Breezi simplificado: pop + rotación + flick.",
            frames=[
                F(70, jump=True), F(40, jump=False),
                F(420, airRollL=True, yaw=-0.55, pitch=0.35),
                F(70, jump=True, pitch=-1.0), F(40, jump=False, pitch=-1.0),
                F(140, pitch=-0.35),
            ],
        ),
        Macro(
            name="Mawkzy Flick (2-Stage)",
            type="Multi-Stage",
            description="Mawkzy (base): pop + micro ajuste + flick rápido.",
            frames=[
                F(70, jump=True), F(40, jump=False),
                F(180, pitch=0.55),
                F(120, pitch=0.0, yaw=0.25),
                F(70, jump=True, pitch=-1.0, yaw=0.25), F(40, jump=False, pitch=-1.0, yaw=0.25),
                F(150, pitch=-0.25),
            ],
        ),
    ]


# ============================
# Persistencia
# ============================
def save_macros(path: str, macros: List[Macro]):
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
            frames = [MacroFrame(**fr) for fr in item.get("frames", [])]
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


# ============================
# Lectura de mando (pygame)
# ============================
class GamepadReader:
    def __init__(self):
        self.ready = False
        self.joy: Optional[pygame.joystick.Joystick] = None
        self._lock = threading.Lock()
        self._buttons: set[str] = set()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self.btn_map: Dict[str, int] = {
            "A": 0, "B": 1, "X": 2, "Y": 3,
            "LB": 4, "RB": 5,
            "BACK": 6, "START": 7,
            "LSTICK": 8, "RSTICK": 9,
        }
        self.trigger_threshold = 0.55

    def start(self):
        pygame.init()
        pygame.joystick.init()
        if pygame.joystick.get_count() <= 0:
            self.ready = False
            return
        self.joy = pygame.joystick.Joystick(0)
        self.joy.init()
        self.ready = True

        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def snapshot(self) -> set[str]:
        with self._lock:
            return set(self._buttons)

    def _loop(self):
        while not self._stop.is_set():
            pygame.event.pump()
            if not self.joy:
                time.sleep(0.03)
                continue

            buttons = set()

            for name, idx in self.btn_map.items():
                try:
                    if self.joy.get_button(idx):
                        buttons.add(name)
                except Exception:
                    pass

            # triggers por ejes (heurística)
            rt = False
            lt = False
            for ax in [2, 3, 4, 5]:
                try:
                    v = float(self.joy.get_axis(ax))
                except Exception:
                    continue
                if v > self.trigger_threshold:
                    rt = True
                if v < -self.trigger_threshold:
                    lt = True
            if rt:
                buttons.add("RT")
            if lt:
                buttons.add("LT")

            with self._lock:
                self._buttons = buttons

            time.sleep(0.02)


# ============================
# Engine: envía frames a tu juego por UDP
# ============================
class MacroNetEngine:
    def __init__(self, status_cb: Callable[[str], None], host: str, port: int):
        self.status_cb = status_cb
        self.host = host
        self.port = port
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self):
        self._stop.set()

    def run(self, macro: Macro):
        if self.is_running():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_blocking, args=(macro,), daemon=True)
        self._thread.start()

    def _send(self, payload: dict):
        try:
            data = json.dumps(payload).encode("utf-8")
            self._sock.sendto(data, (self.host, self.port))
        except Exception:
            pass

    def _run_blocking(self, macro: Macro):
        self.status_cb(f"▶ Macro: {macro.name} → UDP {self.host}:{self.port}")

        # start
        self._send({"type": "macro_start", "name": macro.name, "t": time.time()})

        for fr in (macro.frames or []):
            if self._stop.is_set():
                break

            # manda input frame
            self._send({
                "type": "macro_frame",
                "name": macro.name,
                "dt_ms": fr.dt_ms,
                "inputs": fr.inputs,
                "t": time.time()
            })

            time.sleep(max(0.0, fr.dt_ms / 1000.0))

        # end + reset (inputs neutros)
        self._send({"type": "macro_end", "name": macro.name, "t": time.time()})
        self._send({"type": "macro_reset", "inputs": {
            "throttle": 0.0, "steer": 0.0, "pitch": 0.0, "yaw": 0.0, "roll": 0.0,
            "jump": False, "boost": False, "handbrake": False, "airRollL": False, "airRollR": False
        }, "t": time.time()})

        self.status_cb("✅ Fin." if not self._stop.is_set() else "⏹ Stop.")


# ============================
# UI
# ============================
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

TRIGGERS = ["—", "A", "B", "X", "Y", "LB", "RB", "LT", "RT", "START", "BACK", "LSTICK", "RSTICK"]


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MacroDeck — Connected to Your Game (UDP)")
        self.geometry("1040x640")
        self.minsize(960, 580)

        self.data_path = "macros.json"
        self.macros: List[Macro] = load_macros(self.data_path) or default_macros()

        self.gamepad = GamepadReader()
        self.gamepad.start()

        self.engine = MacroNetEngine(self._set_status_threadsafe, UDP_HOST, UDP_PORT)

        self.auto_start = True
        self.listening = True
        self._last_back_time = 0.0
        self._last_buttons = set()

        self.selected_index: Optional[int] = None

        self._build_ui()
        self._refresh_list()
        self._load_into_editor(0 if self.macros else None)

        self.after(60, self._poll_gamepad)

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(self, corner_radius=16)
        left.grid(row=0, column=0, padx=14, pady=14, sticky="nsw")
        left.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(left, text="Macros", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, padx=14, pady=(14, 8), sticky="w"
        )

        topbar = ctk.CTkFrame(left, fg_color="transparent")
        topbar.grid(row=1, column=0, padx=14, pady=(0, 10), sticky="ew")
        topbar.grid_columnconfigure((0, 1), weight=1)

        self.toggle_autostart = ctk.CTkSwitch(topbar, text="Auto-Start Listening", command=self._on_toggle_autostart)
        self.toggle_autostart.select()
        self.toggle_autostart.grid(row=0, column=0, sticky="w")

        self.badge_listen = ctk.CTkLabel(topbar, text="Listening: ON", corner_radius=8)
        self.badge_listen.grid(row=0, column=1, sticky="e")

        self.pad_status = ctk.CTkLabel(left, text=f"UDP → {UDP_HOST}:{UDP_PORT} · Mando: detectando…", corner_radius=8)
        self.pad_status.grid(row=2, column=0, padx=14, pady=(0, 10), sticky="ew")

        self.listbox = ctk.CTkScrollableFrame(left, width=340, corner_radius=16)
        self.listbox.grid(row=3, column=0, padx=14, pady=(0, 14), sticky="nsew")

        # Right
        right = ctk.CTkFrame(self, corner_radius=16)
        right.grid(row=0, column=1, padx=(0, 14), pady=14, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(3, weight=1)

        self.lbl_title = ctk.CTkLabel(right, text="Editor", font=ctk.CTkFont(size=18, weight="bold"))
        self.lbl_title.grid(row=0, column=0, padx=18, pady=(16, 6), sticky="w")

        form = ctk.CTkFrame(right, corner_radius=14)
        form.grid(row=1, column=0, padx=18, pady=(0, 10), sticky="ew")
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text="Nombre").grid(row=0, column=0, padx=12, pady=10, sticky="w")
        self.entry_name = ctk.CTkEntry(form)
        self.entry_name.grid(row=0, column=1, padx=12, pady=10, sticky="ew")

        ctk.CTkLabel(form, text="Tipo").grid(row=1, column=0, padx=12, pady=10, sticky="w")
        self.entry_type = ctk.CTkEntry(form)
        self.entry_type.grid(row=1, column=1, padx=12, pady=10, sticky="ew")

        ctk.CTkLabel(form, text="Trigger (mando)").grid(row=2, column=0, padx=12, pady=10, sticky="w")
        self.opt_trigger = ctk.CTkOptionMenu(form, values=TRIGGERS)
        self.opt_trigger.grid(row=2, column=1, padx=12, pady=10, sticky="w")

        self.switch_enabled = ctk.CTkSwitch(form, text="Enabled")
        self.switch_enabled.grid(row=2, column=1, padx=12, pady=10, sticky="e")

        self.steps_frame = ctk.CTkScrollableFrame(right, corner_radius=16)
        self.steps_frame.grid(row=2, column=0, padx=18, pady=(0, 10), sticky="nsew")

        actions = ctk.CTkFrame(right, corner_radius=14)
        actions.grid(row=4, column=0, padx=18, pady=(0, 14), sticky="ew")
        actions.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkButton(actions, text="Guardar", command=self._save_current).grid(
            row=0, column=0, padx=(0, 10), pady=12, sticky="ew"
        )
        ctk.CTkButton(actions, text="Start", command=self._run_current).grid(
            row=0, column=1, padx=10, pady=12, sticky="ew"
        )
        ctk.CTkButton(actions, text="Stop", fg_color="#B23B3B", hover_color="#8E2F2F", command=self._stop_run).grid(
            row=0, column=2, padx=(10, 0), pady=12, sticky="ew"
        )

        self.status = ctk.CTkLabel(right, text="Listo.", anchor="w")
        self.status.grid(row=5, column=0, padx=18, pady=(0, 10), sticky="ew")

        hint = ctk.CTkLabel(
            right,
            text="Doble BACK = toggle Listening. Auto-Start ejecuta macro al pulsar su Trigger.",
            text_color="#9AA4B2",
            anchor="w",
        )
        hint.grid(row=6, column=0, padx=18, pady=(0, 12), sticky="ew")

    def _refresh_list(self):
        for w in self.listbox.winfo_children():
            w.destroy()

        for idx, m in enumerate(self.macros):
            trigger = m.trigger or "—"
            enabled = "✓" if m.enabled else "✗"
            btn = ctk.CTkButton(
                self.listbox,
                text=f"{enabled}  {m.name}\nType: {m.type}   Trigger: {trigger}",
                anchor="w",
                height=58,
                command=lambda i=idx: self._load_into_editor(i),
            )
            btn.pack(fill="x", padx=10, pady=8)

    def _load_into_editor(self, index: Optional[int]):
        self.selected_index = index
        for w in self.steps_frame.winfo_children():
            w.destroy()

        if index is None:
            self.lbl_title.configure(text="Editor")
            return

        m = self.macros[index]
        self.lbl_title.configure(text=f"Editor — {m.name}")

        self.entry_name.delete(0, "end")
        self.entry_name.insert(0, m.name)

        self.entry_type.delete(0, "end")
        self.entry_type.insert(0, m.type)

        self.opt_trigger.set(m.trigger if m.trigger in TRIGGERS else "—")
        if m.enabled:
            self.switch_enabled.select()
        else:
            self.switch_enabled.deselect()

        ctk.CTkLabel(self.steps_frame, text=m.description, justify="left", wraplength=650).pack(
            fill="x", padx=12, pady=(10, 8)
        )

        for i, fr in enumerate(m.frames or []):
            pretty = ", ".join([f"{k}={v}" for k, v in fr.inputs.items()])
            line = f"{i+1:02d}. dt={fr.dt_ms}ms  |  {pretty}"
            ctk.CTkLabel(self.steps_frame, text=line, anchor="w", justify="left", wraplength=650).pack(
                fill="x", padx=12, pady=4
            )

    def _save_current(self):
        m = self._get_current()
        if not m:
            return

        m.name = self.entry_name.get().strip() or m.name
        m.type = self.entry_type.get().strip() or m.type

        trig = self.opt_trigger.get()
        m.trigger = None if trig == "—" else trig

        m.enabled = bool(self.switch_enabled.get())

        save_macros(self.data_path, self.macros)
        self._refresh_list()
        self._set_status("Guardado en macros.json")

    def _run_current(self):
        m = self._get_current()
        if not m:
            return
        if self.engine.is_running():
            self._set_status("Ya hay una macro corriendo.")
            return
        self.engine.run(m)

    def _stop_run(self):
        self.engine.stop()
        self._set_status("Stop enviado.")

    def _get_current(self) -> Optional[Macro]:
        if self.selected_index is None:
            return None
        if self.selected_index < 0 or self.selected_index >= len(self.macros):
            return None
        return self.macros[self.selected_index]

    def _set_status(self, msg: str):
        self.status.configure(text=msg)

    def _set_status_threadsafe(self, msg: str):
        self.after(0, lambda: self._set_status(msg))

    def _on_toggle_autostart(self):
        self.auto_start = bool(self.toggle_autostart.get())

    def _poll_gamepad(self):
        if self.gamepad.ready:
            buttons = self.gamepad.snapshot()
            self.pad_status.configure(text=f"UDP → {UDP_HOST}:{UDP_PORT} · Mando: OK · {', '.join(sorted(buttons)) or '—'}")

            now = time.time()
            just_pressed = buttons - self._last_buttons

            # doble BACK → toggle listening
            if "BACK" in just_pressed:
                if now - self._last_back_time < 0.6:
                    self.listening = not self.listening
                    self.badge_listen.configure(text=f"Listening: {'ON' if self.listening else 'OFF'}")
                    self._set_status(f"Listening {'activado' if self.listening else 'desactivado'}")
                self._last_back_time = now

            # auto-start macros por trigger (solo en just_pressed)
            if self.auto_start and self.listening and (not self.engine.is_running()):
                for m in self.macros:
                    if m.enabled and m.trigger and (m.trigger in just_pressed):
                        self.engine.run(m)
                        break

            self._last_buttons = buttons
        else:
            self.pad_status.configure(text=f"UDP → {UDP_HOST}:{UDP_PORT} · Mando: NO detectado")

        self.after(60, self._poll_gamepad)


if __name__ == "__main__":
    app = App()
    app.mainloop()
