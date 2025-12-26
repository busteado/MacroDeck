import json
import time
import threading
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Callable, Tuple

import customtkinter as ctk
import pygame
from pynput import keyboard


# ============================
# Modelo de datos (GUÍAS)
# ============================
@dataclass
class Step:
    # type: note | wait | expect
    type: str
    text: Optional[str] = None
    seconds: Optional[float] = None
    expect: Optional[str] = None  # e.g. "A", "B", "X", "Y", "LB", "RB", "LT", "RT", "LS_UP", "LS_DOWN", "LS_DIAG"


@dataclass
class Guide:
    name: str
    type: str  # "Single-Stage" | "Multi-Stage"
    description: str
    trigger: Optional[str] = None  # controller button name (A/B/...)
    enabled: bool = True
    steps: List[Step] = None


# ============================
# Biblioteca por defecto
# (son GUÍAS; NO automatizan)
# ============================
def default_guides() -> List[Guide]:
    return [
        Guide(
            name="Half Flip",
            type="Single-Stage",
            description="Guía de timing y pasos para practicar half-flip.",
            steps=[
                Step("note", "Prepárate en línea recta."),
                Step("wait", seconds=0.8),
                Step("expect", text="Salta (A).", expect="A"),
                Step("wait", seconds=0.18),
                Step("expect", text="Backflip (stick abajo + salto).", expect="LS_DOWN"),
                Step("wait", seconds=0.12),
                Step("expect", text="Cancela el flip: stick ARRIBA rápido.", expect="LS_UP"),
                Step("wait", seconds=0.25),
                Step("note", "Air roll para enderezar y caer mirando atrás."),
            ],
        ),
        Guide(
            name="Speedflip",
            type="Single-Stage",
            description="Guía de práctica (timing orientativo). Ajusta a tu sensación.",
            steps=[
                Step("note", "En Freeplay: acelera recto."),
                Step("wait", seconds=0.45),
                Step("expect", text="Salto 1 (A).", expect="A"),
                Step("wait", seconds=0.07),
                Step("expect", text="Salto 2 rápido (A) + stick DIAGONAL.", expect="LS_DIAG"),
                Step("wait", seconds=0.18),
                Step("note", "Corrige el giro (stick contrario/air roll si lo usas)."),
                Step("wait", seconds=0.35),
                Step("expect", text="Sigue acelerando (RT).", expect="RT"),
            ],
        ),
        Guide(
            name="Wavedash",
            type="Single-Stage",
            description="Guía para wavedash básico.",
            steps=[
                Step("note", "Busca una caída baja (tras pequeño salto)."),
                Step("wait", seconds=0.6),
                Step("expect", text="Salta (A) y suelta rápido.", expect="A"),
                Step("wait", seconds=0.25),
                Step("expect", text="Al tocar suelo: stick ADELANTE y salto (A).", expect="LS_UP"),
                Step("wait", seconds=0.08),
                Step("expect", text="Completa el dash con el salto (A).", expect="A"),
            ],
        ),
        Guide(
            name="Stall (aerial)",
            type="Single-Stage",
            description="Guía para practicar stall (orientativo).",
            steps=[
                Step("note", "Inicia aerial (salto + boost si lo usas)."),
                Step("wait", seconds=0.8),
                Step("expect", text="Stick: IZQ o DER fuerte.", expect="LS_DIAG"),
                Step("wait", seconds=0.05),
                Step("expect", text="Pulsa salto (A) en el timing.", expect="A"),
                Step("note", "Repite ajustando timing y dirección."),
            ],
        ),
        Guide(
            name="Wall Dash Right",
            type="Single-Stage",
            description="Guía para wall dash en pared (derecha) (orientativo).",
            steps=[
                Step("note", "Sube por pared con velocidad."),
                Step("wait", seconds=0.7),
                Step("expect", text="Salto pequeño (A) pegado a pared.", expect="A"),
                Step("wait", seconds=0.12),
                Step("expect", text="Repite saltos rítmicos (A) mientras mantienes dirección.", expect="A"),
                Step("note", "Ajusta cámara/binds a tu gusto."),
            ],
        ),
        Guide(
            name="Musty Flick",
            type="Multi-Stage",
            description="Guía por etapas para practicar musty flick.",
            steps=[
                Step("note", "Stage 1: dribble estable (balón sobre el coche)."),
                Step("wait", seconds=0.8),
                Step("expect", text="Salto (A).", expect="A"),
                Step("wait", seconds=0.22),
                Step("expect", text="Levanta morro: stick ABAJO un instante.", expect="LS_DOWN"),
                Step("wait", seconds=0.35),
                Step("expect", text="Segundo salto (A) para flick.", expect="A"),
                Step("wait", seconds=0.06),
                Step("expect", text="Dirección del flick: stick ARRIBA.", expect="LS_UP"),
            ],
        ),
        Guide(
            name="Breezi Flick (2-stage)",
            type="Multi-Stage",
            description="Guía por etapas (simplificada) para practicar breezi.",
            steps=[
                Step("note", "Stage 1: dribble estable."),
                Step("wait", seconds=0.7),
                Step("expect", text="Salto (A).", expect="A"),
                Step("wait", seconds=0.25),
                Step("note", "Stage 1: rotación/air roll si lo usas (a tu estilo)."),
                Step("wait", seconds=0.55),
                Step("expect", text="Stage 2: segundo salto (A) para flick.", expect="A"),
                Step("wait", seconds=0.08),
                Step("expect", text="Stage 2: empuja stick en dirección del flick.", expect="LS_DIAG"),
            ],
        ),
    ]


