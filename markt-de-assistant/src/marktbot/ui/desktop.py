"""Desktop-Steuerung (Tkinter).

Bewusst Tkinter und nicht Qt: Tkinter liegt jeder Python-Installation bei.
Dieses Fenster ist damit das Einzige, was schon VOR "pip install" startet -
und genau das braucht man, wenn die Einrichtung selbst ueber die Oberflaeche
laufen soll.

Der Bot laeuft als eigener Prozess, nicht im selben Interpreter. Das kostet
etwas Umstand bei der Ausgabe (Thread + Queue), hat aber zwei Vorteile, die
das mehr als aufwiegen: ein Absturz des Bots nimmt die Oberflaeche nicht mit,
und "Stoppen" ist ein sauberes Prozessende statt eines halb abgeraeumten
Event-Loops.

Die eigentliche Arbeit - Entwuerfe lesen, freigeben, Anzeigen verwalten -
passiert im Web-Dashboard. Dieses Fenster ist Schaltzentrale und Einrichtung.
"""

from __future__ import annotations

import os
import queue
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from .envfile import read_env, write_env

# --------------------------------------------------------------------------
# Farben - abgestimmt auf das Web-Dashboard
# --------------------------------------------------------------------------

BG = "#0f1115"
SURFACE = "#171a21"
SURFACE_2 = "#1e222b"
BORDER = "#2a2f3a"
TEXT = "#e6e8ee"
MUTED = "#8b93a3"
ACCENT = "#4f8cff"
OK = "#3fb27f"
WARN = "#e0a33e"
DANGER = "#e05c5c"

FONT = ("Segoe UI", 10) if sys.platform == "win32" else ("DejaVu Sans", 10)
FONT_BOLD = (FONT[0], 10, "bold")
FONT_TITLE = (FONT[0], 15, "bold")
FONT_SMALL = (FONT[0], 9)
FONT_MONO = ("Consolas", 9) if sys.platform == "win32" else ("DejaVu Sans Mono", 9)

ENV_FIELDS = [
    ("MARKT_USERNAME", "markt.de E-Mail", False),
    ("MARKT_PASSWORD", "markt.de Passwort", True),
    ("TELEGRAM_BOT_TOKEN", "Telegram Bot-Token", True),
    ("TELEGRAM_CHAT_ID", "Telegram Chat-ID", False),
    ("PROXY_SERVER", "Proxy-Server (optional)", False),
    ("PROXY_USERNAME", "Proxy-Benutzer (optional)", False),
    ("PROXY_PASSWORD", "Proxy-Passwort (optional)", True),
]


# --------------------------------------------------------------------------


