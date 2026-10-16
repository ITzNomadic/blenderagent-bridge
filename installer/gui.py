"""Modern, intuitive graphical user interface for BlenderAgent Bridge One-Click Installer."""

from __future__ import annotations

import ctypes
import os
import pathlib
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

# Ensure repository root / frozen bundle directory is in sys.path
if getattr(sys, "frozen", False):
    bundle_dir = pathlib.Path(sys._MEIPASS).resolve()
    if str(bundle_dir) not in sys.path:
        sys.path.insert(0, str(bundle_dir))
else:
    repo_root = pathlib.Path(__file__).parent.parent.resolve()
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

try:
    from installer.constants import (
        APP_NAME,
        DEFAULT_PORT,
        DEFAULT_WORKSPACE_DIR,
        VERSION,
    )
    from installer.detector import BlenderInstallation, SystemDetectionResult, detect_system_state
    from installer.orchestrator import InstallationOrchestrator, InstallOptions, StepProgress
    from installer.i18n import detect_system_language, get_text
except ImportError:
    from .constants import (
        APP_NAME,
        DEFAULT_PORT,
        DEFAULT_WORKSPACE_DIR,
        VERSION,
    )
    from .detector import BlenderInstallation, SystemDetectionResult, detect_system_state
    from .orchestrator import InstallationOrchestrator, InstallOptions, StepProgress
    from .i18n import detect_system_language, get_text


# Enable High-DPI awareness on Windows 10/11
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class ModernTheme:
    """Design system and color tokens for modern desktop appearance."""
    BG = "#0f172a"          # Slate 900
    SURFACE = "#1e293b"     # Slate 800
    SURFACE_HOVER = "#334155" # Slate 700
    BORDER = "#334155"
    TEXT_MAIN = "#f8fafc"   # Slate 50
    TEXT_MUTED = "#94a3b8"  # Slate 400
    PRIMARY = "#3b82f6"     # Blue 500
    PRIMARY_HOVER = "#2563eb"
    SUCCESS = "#10b981"     # Emerald 500
    WARNING = "#f59e0b"     # Amber 500
    ERROR = "#ef4444"       # Red 500
    ACCENT = "#8b5cf6"      # Violet 500