# ============================
# Lectura de mando (pygame)
# ============================
class GamepadReader:
    """
    Lee mando con pygame. NO envía inputs.
    Devuelve:
      - botones pulsados (set[str])
      - ejes (lx, ly)
    """
    def __init__(self):
        self.ready = False
        self.joy: Optional[pygame.joystick.Joystick] = None
        self._lock = threading.Lock()
        self._buttons: set[str] = set()
        self._axes: Tuple[float, float] = (0.0, 0.0)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Mapping “Xbox-like” típico en Windows
        self.btn_map: Dict[str, int] = {
            "A": 0, "B": 1, "X": 2, "Y": 3,
            "LB": 4, "RB": 5,
            "BACK": 6, "START": 7,
            "LSTICK": 8, "RSTICK": 9,
        }

        # Triggers: heurística (axes) — varía por mando/driver
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

    def stop(self):
        self._stop.set()

    def snapshot(self) -> Tuple[set[str], Tuple[float, float]]:
        with self._lock:
            return set(self._buttons), self._axes

    def _loop(self):
        while not self._stop.is_set():
            pygame.event.pump()
            if not self.joy:
                time.sleep(0.03)
                continue

            buttons = set()

            # botones
            for name, idx in self.btn_map.items():
                try:
                    if self.joy.get_button(idx):
                        buttons.add(name)
                except Exception:
                    pass

            # sticks (0,1 suelen ser LS)
            try:
                lx = float(self.joy.get_axis(0))
                ly = float(self.joy.get_axis(1))
            except Exception:
                lx, ly = 0.0, 0.0

            # triggers por ejes típicos
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
                self._axes = (lx, ly)

            time.sleep(0.02)

    @staticmethod
    def match_expect(expect: str, buttons: set[str], axes: Tuple[float, float]) -> bool:
        lx, ly = axes
        # Nota: en pygame, arriba suele ser ly negativo
        if expect in buttons:
            return True
        if expect == "LS_UP":
            return ly < -0.6
        if expect == "LS_DOWN":
            return ly > 0.6
        if expect == "LS_DIAG":
            return abs(lx) > 0.55 and abs(ly) > 0.55
        return False


# ============================
# Persistencia
# ============================
def save_guides(path: str, guides: List[Guide]):
    payload = []
    for g in guides:
        payload.append({
            "name": g.name,
            "type": g.type,
            "description": g.description,
            "trigger": g.trigger,
            "enabled": g.enabled,
            "steps": [asdict(s) for s in (g.steps or [])],
        })
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def load_guides(path: str) -> List[Guide]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        out: List[Guide] = []
        for item in payload:
            steps = [Step(**s) for s in item.get("steps", [])]
            out.append(Guide(
                name=item.get("name", "Guide"),
                type=item.get("type", "Single-Stage"),
                description=item.get("description", ""),
                trigger=item.get("trigger"),
                enabled=bool(item.get("enabled", True)),
                steps=steps,
            ))
        return out
    except FileNotFoundError:
        return []
    except Exception:
        return []