class ControlCenter:
    def __init__(self, root: Path) -> None:
        self.root_dir = root
        self.env_path = root / ".env"
        self.process: subprocess.Popen[str] | None = None
        self.output: queue.Queue[str] = queue.Queue()

        self.window = Tk()
        self.window.title("markt.de Assistent")
        self.window.geometry("880x640")
        self.window.minsize(760, 560)
        self.window.configure(bg=BG)

        self.mode = StringVar(value="freigabe")
        self.dry_run = BooleanVar(value=False)
        self.env_vars: dict[str, StringVar] = {}

        self._build_style()
        self._build_layout()
        self._load_env_into_form()
        self.refresh_checks()

        self.window.after(120, self._drain_output)
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # Aussehen
    # ------------------------------------------------------------------

    def _build_style(self) -> None:
        style = ttk.Style(self.window)
        # 'clam' ist das einzige mitgelieferte Theme, das sich durchgehend
        # umfaerben laesst - die nativen Themes ignorieren viele Optionen.
        style.theme_use("clam")

        style.configure(".", background=BG, foreground=TEXT, font=FONT)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=SURFACE, relief="flat")
        style.configure("TLabel", background=BG, foreground=TEXT, font=FONT)
        style.configure("Card.TLabel", background=SURFACE, foreground=TEXT)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=FONT_SMALL)
        style.configure("CardMuted.TLabel", background=SURFACE, foreground=MUTED, font=FONT_SMALL)
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=FONT_TITLE)
        style.configure("Heading.TLabel", background=BG, foreground=TEXT, font=FONT_BOLD)

        style.configure(
            "TButton",
            background=SURFACE_2, foreground=TEXT,
            borderwidth=0, focuscolor=SURFACE_2, padding=(14, 8), font=FONT,
        )
        style.map("TButton", background=[("active", BORDER), ("disabled", SURFACE)],
                  foreground=[("disabled", MUTED)])

        style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff",
                        padding=(18, 10), font=FONT_BOLD)
        style.map("Accent.TButton", background=[("active", "#3d76e0"), ("disabled", BORDER)],
                  foreground=[("disabled", MUTED)])

        style.configure("Danger.TButton", background=DANGER, foreground="#ffffff",
                        padding=(18, 10), font=FONT_BOLD)
        style.map("Danger.TButton", background=[("active", "#c94d4d")])

        style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 8, 0, 0))
        style.configure("TNotebook.Tab", background=BG, foreground=MUTED,
                        padding=(18, 10), borderwidth=0, font=FONT)
        style.map("TNotebook.Tab", background=[("selected", BG)],
                  foreground=[("selected", TEXT)])

        style.configure("TEntry", fieldbackground=SURFACE_2, foreground=TEXT,
                        bordercolor=BORDER, insertcolor=TEXT, padding=6)
        style.configure("TRadiobutton", background=BG, foreground=TEXT, font=FONT)
        style.map("TRadiobutton", background=[("active", BG)])
        style.configure("TCheckbutton", background=BG, foreground=TEXT, font=FONT)
        style.map("TCheckbutton", background=[("active", BG)])
        style.configure("TSeparator", background=BORDER)

    def _card(self, parent: ttk.Frame) -> ttk.Frame:
        frame = ttk.Frame(parent, style="Card.TFrame", padding=16)
        return frame

    # ------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        header = ttk.Frame(self.window, padding=(24, 18, 24, 12))
        header.pack(fill="x")

        left = ttk.Frame(header)
        left.pack(side="left")
        ttk.Label(left, text="markt.de Assistent", style="Title.TLabel").pack(anchor="w")
        self.subtitle = ttk.Label(left, text="Bereit", style="Muted.TLabel")
        self.subtitle.pack(anchor="w")

        self.state_label = ttk.Label(header, text="● Gestoppt", style="Heading.TLabel")
        self.state_label.configure(foreground=MUTED)
        self.state_label.pack(side="right")

        ttk.Separator(self.window, orient="horizontal").pack(fill="x", padx=24)

        notebook = ttk.Notebook(self.window)
        notebook.pack(fill="both", expand=True, padx=16, pady=(8, 0))

        self.tab_overview = ttk.Frame(notebook, padding=16)
        self.tab_setup = ttk.Frame(notebook, padding=16)
        self.tab_log = ttk.Frame(notebook, padding=16)
        notebook.add(self.tab_overview, text="  Übersicht  ")
        notebook.add(self.tab_setup, text="  Einrichtung  ")
        notebook.add(self.tab_log, text="  Protokoll  ")

        self._build_overview()
        self._build_setup()
        self._build_log()

        self.status_bar = ttk.Label(
            self.window, text=f"Ordner: {self.root_dir}", style="Muted.TLabel",
            padding=(24, 8),
        )
        self.status_bar.pack(fill="x")

    # -- Übersicht ------------------------------------------------------

    def _build_overview(self) -> None:
        checks = self._card(self.tab_overview)
        checks.pack(fill="x")
        ttk.Label(checks, text="Systemcheck", style="Card.TLabel",
                  font=FONT_BOLD).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))

        self.check_labels: dict[str, ttk.Label] = {}
        for index, (key, title) in enumerate([
            ("deps", "Pakete"), ("browser", "Browser"),
            ("config", "Konfiguration"), ("profile", "Anmeldung"),
        ]):
            column = ttk.Frame(checks, style="Card.TFrame")
            column.grid(row=1, column=index, sticky="w", padx=(0, 28))
            ttk.Label(column, text=title, style="CardMuted.TLabel").pack(anchor="w")
            label = ttk.Label(column, text="prüfe …", style="Card.TLabel", font=FONT_BOLD)
            label.pack(anchor="w")
            self.check_labels[key] = label

        ttk.Button(checks, text="Neu prüfen", command=self.refresh_checks).grid(
            row=1, column=4, sticky="e"
        )
        checks.columnconfigure(4, weight=1)

        # --- Betriebsart ---
        mode_card = self._card(self.tab_overview)
        mode_card.pack(fill="x", pady=(14, 0))
        ttk.Label(mode_card, text="Betriebsart", style="Card.TLabel",
                  font=FONT_BOLD).pack(anchor="w", pady=(0, 10))

        for value, title, subtitle in [
            ("freigabe", "Freigabe-Modus",
             "KI erzeugt Entwürfe, du gibst jeden per Telegram frei"),
            ("assistent", "Assistenzmodus",
             "Antwortet selbstständig und weist sich als Programm aus"),
        ]:
            row = ttk.Frame(mode_card, style="Card.TFrame")
            row.pack(fill="x", pady=3)
            ttk.Radiobutton(
                row, text=title, value=value, variable=self.mode,
                command=self.refresh_checks, style="TRadiobutton",
            ).pack(anchor="w")
            ttk.Label(row, text=f"      {subtitle}", style="CardMuted.TLabel").pack(anchor="w")

        ttk.Checkbutton(
            mode_card, variable=self.dry_run,
            text="Trockenlauf – alles läuft, aber nichts wird an markt.de gesendet",
        ).pack(anchor="w", pady=(12, 0))

        # --- Steuerung ---
        controls = ttk.Frame(self.tab_overview)
        controls.pack(fill="x", pady=(18, 0))

        self.start_button = ttk.Button(
            controls, text="▶  Starten", style="Accent.TButton", command=self.toggle_bot
        )
        self.start_button.pack(side="left")

        self.dashboard_button = ttk.Button(
            controls, text="Dashboard öffnen", command=self.open_dashboard, state="disabled"
        )
        self.dashboard_button.pack(side="left", padx=8)

        ttk.Button(controls, text="Ordner öffnen", command=self.open_folder).pack(side="left")

    # -- Einrichtung ----------------------------------------------------

    def _build_setup(self) -> None:
        creds = self._card(self.tab_setup)
        creds.pack(fill="x")
        ttk.Label(creds, text="Zugangsdaten", style="Card.TLabel",
                  font=FONT_BOLD).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            creds,
            text="Wird in .env gespeichert – bleibt auf diesem Rechner und wird nie mit übertragen.",
            style="CardMuted.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 12))

        for index, (key, label, secret) in enumerate(ENV_FIELDS, start=2):
            ttk.Label(creds, text=label, style="Card.TLabel").grid(
                row=index, column=0, sticky="w", pady=4, padx=(0, 14)
            )
            variable = StringVar()
            self.env_vars[key] = variable
            entry = ttk.Entry(creds, textvariable=variable, width=48,
                              show="•" if secret else "")
            entry.grid(row=index, column=1, sticky="ew", pady=4)
        creds.columnconfigure(1, weight=1)

        ttk.Button(creds, text="Speichern", style="Accent.TButton",
                   command=self.save_env).grid(
            row=len(ENV_FIELDS) + 2, column=1, sticky="e", pady=(14, 0)
        )

        # --- Einrichtungsschritte ---
        steps = self._card(self.tab_setup)
        steps.pack(fill="x", pady=(14, 0))
        ttk.Label(steps, text="Einrichtung", style="Card.TLabel",
                  font=FONT_BOLD).pack(anchor="w", pady=(0, 10))

        for text, description, command in [
            ("Pakete installieren", "Einmalig, dauert einige Minuten",
             self.install_dependencies),
            ("Browser installieren", "Chromium für Playwright", self.install_browser),
            ("Bei markt.de anmelden", "Öffnet ein Fenster – Captcha hier von Hand lösen",
             self.run_login),
            ("Selektoren prüfen", "Zeigt, ob der Bot die Seite noch versteht",
             self.run_doctor),
            ("KI testen", "Erzeugt eine Beispielantwort, ohne den Browser zu starten",
             self.run_ai_test),
        ]:
            row = ttk.Frame(steps, style="Card.TFrame")
            row.pack(fill="x", pady=4)
            ttk.Button(row, text=text, command=command, width=24).pack(side="left")
            ttk.Label(row, text=description, style="CardMuted.TLabel").pack(
                side="left", padx=12
            )

    # -- Protokoll ------------------------------------------------------

    def _build_log(self) -> None:
        top = ttk.Frame(self.tab_log)
        top.pack(fill="x", pady=(0, 8))
        ttk.Label(top, text="Ausgabe", style="Heading.TLabel").pack(side="left")
        ttk.Button(top, text="Leeren", command=self.clear_log).pack(side="right")

        self.log_view = ScrolledText(
            self.tab_log, bg=SURFACE, fg=TEXT, insertbackground=TEXT,
            font=FONT_MONO, relief="flat", borderwidth=0, wrap="word", padx=12, pady=10,
        )
        self.log_view.pack(fill="both", expand=True)
        self.log_view.configure(state="disabled")

        for tag, color in [
            ("info", TEXT), ("muted", MUTED), ("ok", OK),
            ("warn", WARN), ("error", DANGER),
        ]:
            self.log_view.tag_configure(tag, foreground=color)

    # ------------------------------------------------------------------
    # Protokollausgabe
    # ------------------------------------------------------------------

    def log(self, text: str, tag: str = "info") -> None:
        self.log_view.configure(state="normal")
        self.log_view.insert("end", text.rstrip() + "\n", tag)
        self.log_view.see("end")
        self.log_view.configure(state="disabled")

    def clear_log(self) -> None:
        self.log_view.configure(state="normal")
        self.log_view.delete("1.0", "end")
        self.log_view.configure(state="disabled")

    def _drain_output(self) -> None:
        """Ausgabe der Unterprozesse in die Oberflaeche holen.

        Laeuft im Tk-Thread; die Leser-Threads schieben nur in die Queue.
        Tk-Widgets aus einem fremden Thread anzufassen ist der klassische Weg
        in sporadische Abstuerze.
        """
        try:
            while True:
                line = self.output.get_nowait()
                lowered = line.lower()
                if "error" in lowered or "fehlgeschlagen" in lowered or "❌" in line:
                    tag = "error"
                elif "warn" in lowered or "⚠" in line:
                    tag = "warn"
                elif "✅" in line or "bereit" in lowered:
                    tag = "ok"
                elif line.startswith(" ") or "debug" in lowered:
                    tag = "muted"
                else:
                    tag = "info"
                self.log(line, tag)
        except queue.Empty:
            pass

        if self.process is not None and self.process.poll() is not None:
            code = self.process.returncode
            self.process = None
            self._set_running(False)
            if code:
                self.log(f"Prozess beendet mit Code {code}.", "error")
            else:
                self.log("Prozess beendet.", "muted")

        self.window.after(120, self._drain_output)

    # ------------------------------------------------------------------
    # Prozesse
    # ------------------------------------------------------------------

    def _python(self) -> str:
        """Interpreter aus der virtuellen Umgebung, sonst der laufende."""
        candidates = [
            self.root_dir / ".venv" / "Scripts" / "python.exe",
            self.root_dir / ".venv" / "bin" / "python",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return sys.executable

    def _spawn(self, args: list[str], label: str, track: bool = False) -> None:
        if track and self.process is not None:
            messagebox.showinfo("Läuft bereits", "Der Bot läuft schon.")
            return

        command = [self._python(), "-u", "run.py", *args]
        self.log(f"→ {' '.join(command[1:])}", "muted")

        try:
            process = subprocess.Popen(
                command,
                cwd=self.root_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                creationflags=(
                    subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                ),
            )
        except OSError as exc:
            self.log(f"{label} konnte nicht gestartet werden: {exc}", "error")
            return

        if track:
            self.process = process
            self._set_running(True)

        threading.Thread(
            target=self._read_stream, args=(process,), daemon=True
        ).start()

    def _read_stream(self, process: subprocess.Popen[str]) -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            self.output.put(line)

    def _run_tool(self, args: list[str], label: str) -> None:
        """Kurzlaeufer wie doctor oder ai-test."""
        self.log(f"— {label} —", "ok")
        self._spawn(args, label, track=False)

    def _run_shell(self, command: list[str], label: str) -> None:
        """Fuer pip und playwright, die nicht ueber run.py laufen."""
        self.log(f"— {label} —", "ok")
        self.log(f"→ {' '.join(command)}", "muted")

        def worker() -> None:
            try:
                process = subprocess.Popen(
                    command, cwd=self.root_dir,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                    creationflags=(
                        subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                    ),
                )
            except OSError as exc:
                self.output.put(f"Fehlgeschlagen: {exc}")
                return
            if process.stdout is not None:
                for line in process.stdout:
                    self.output.put(line)
            process.wait()
            self.output.put(
                f"✅ {label} fertig." if process.returncode == 0
                else f"❌ {label} fehlgeschlagen (Code {process.returncode})."
            )
            self.window.after(0, self.refresh_checks)

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Aktionen
    # ------------------------------------------------------------------

    def toggle_bot(self) -> None:
        if self.process is not None:
            self.stop_bot()
        else:
            self.start_bot()

    def start_bot(self) -> None:
        config = self._config_for_mode()
        if config is None:
            return

        args: list[str] = []
        if self.mode.get() == "assistent":
            args.append("assistant")
        if self.dry_run.get():
            args.append("--dry-run")

        self.clear_log()
        self.log("Starte …", "ok")
        if self.dry_run.get():
            self.log("TROCKENLAUF – es wird nichts an markt.de gesendet.", "warn")
        self._spawn(args, "Bot", track=True)

    def stop_bot(self) -> None:
        if self.process is None:
            return
        self.log("Beende …", "muted")
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.log("Reagiert nicht, erzwinge das Ende.", "warn")
            self.process.kill()

    def _set_running(self, running: bool) -> None:
        if running:
            self.state_label.configure(text="● Läuft", foreground=OK)
            self.start_button.configure(text="■  Stoppen", style="Danger.TButton")
            self.dashboard_button.configure(state="normal")
            self.subtitle.configure(
                text="Trockenlauf" if self.dry_run.get() else "Im Betrieb"
            )
        else:
            self.state_label.configure(text="● Gestoppt", foreground=MUTED)
            self.start_button.configure(text="▶  Starten", style="Accent.TButton")
            self.dashboard_button.configure(state="disabled")
            self.subtitle.configure(text="Bereit")

    def open_dashboard(self) -> None:
        webbrowser.open("http://127.0.0.1:8765")

    def open_folder(self) -> None:
        if sys.platform == "win32":
            os.startfile(self.root_dir)  # noqa: S606 - genau dafuer gedacht
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(self.root_dir)])
        else:
            subprocess.Popen(["xdg-open", str(self.root_dir)])

    def install_dependencies(self) -> None:
        self._run_shell(
            [self._python(), "-m", "pip", "install", "-r", "requirements.txt"],
            "Pakete installieren",
        )

    def install_browser(self) -> None:
        self._run_shell(
            [self._python(), "-m", "playwright", "install", "chromium"],
            "Browser installieren",
        )

    def run_login(self) -> None:
        if self._config_for_mode() is None:
            return
        self._run_tool(["login"], "Anmeldung")

    def run_doctor(self) -> None:
        if self._config_for_mode() is None:
            return
        self._run_tool(["doctor"], "Selektor-Check")

    def run_ai_test(self) -> None:
        if self._config_for_mode() is None:
            return
        args = ["ai-test"]
        if self.mode.get() == "assistent":
            args = ["-c", "config.assistant.yaml", "ai-test"]
        self._run_tool(args, "KI-Test")

    # ------------------------------------------------------------------
    # Konfiguration
    # ------------------------------------------------------------------

    def _config_for_mode(self) -> Path | None:
        """Passende Konfigurationsdatei sicherstellen, notfalls anlegen."""
        if self.mode.get() == "assistent":
            target, example = "config.assistant.yaml", "config.assistant.example.yaml"
        else:
            target, example = "config.yaml", "config.example.yaml"

        path = self.root_dir / target
        if path.exists():
            return path

        source = self.root_dir / example
        if not source.exists():
            messagebox.showerror(
                "Vorlage fehlt",
                f"Weder {target} noch {example} gefunden.\n"
                "Ist der Ordner vollständig entpackt?",
            )
            return None

        if not messagebox.askyesno(
            "Konfiguration anlegen",
            f"{target} gibt es noch nicht.\n\nJetzt aus {example} erstellen?",
        ):
            return None

        shutil.copy(source, path)
        self.log(f"{target} aus der Vorlage angelegt.", "ok")
        if self.mode.get() == "assistent":
            messagebox.showinfo(
                "Noch ein Schritt",
                f"{target} wurde angelegt.\n\n"
                "Der Assistenzmodus antwortet ohne Rückfrage. Trag darin unter "
                "'assistant.identification' ein, wie sich der Assistent vorstellt – "
                "ohne diese Zeile startet er nicht.",
            )
        self.refresh_checks()
        return path

    def _load_env_into_form(self) -> None:
        if not self.env_path.exists():
            example = self.root_dir / ".env.example"
            if example.exists():
                shutil.copy(example, self.env_path)
                self.log(".env aus der Vorlage angelegt.", "ok")
        values = read_env(self.env_path)
        for key, variable in self.env_vars.items():
            variable.set(values.get(key, ""))

    def save_env(self) -> None:
        updates = {key: variable.get().strip() for key, variable in self.env_vars.items()}

        chat_id = updates.get("TELEGRAM_CHAT_ID", "")
        if chat_id and not chat_id.lstrip("-").isdigit():
            messagebox.showerror(
                "Ungültige Chat-ID",
                "Die Telegram Chat-ID ist eine Zahl, z. B. 123456789.\n"
                "Bekommst du z. B. über @userinfobot.",
            )
            return

        try:
            write_env(self.env_path, updates)
        except OSError as exc:
            messagebox.showerror("Nicht gespeichert", str(exc))
            return

        self.log("Zugangsdaten in .env gespeichert.", "ok")
        messagebox.showinfo("Gespeichert", "Die Zugangsdaten wurden übernommen.")
        self.refresh_checks()

    # ------------------------------------------------------------------
    # Systemcheck
    # ------------------------------------------------------------------

    def refresh_checks(self) -> None:
        def mark(key: str, ok: bool, text_ok: str, text_bad: str) -> None:
            label = self.check_labels[key]
            label.configure(text=text_ok if ok else text_bad,
                            foreground=OK if ok else WARN)

        venv_exists = any(
            (self.root_dir / ".venv" / sub).exists() for sub in ("Scripts", "bin")
        )
        deps_ok = venv_exists and self._module_available("playwright")
        mark("deps", deps_ok, "installiert", "fehlen")

        browser_ok = self._browser_present()
        mark("browser", browser_ok, "bereit", "fehlt")

        config_name = (
            "config.assistant.yaml" if self.mode.get() == "assistent" else "config.yaml"
        )
        config_ok = (self.root_dir / config_name).exists()
        mark("config", config_ok, config_name, "fehlt noch")

        profile = self.root_dir / "profiles" / "default"
        profile_ok = profile.exists() and any(profile.iterdir())
        mark("profile", profile_ok, "Profil vorhanden", "noch nie angemeldet")

    def _module_available(self, name: str) -> bool:
        try:
            result = subprocess.run(
                [self._python(), "-c", f"import {name}"],
                cwd=self.root_dir, capture_output=True, timeout=20,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                ),
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _browser_present(self) -> bool:
        if os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"):
            return True
        if sys.platform == "win32":
            cache = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
        elif sys.platform == "darwin":
            cache = Path.home() / "Library" / "Caches" / "ms-playwright"
        else:
            cache = Path.home() / ".cache" / "ms-playwright"
        if cache.exists() and any(cache.glob("chromium*")):
            return True
        return bool(shutil.which("chromium") or shutil.which("chromium-browser"))

    # ------------------------------------------------------------------

    def _on_close(self) -> None:
        if self.process is not None:
            if not messagebox.askyesno(
                "Beenden?",
                "Der Bot läuft noch. Fenster schließen und Bot beenden?",
            ):
                return
            self.stop_bot()
        self.window.destroy()

    def run(self) -> None:
        self.window.mainloop()


def main(root: Path | None = None) -> int:
    root = root or Path(__file__).resolve().parents[3]
    ControlCenter(root).run()
    return 0