class InstallerGUI:
    """Main Application Controller managing the 4 distinct screens."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.lang = detect_system_language()
        self.active_screen = "welcome"

        self.root.title(self.t("app_title", app_name=APP_NAME, version=VERSION))
        self.root.geometry("780x640")
        self.root.minsize(740, 580)
        self.root.configure(bg=ModernTheme.BG)

        self.detection: SystemDetectionResult = detect_system_state()
        self.orchestrator = InstallationOrchestrator()

        # Selected state
        self.selected_blender: Optional[BlenderInstallation] = self.detection.recommended_blender
        self.var_antigravity = tk.BooleanVar(value=self.detection.antigravity.installed)
        self.var_codex = tk.BooleanVar(value=self.detection.codex.installed)
        self.var_workspace = tk.StringVar(value=str(DEFAULT_WORKSPACE_DIR))
        self.var_port = tk.IntVar(value=DEFAULT_PORT)

        # Container for screens
        self.container = tk.Frame(self.root, bg=ModernTheme.BG)
        self.container.pack(fill="both", expand=True, padx=24, pady=24)

        # Active screen holder
        self.current_frame: Optional[tk.Frame] = None

        # Build initial screen
        self.show_screen_welcome()

    def t(self, key: str, **kwargs) -> str:
        """Helper to get translated string for current active language."""
        return get_text(key, self.lang, **kwargs)

    def toggle_language(self):
        """Toggle UI between English and Spanish and re-render current screen."""
        self.lang = "es" if self.lang == "en" else "en"
        self.root.title(self.t("app_title", app_name=APP_NAME, version=VERSION))
        if self.active_screen == "welcome":
            self.show_screen_welcome()
        elif self.active_screen == "review":
            self.show_screen_review()
        elif self.active_screen == "dashboard":
            self.show_screen_dashboard()

    def clear_screen(self):
        if self.current_frame:
            self.current_frame.destroy()
            self.current_frame = None

    def _render_top_header(self, parent: tk.Frame, title_text: str = APP_NAME, show_badge: bool = True):
        """Standardized top bar with title, Beta/Experimental badge, and Language toggle."""
        top_bar = tk.Frame(parent, bg=ModernTheme.BG)
        top_bar.pack(fill="x", pady=(0, 4))

        title_frame = tk.Frame(top_bar, bg=ModernTheme.BG)
        title_frame.pack(side="left", anchor="w")

        header = tk.Label(
            title_frame,
            text=title_text,
            font=("Segoe UI", 18, "bold"),
            fg=ModernTheme.TEXT_MAIN,
            bg=ModernTheme.BG,
        )
        header.pack(side="left")

        if show_badge:
            beta_badge = tk.Label(
                title_frame,
                text=f" {self.t('beta_badge')} ",
                font=("Segoe UI", 8, "bold"),
                fg=ModernTheme.WARNING,
                bg=ModernTheme.SURFACE,
                bd=1,
                relief="solid",
            )
            beta_badge.pack(side="left", padx=(10, 0), pady=(4, 0))

        lang_label = "🌐 Language: English" if self.lang == "en" else "🌐 Idioma: Español"
        lang_btn = tk.Button(
            top_bar,
            text=lang_label,
            font=("Segoe UI", 9),
            fg=ModernTheme.TEXT_MAIN,
            bg=ModernTheme.SURFACE,
            activebackground=ModernTheme.SURFACE_HOVER,
            activeforeground=ModernTheme.TEXT_MAIN,
            bd=1,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self.toggle_language,
        )
        lang_btn.pack(side="right", anchor="e")

    # =========================================================================
    # SCREEN A: WELCOME / DETECT
    # =========================================================================
    def show_screen_welcome(self):
        self.active_screen = "welcome"
        self.clear_screen()
        frame = tk.Frame(self.container, bg=ModernTheme.BG)
        frame.pack(fill="both", expand=True)
        self.current_frame = frame

        # Header with Beta badge and Language switch
        self._render_top_header(frame, title_text=APP_NAME, show_badge=True)

        sub = tk.Label(
            frame,
            text=self.t("subtitle"),
            font=("Segoe UI", 10),
            fg=ModernTheme.TEXT_MUTED,
            bg=ModernTheme.BG,
        )
        sub.pack(anchor="w", pady=(0, 16))

        # 1. Blender Card
        b_card = tk.LabelFrame(
            frame,
            text=self.t("blender_card_title"),
            font=("Segoe UI", 10, "bold"),
            fg=ModernTheme.TEXT_MAIN,
            bg=ModernTheme.SURFACE,
            bd=1,
            relief="solid",
        )
        b_card.pack(fill="x", pady=8, ipady=8, padx=2)

        if self.detection.blender_installations:
            b_text = self.t("blender_detected", display_name=self.detection.recommended_blender.display_name)
            b_color = ModernTheme.SUCCESS
        else:
            b_text = self.t("blender_not_found")
            b_color = ModernTheme.ERROR

        b_lbl = tk.Label(
            b_card,
            text=b_text,
            font=("Segoe UI", 9),
            fg=b_color,
            bg=ModernTheme.SURFACE,
            wraplength=640,
            justify="left",
        )
        b_lbl.pack(anchor="w", padx=16, pady=4)

        # 2. AI Clients Card
        ai_card = tk.LabelFrame(
            frame,
            text=self.t("ai_card_title"),
            font=("Segoe UI", 10, "bold"),
            fg=ModernTheme.TEXT_MAIN,
            bg=ModernTheme.SURFACE,
            bd=1,
            relief="solid",
        )
        ai_card.pack(fill="x", pady=8, ipady=8, padx=2)

        # Antigravity Checkbox
        ag_status = self.t("status_detected") if self.detection.antigravity.installed else self.t("status_not_detected")
        if self.detection.antigravity.is_configured:
            ag_status += self.t("status_configured")
        ag_cb = tk.Checkbutton(
            ai_card,
            text=self.t("antigravity_label", status=ag_status),
            variable=self.var_antigravity,
            font=("Segoe UI", 9),
            fg=ModernTheme.TEXT_MAIN,
            bg=ModernTheme.SURFACE,
            selectcolor=ModernTheme.BG,
            activebackground=ModernTheme.SURFACE,
            activeforeground=ModernTheme.TEXT_MAIN,
        )
        ag_cb.pack(anchor="w", padx=16, pady=2)

        # Codex Checkbox
        codex_status = self.t("status_detected") if self.detection.codex.installed else self.t("status_not_detected")
        if self.detection.codex.is_configured:
            codex_status += self.t("status_configured")
        codex_cb = tk.Checkbutton(
            ai_card,
            text=self.t("codex_label", status=codex_status),
            variable=self.var_codex,
            font=("Segoe UI", 9),
            fg=ModernTheme.TEXT_MAIN,
            bg=ModernTheme.SURFACE,
            selectcolor=ModernTheme.BG,
            activebackground=ModernTheme.SURFACE,
            activeforeground=ModernTheme.TEXT_MAIN,
        )
        codex_cb.pack(anchor="w", padx=16, pady=2)

        # Advanced Settings Accordion / Button
        adv_btn = tk.Button(
            frame,
            text=self.t("adv_settings_btn"),
            font=("Segoe UI", 9),
            fg=ModernTheme.TEXT_MUTED,
            bg=ModernTheme.BG,
            bd=0,
            cursor="hand2",
            command=self._toggle_advanced_settings,
        )
        adv_btn.pack(anchor="w", pady=(8, 0))

        # Bottom Bar Buttons
        btn_bar = tk.Frame(frame, bg=ModernTheme.BG)
        btn_bar.pack(side="bottom", fill="x", pady=(16, 0))

        can_install = bool(self.detection.recommended_blender) and (
            self.var_antigravity.get() or self.var_codex.get()
        )

        btn_install = tk.Button(
            btn_bar,
            text=self.t("btn_install"),
            font=("Segoe UI", 11, "bold"),
            bg=ModernTheme.PRIMARY,
            fg="#ffffff",
            activebackground=ModernTheme.PRIMARY_HOVER,
            activeforeground="#ffffff",
            bd=0,
            padx=20,
            pady=10,
            cursor="hand2" if can_install else "arrow",
            command=self.show_screen_review if can_install else None,
        )
        btn_install.pack(side="right")

        btn_repair = tk.Button(
            btn_bar,
            text=self.t("btn_repair"),
            font=("Segoe UI", 9),
            bg=ModernTheme.SURFACE,
            fg=ModernTheme.TEXT_MAIN,
            bd=1,
            padx=14,
            pady=8,
            command=self.trigger_repair,
        )
        btn_repair.pack(side="left")

    def _toggle_advanced_settings(self):
        win = tk.Toplevel(self.root)
        win.title(self.t("adv_settings_title"))
        win.geometry("520x280")
        win.configure(bg=ModernTheme.BG)
        win.transient(self.root)
        win.grab_set()

        lbl = tk.Label(win, text=self.t("custom_workspace_lbl"), fg=ModernTheme.TEXT_MAIN, bg=ModernTheme.BG)
        lbl.pack(anchor="w", padx=20, pady=(20, 4))

        ent = tk.Entry(win, textvariable=self.var_workspace, width=50)
        ent.pack(anchor="w", padx=20)

        p_lbl = tk.Label(win, text=self.t("port_lbl"), fg=ModernTheme.TEXT_MAIN, bg=ModernTheme.BG)
        p_lbl.pack(anchor="w", padx=20, pady=(16, 4))

        p_ent = tk.Entry(win, textvariable=self.var_port, width=15)
        p_ent.pack(anchor="w", padx=20)

        ok_btn = tk.Button(win, text=self.t("btn_save_settings"), bg=ModernTheme.PRIMARY, fg="#fff", command=win.destroy)
        ok_btn.pack(side="bottom", pady=20)

    # =========================================================================
    # SCREEN B: CONSENT / REVIEW
    # =========================================================================
    def show_screen_review(self):
        self.active_screen = "review"
        self.clear_screen()
        frame = tk.Frame(self.container, bg=ModernTheme.BG)
        frame.pack(fill="both", expand=True)
        self.current_frame = frame

        self._render_top_header(frame, title_text=self.t("review_title"), show_badge=False)

        desc = tk.Label(
            frame,
            text=self.t("review_summary"),
            font=("Segoe UI", 9),
            fg=ModernTheme.TEXT_MUTED,
            bg=ModernTheme.BG,
        )
        desc.pack(anchor="w", pady=(0, 16))

        box = tk.Text(frame, height=12, bg=ModernTheme.SURFACE, fg=ModernTheme.TEXT_MAIN, bd=1, padx=12, pady=12)
        box.pack(fill="both", expand=True)

        target_name = self.detection.recommended_blender.display_name if self.detection.recommended_blender else "None"
        summary_lines = [
            self.t("review_item_blender", name=target_name),
            self.t("review_item_addon"),
            self.t("review_item_mcp"),
            self.t("review_item_workspace", path=self.var_workspace.get()),
            self.t("review_item_security"),
        ]
        if self.var_antigravity.get():
            summary_lines.append(self.t("review_item_ag"))
        if self.var_codex.get():
            summary_lines.append(self.t("review_item_codex"))

        if self.detection.recommended_blender and self.detection.recommended_blender.is_running:
            summary_lines.append(self.t("review_blender_running"))

        box.insert("1.0", "\n".join(summary_lines))
        box.configure(state="disabled")

        # Buttons
        btn_bar = tk.Frame(frame, bg=ModernTheme.BG)
        btn_bar.pack(side="bottom", fill="x", pady=(16, 0))

        btn_confirm = tk.Button(
            btn_bar,
            text=self.t("btn_confirm"),
            font=("Segoe UI", 10, "bold"),
            bg=ModernTheme.PRIMARY,
            fg="#ffffff",
            bd=0,
            padx=18,
            pady=8,
            command=self.show_screen_progress,
        )
        btn_confirm.pack(side="right")

        btn_back = tk.Button(
            btn_bar,
            text=self.t("btn_back"),
            font=("Segoe UI", 9),
            bg=ModernTheme.SURFACE,
            fg=ModernTheme.TEXT_MAIN,
            bd=1,
            padx=14,
            pady=6,
            command=self.show_screen_welcome,
        )
        btn_back.pack(side="left")

    # =========================================================================
    # SCREEN C: PROGRESS
    # =========================================================================
    def show_screen_progress(self):
        self.active_screen = "progress"
        self.clear_screen()
        frame = tk.Frame(self.container, bg=ModernTheme.BG)
        frame.pack(fill="both", expand=True)
        self.current_frame = frame

        title = tk.Label(
            frame,
            text=self.t("progress_title"),
            font=("Segoe UI", 16, "bold"),
            fg=ModernTheme.TEXT_MAIN,
            bg=ModernTheme.BG,
        )
        title.pack(anchor="w", pady=(0, 16))

        # Step labels container
        steps_frame = tk.Frame(frame, bg=ModernTheme.SURFACE, bd=1, relief="solid")
        steps_frame.pack(fill="both", expand=True, padx=2, pady=4, ipady=12)

        self.step_labels = {}
        step_names = [
            ("verify_package", self.t("step_verify_package")),
            ("stage_directories", self.t("step_stage_directories")),
            ("install_runtime", self.t("step_install_runtime")),
            ("install_addon", self.t("step_install_addon")),
            ("register_antigravity", self.t("step_register_antigravity")),
            ("register_codex", self.t("step_register_codex")),
            ("init_session", self.t("step_init_session")),
            ("verify_mcp", self.t("step_verify_mcp")),
        ]

        for code, label in step_names:
            row = tk.Frame(steps_frame, bg=ModernTheme.SURFACE)
            row.pack(fill="x", padx=16, pady=4)
            icon_lbl = tk.Label(row, text="⏳", font=("Segoe UI", 10), fg=ModernTheme.TEXT_MUTED, bg=ModernTheme.SURFACE)
            icon_lbl.pack(side="left", padx=(0, 8))
            text_lbl = tk.Label(row, text=label, font=("Segoe UI", 9), fg=ModernTheme.TEXT_MAIN, bg=ModernTheme.SURFACE)
            text_lbl.pack(side="left")
            self.step_labels[code] = (icon_lbl, text_lbl)

        # Launch background worker
        threading.Thread(target=self._run_install_worker, daemon=True).start()

    def _run_install_worker(self):
        options = InstallOptions(
            blender=self.detection.recommended_blender,
            install_antigravity=self.var_antigravity.get(),
            install_codex=self.var_codex.get(),
            workspace_dir=pathlib.Path(self.var_workspace.get()),
            port=self.var_port.get(),
        )
        orchestrator = InstallationOrchestrator(options)

        def on_progress(name: str, status: str, msg: str):
            self.root.after(0, self._update_step_ui, name, status, msg)

        success, steps = orchestrator.run_installation(progress_callback=on_progress)
        time.sleep(0.8)
        self.root.after(0, self.show_screen_dashboard if success else lambda: self._show_install_failed(steps))

    def _update_step_ui(self, name: str, status: str, msg: str):
        if name in self.step_labels:
            icon_lbl, text_lbl = self.step_labels[name]
            if status == "running":
                icon_lbl.configure(text="⚙", fg=ModernTheme.PRIMARY)
            elif status == "done":
                icon_lbl.configure(text="✔", fg=ModernTheme.SUCCESS)
            elif status == "failed":
                icon_lbl.configure(text="✖", fg=ModernTheme.ERROR)
            elif status == "skipped":
                icon_lbl.configure(text="–", fg=ModernTheme.TEXT_MUTED)

    def _show_install_failed(self, steps=None):
        detail = ""
        if steps:
            for s in steps:
                if s.status == "failed":
                    detail = f"\n\nStep: {s.name}\nDetail: {s.message}"
                    break
        messagebox.showerror(
            self.t("install_failed_title"),
            self.t("install_failed_msg", detail=detail),
        )
        self.show_screen_welcome()

    # =========================================================================
    # SCREEN D: CONNECTED / DASHBOARD
    # =========================================================================
    def show_screen_dashboard(self):
        self.active_screen = "dashboard"
        self.clear_screen()
        frame = tk.Frame(self.container, bg=ModernTheme.BG)
        frame.pack(fill="both", expand=True)
        self.current_frame = frame

        self._render_top_header(frame, title_text=self.t("dashboard_title"), show_badge=True)

        sub = tk.Label(
            frame,
            text=self.t("dashboard_sub"),
            font=("Segoe UI", 9),
            fg=ModernTheme.TEXT_MUTED,
            bg=ModernTheme.BG,
        )
        sub.pack(anchor="w", pady=(0, 16))

        # Component health list
        card = tk.LabelFrame(
            frame,
            text=self.t("comp_status_title"),
            font=("Segoe UI", 10, "bold"),
            fg=ModernTheme.TEXT_MAIN,
            bg=ModernTheme.SURFACE,
            bd=1,
            relief="solid",
        )
        card.pack(fill="x", pady=4, ipady=8, padx=2)

        items = [
            (self.t("comp_addon_title"), self.t("comp_addon_desc")),
            (self.t("comp_mcp_title"), self.t("comp_mcp_desc")),
            (self.t("comp_sec_title"), self.t("comp_sec_desc")),
            (self.t("comp_ws_title"), f" {str(self.var_workspace.get())}"),
        ]
        for title, val in items:
            r = tk.Frame(card, bg=ModernTheme.SURFACE)
            r.pack(fill="x", padx=16, pady=2)
            tk.Label(r, text=title, font=("Segoe UI", 9, "bold"), fg=ModernTheme.SUCCESS, bg=ModernTheme.SURFACE).pack(side="left")
            tk.Label(r, text=f" {val}", font=("Segoe UI", 9), fg=ModernTheme.TEXT_MAIN, bg=ModernTheme.SURFACE).pack(side="left")

        # Example prompt
        p_frame = tk.LabelFrame(frame, text=self.t("prompt_card_title"), bg=ModernTheme.SURFACE, fg=ModernTheme.TEXT_MAIN)
        p_frame.pack(fill="x", pady=12, ipady=8, padx=2)

        prompt_text = "Create a blue metallic cube named 'TestCube' in Blender at [2, 0, 1] using BlenderAgent Bridge."
        p_box = tk.Entry(p_frame, width=70, font=("Consolas", 9), bg=ModernTheme.BG, fg=ModernTheme.TEXT_MAIN)
        p_box.insert(0, prompt_text)
        p_box.pack(side="left", padx=12, fill="x", expand=True)

        def copy_prompt():
            self.root.clipboard_clear()
            self.root.clipboard_append(prompt_text)
            messagebox.showinfo(self.t("copied_title"), self.t("copied_msg"))

        cp_btn = tk.Button(p_frame, text=self.t("btn_copy"), bg=ModernTheme.PRIMARY, fg="#fff", command=copy_prompt)
        cp_btn.pack(side="right", padx=12)

        # Action Buttons Bar
        act_bar = tk.Frame(frame, bg=ModernTheme.BG)
        act_bar.pack(side="bottom", fill="x", pady=(12, 0))

        btn_test = tk.Button(
            act_bar,
            text=self.t("btn_test"),
            font=("Segoe UI", 10, "bold"),
            bg=ModernTheme.SUCCESS,
            fg="#ffffff",
            bd=0,
            padx=16,
            pady=8,
            command=self.run_test_connection,
        )
        btn_test.pack(side="left")

        btn_repair = tk.Button(
            act_bar,
            text=self.t("btn_repair"),
            font=("Segoe UI", 9),
            bg=ModernTheme.SURFACE,
            fg=ModernTheme.TEXT_MAIN,
            bd=1,
            padx=12,
            pady=6,
            command=self.trigger_repair,
        )
        btn_repair.pack(side="left", padx=8)

        btn_uninst = tk.Button(
            act_bar,
            text=self.t("btn_uninst"),
            font=("Segoe UI", 9),
            bg=ModernTheme.SURFACE,
            fg=ModernTheme.ERROR,
            bd=1,
            padx=12,
            pady=6,
            command=self.trigger_uninstall,
        )
        btn_uninst.pack(side="right")

    def run_test_connection(self):
        """Run verified live check using discovered session port and credentials."""
        import json
        import httpx
        from .constants import DEFAULT_WORKSPACE_DIR, SESSION_FILE_PATH, LIVE_SESSION_FILE_PATH

        port = 9876
        token = None

        for sfile in [LIVE_SESSION_FILE_PATH, SESSION_FILE_PATH]:
            if sfile.exists():
                try:
                    with open(sfile, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("port"):
                        port = int(data["port"])
                    if data.get("token"):
                        token = data["token"]
                        break
                except Exception:
                    pass

        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.get(f"http://127.0.0.1:{port}/api/v1/health")
                if res.status_code == 200:
                    health_info = res.json()
                    version = health_info.get("version", VERSION)

                    if not token:
                        messagebox.showwarning(
                            self.t("conn_test_title"),
                            self.t("conn_test_no_token", port=port, version=version),
                        )
                        return

                    # Verify authenticated RPC command
                    auth_res = client.post(
                        f"http://127.0.0.1:{port}/api/v1/command",
                        headers={"Authorization": f"Bearer {token}"},
                        json={"command": "get_scene_info", "params": {}},
                        timeout=3.0,
                    )
                    if auth_res.status_code == 200:
                        payload = auth_res.json()
                        if payload.get("status") == "success":
                            scene_data = payload.get("data", {})
                            active_obj = scene_data.get("active_object") or "None"
                            obj_count = len(scene_data.get("objects", []))
                            messagebox.showinfo(
                                self.t("conn_test_title"),
                                self.t(
                                    "conn_test_success",
                                    port=port,
                                    version=version,
                                    active_obj=active_obj,
                                    obj_count=obj_count,
                                ),
                            )
                            return
                        else:
                            err_msg = payload.get("error", {}).get("message", "Unknown error")
                            messagebox.showerror(
                                self.t("conn_test_title"),
                                f"Bridge reachable, but command execution returned error:\n{err_msg}",
                            )
                            return
                    elif auth_res.status_code in (401, 403):
                        messagebox.showerror(
                            self.t("conn_test_title"),
                            self.t("conn_test_rejected", port=port, code=auth_res.status_code),
                        )
                        return
                    else:
                        messagebox.showerror(
                            self.t("conn_test_title"),
                            f"Bridge server reachable, but returned unexpected HTTP {auth_res.status_code} during test command.",
                        )
                        return
        except httpx.ConnectError:
            messagebox.showwarning(
                self.t("conn_test_title"),
                self.t("conn_test_offline", port=port),
            )
            return
        except Exception as err:
            messagebox.showwarning(
                self.t("conn_test_title"),
                f"Could not connect to Bridge on port {port}: {err}\n\n"
                f"Open Blender to start the bridge automatically.",
            )
            return

        messagebox.showwarning(
            self.t("conn_test_title"),
            self.t("conn_test_offline", port=port),
        )

    def trigger_repair(self):
        confirm = messagebox.askyesno(self.t("repair_confirm_title"), self.t("repair_confirm_msg"))
        if confirm:
            self.show_screen_progress()

    def trigger_uninstall(self):
        confirm = messagebox.askyesno(
            self.t("uninst_confirm_title"),
            self.t("uninst_confirm_msg"),
        )
        if confirm:
            orch = InstallationOrchestrator()
            success, logs = orch.uninstall(keep_workspace=True)
            messagebox.showinfo(self.t("uninst_done_title"), "\n".join(logs))
            self.show_screen_welcome()


def launch_gui():
    """Application entrypoint for the graphical installer."""
    root = tk.Tk()
    app = InstallerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    launch_gui()