# ============================
# Motor Trainer (guía + validación)
# ============================
class TrainerEngine:
    def __init__(self, gamepad: GamepadReader, status_cb: Callable[[str], None]):
        self.gamepad = gamepad
        self.status_cb = status_cb
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.tolerance = 0.35  # ventana para validar (segundos)

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self):
        self._stop.set()

    def run(self, guide: Guide):
        if self.is_running():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_blocking, args=(guide,), daemon=True)
        self._thread.start()

    def _run_blocking(self, guide: Guide):
        self.status_cb(f"▶ Iniciando: {guide.name}")
        for step in (guide.steps or []):
            if self._stop.is_set():
                self.status_cb("⏹ Stop.")
                return

            if step.type == "note":
                self.status_cb(f"ℹ {step.text or ''}")
                time.sleep(0.65)
                continue

            if step.type == "wait":
                time.sleep(float(step.seconds or 0))
                continue

            if step.type == "expect":
                # mostramos instrucción y damos una ventana para validar
                msg = step.text or "Acción"
                self.status_cb(f"👉 {msg}")
                ok = self._wait_for_expect(step.expect)
                if step.expect:
                    self.status_cb(("✅ OK" if ok else "⚠ No detectado") + f" · {step.expect}")
                time.sleep(0.18)

        self.status_cb(f"🏁 Fin: {guide.name}")

    def _wait_for_expect(self, expect: Optional[str]) -> bool:
        if not expect:
            time.sleep(self.tolerance)
            return True

        t0 = time.time()
        while time.time() - t0 < self.tolerance:
            if self._stop.is_set():
                return False
            buttons, axes = self.gamepad.snapshot()
            if GamepadReader.match_expect(expect, buttons, axes):
                return True
            time.sleep(0.01)
        return False


# ============================
# UI
# ============================
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


TRIGGERS = ["—", "A", "B", "X", "Y", "LB", "RB", "LT", "RT", "START", "BACK", "LSTICK", "RSTICK"]


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MacroDeck — Trainer (mando)")
        self.geometry("1020x620")
        self.minsize(940, 560)

        self.data_path = "macros.json"
        self.guides: List[Guide] = load_guides(self.data_path) or default_guides()

        self.gamepad = GamepadReader()
        self.gamepad.start()

        self.listening_enabled = True
        self.auto_start_listening = True

        self._last_back_press = 0.0

        self.engine = TrainerEngine(self.gamepad, self._set_status_threadsafe)

        self.selected_index: Optional[int] = None

        self._hotkey_listener = None
        self._start_keyboard_listener()

        self._build_ui()
        self._refresh_list()
        self._load_into_editor(0 if self.guides else None)

        self.after(80, self._poll_gamepad_triggers)

    # ---------- UI ----------
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Left
        left = ctk.CTkFrame(self, corner_radius=16)
        left.grid(row=0, column=0, padx=14, pady=14, sticky="nsw")
        left.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(left, text="Macros", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, padx=14, pady=(14, 8), sticky="w"
        )

        topbar = ctk.CTkFrame(left, fg_color="transparent")
        topbar.grid(row=1, column=0, padx=14, pady=(0, 10), sticky="ew")
        topbar.grid_columnconfigure((0, 1), weight=1)

        self.toggle_autostart = ctk.CTkSwitch(
            topbar, text="Auto-Start Listening", command=self._on_toggle_autostart
        )
        self.toggle_autostart.select()
        self.toggle_autostart.grid(row=0, column=0, sticky="w")

        self.badge_listen = ctk.CTkLabel(topbar, text="Listening: ON", corner_radius=8)
        self.badge_listen.grid(row=0, column=1, sticky="e")

        self.pad_status = ctk.CTkLabel(left, text="Mando: detectando…", corner_radius=8)
        self.pad_status.grid(row=2, column=0, padx=14, pady=(0, 10), sticky="ew")

        self.listbox = ctk.CTkScrollableFrame(left, width=320, corner_radius=16)
        self.listbox.grid(row=3, column=0, padx=14, pady=(0, 14), sticky="nsew")

        # Right
        right = ctk.CTkFrame(self, corner_radius=16)
        right.grid(row=0, column=1, padx=(0, 14), pady=14, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(4, weight=1)

        self.lbl_title = ctk.CTkLabel(right, text="Editor", font=ctk.CTkFont(size=18, weight="bold"))
        self.lbl_title.grid(row=0, column=0, padx=18, pady=(16, 6), sticky="w")

        form = ctk.CTkFrame(right, corner_radius=14)
        form.grid(row=1, column=0, padx=18, pady=(0, 10), sticky="ew")
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text="Nombre").grid(row=0, column=0, padx=12, pady=10, sticky="w")
        self.entry_name = ctk.CTkEntry(form, placeholder_text="Nombre")
        self.entry_name.grid(row=0, column=1, padx=12, pady=10, sticky="ew")

        ctk.CTkLabel(form, text="Tipo").grid(row=1, column=0, padx=12, pady=10, sticky="w")
        self.entry_type = ctk.CTkEntry(form)
        self.entry_type.grid(row=1, column=1, padx=12, pady=10, sticky="ew")

        ctk.CTkLabel(form, text="Trigger (mando)").grid(row=2, column=0, padx=12, pady=10, sticky="w")
        self.opt_trigger = ctk.CTkOptionMenu(form, values=TRIGGERS)
        self.opt_trigger.grid(row=2, column=1, padx=12, pady=10, sticky="w")

        self.switch_enabled = ctk.CTkSwitch(form, text="Enabled")
        self.switch_enabled.grid(row=2, column=1, padx=12, pady=10, sticky="e")

        ctk.CTkLabel(right, text="Pasos (guía):").grid(row=2, column=0, padx=18, pady=(0, 8), sticky="w")
        self.steps_frame = ctk.CTkScrollableFrame(right, corner_radius=16)
        self.steps_frame.grid(row=3, column=0, padx=18, pady=(0, 10), sticky="nsew")

        actions = ctk.CTkFrame(right, corner_radius=14)
        actions.grid(row=5, column=0, padx=18, pady=(0, 14), sticky="ew")
        actions.grid_columnconfigure((0, 1, 2), weight=1)

        self.btn_save = ctk.CTkButton(actions, text="Guardar", command=self._save_current)
        self.btn_save.grid(row=0, column=0, padx=(0, 10), pady=12, sticky="ew")

        self.btn_run = ctk.CTkButton(actions, text="Start", command=self._run_current)
        self.btn_run.grid(row=0, column=1, padx=10, pady=12, sticky="ew")

        self.btn_stop = ctk.CTkButton(actions, text="Stop", fg_color="#B23B3B", hover_color="#8E2F2F",
                                      command=self._stop_run)
        self.btn_stop.grid(row=0, column=2, padx=(10, 0), pady=12, sticky="ew")

        self.status = ctk.CTkLabel(right, text="Listo.", anchor="w")
        self.status.grid(row=6, column=0, padx=18, pady=(0, 10), sticky="ew")

        hint = ctk.CTkLabel(
            right,
            text="Tip: Doble pulsación de BACK = activar/desactivar Listening.",
            text_color="#9AA4B2",
            anchor="w",
        )
        hint.grid(row=7, column=0, padx=18, pady=(0, 12), sticky="ew")

    # ---------- List ----------
    def _refresh_list(self):
        for w in self.listbox.winfo_children():
            w.destroy()

        for idx, g in enumerate(self.guides):
            trigger = g.trigger or "—"
            enabled = "✓" if g.enabled else "✗"
            btn = ctk.CTkButton(
                self.listbox,
                text=f"{enabled}  {g.name}\nType: {g.type}   Trigger: {trigger}",
                anchor="w",
                height=58,
                command=lambda i=idx: self._load_into_editor(i),
            )
            btn.pack(fill="x", padx=10, pady=8)

    # ---------- Editor ----------
    def _load_into_editor(self, index: Optional[int]):
        self.selected_index = index
        for w in self.steps_frame.winfo_children():
            w.destroy()

        if index is None:
            self.lbl_title.configure(text="Editor")
            return

        g = self.guides[index]
        self.lbl_title.configure(text=f"Editor — {g.name}")

        self.entry_name.delete(0, "end")
        self.entry_name.insert(0, g.name)

        self.entry_type.delete(0, "end")
        self.entry_type.insert(0, g.type)

        self.opt_trigger.set(g.trigger if g.trigger in TRIGGERS else "—")
        if g.enabled:
            self.switch_enabled.select()
        else:
            self.switch_enabled.deselect()

        ctk.CTkLabel(self.steps_frame, text=g.description, justify="left", wraplength=620).pack(
            fill="x", padx=12, pady=(10, 8)
        )

        for s in (g.steps or []):
            if s.type == "wait":
                line = f"⏱ wait {s.seconds:.2f}s"
            elif s.type == "expect":
                line = f"👉 {s.text}  ·  expect: {s.expect}"
            else:
                line = f"ℹ {s.text}"
            ctk.CTkLabel(self.steps_frame, text=line, anchor="w", justify="left", wraplength=620).pack(
                fill="x", padx=12, pady=6
            )

    def _save_current(self):
        g = self._get_current()
        if not g:
            return
        g.name = self.entry_name.get().strip() or g.name
        g.type = self.entry_type.get().strip() or g.type

        trig = self.opt_trigger.get()
        g.trigger = None if trig == "—" else trig

        g.enabled = bool(self.switch_enabled.get())

        save_guides(self.data_path, self.guides)
        self._refresh_list()
        self._set_status("Guardado en macros.json")

    # ---------- Run ----------
    def _run_current(self):
        g = self._get_current()
        if not g:
            return
        if self.engine.is_running():
            self._set_status("Ya hay una guía corriendo.")
            return
        self.engine.run(g)

    def _stop_run(self):
        self.engine.stop()
        self._set_status("Stop enviado.")

    def _get_current(self) -> Optional[Guide]:
        if self.selected_index is None:
            return None
        if self.selected_index < 0 or self.selected_index >= len(self.guides):
            return None
        return self.guides[self.selected_index]

    # ---------- Listening / triggers ----------
    def _on_toggle_autostart(self):
        self.auto_start_listening = bool(self.toggle_autostart.get())

    def _poll_gamepad_triggers(self):
        # Estado mando
        if self.gamepad.ready:
            buttons, _axes = self.gamepad.snapshot()
            self.pad_status.configure(text=f"Mando: OK · Botones: {', '.join(sorted(buttons)) or '—'}")
        else:
            self.pad_status.configure(text="Mando: NO detectado (conéctalo y reinicia)")

        # Master toggle: doble BACK
        if self.gamepad.ready:
            buttons, _ = self.gamepad.snapshot()
            now = time.time()
            if "BACK" in buttons:
                # debounce simple
                if now - self._last_back_press > 0.25:
                    # si fue "rápido" -> doble pulsación
                    if now - self._last_back_press < 0.60:
                        self.listening_enabled = not self.listening_enabled
                        self.badge_listen.configure(text=f"Listening: {'ON' if self.listening_enabled else 'OFF'}")
                        self._set_status(f"Listening {'activado' if self.listening_enabled else 'desactivado'}")
                    self._last_back_press = now

            # Auto-start guides por trigger
            if self.auto_start_listening and self.listening_enabled and not self.engine.is_running():
                for g in self.guides:
                    if g.enabled and g.trigger and g.trigger in buttons:
                        self.engine.run(g)
                        break

        self.after(80, self._poll_gamepad_triggers)

    # ---------- Keyboard (opcional) ----------
    def _start_keyboard_listener(self):
        # Te permite, si quieres, usar teclas del PC para Start/Stop de la app (no del juego)
        def on_press(key):
            try:
                if key == keyboard.Key.f8:
                    # toggle listening
                    self.listening_enabled = not self.listening_enabled
                    self.badge_listen.configure(text=f"Listening: {'ON' if self.listening_enabled else 'OFF'}")
                    self._set_status(f"Listening {'activado' if self.listening_enabled else 'desactivado'}")
                if key == keyboard.Key.f9:
                    self._run_current()
                if key == keyboard.Key.f10:
                    self._stop_run()
            except Exception:
                pass

        self._hotkey_listener = keyboard.Listener(on_press=on_press)
        self._hotkey_listener.daemon = True
        self._hotkey_listener.start()

    # ---------- Status helpers ----------
    def _set_status(self, msg: str):
        self.status.configure(text=msg)

    def _set_status_threadsafe(self, msg: str):
        self.after(0, lambda: self._set_status(msg))


if __name__ == "__main__":
    app = App()
    app.mainloop()
