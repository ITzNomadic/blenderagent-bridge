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
except ImportError:
    from .constants import (
        APP_NAME,
        DEFAULT_PORT,
        DEFAULT_WORKSPACE_DIR,
        VERSION,
    )
    from .detector import BlenderInstallation, SystemDetectionResult, detect_system_state
    from .orchestrator import InstallationOrchestrator, InstallOptions, StepProgress


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
        self.root.title(f"{APP_NAME} v{VERSION} — Installer & AI Setup")
        self.root.geometry("760x620")
        self.root.minsize(720, 560)
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

    def clear_screen(self):
        if self.current_frame:
            self.current_frame.destroy()
            self.current_frame = None

    # =========================================================================
    # SCREEN A: WELCOME / DETECT
    # =========================================================================
    def show_screen_welcome(self):
        self.clear_screen()
        frame = tk.Frame(self.container, bg=ModernTheme.BG)
        frame.pack(fill="both", expand=True)
        self.current_frame = frame

        # Header
        header = tk.Label(
            frame,
            text=APP_NAME,
            font=("Segoe UI", 20, "bold"),
            fg=ModernTheme.TEXT_MAIN,
            bg=ModernTheme.BG,
        )
        header.pack(anchor="w")

        sub = tk.Label(
            frame,
            text="Connect Blender to your AI assistants (Google Antigravity & OpenAI Codex)",
            font=("Segoe UI", 10),
            fg=ModernTheme.TEXT_MUTED,
            bg=ModernTheme.BG,
        )
        sub.pack(anchor="w", pady=(0, 16))

        # 1. Blender Card
        b_card = tk.LabelFrame(
            frame,
            text="  3D Environment (Blender)  ",
            font=("Segoe UI", 10, "bold"),
            fg=ModernTheme.TEXT_MAIN,
            bg=ModernTheme.SURFACE,
            bd=1,
            relief="solid",
        )
        b_card.pack(fill="x", pady=8, ipady=8, padx=2)

        if self.detection.blender_installations:
            b_text = f"Detected: {self.detection.recommended_blender.display_name}"
            b_color = ModernTheme.SUCCESS
        else:
            b_text = "No compatible Blender installation found (Requires Blender 4.2+ or 5.2)."
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
            text="  AI Clients Integration  ",
            font=("Segoe UI", 10, "bold"),
            fg=ModernTheme.TEXT_MAIN,
            bg=ModernTheme.SURFACE,
            bd=1,
            relief="solid",
        )
        ai_card.pack(fill="x", pady=8, ipady=8, padx=2)

        # Antigravity Checkbox
        ag_status = "Detected" if self.detection.antigravity.installed else "Not detected"
        if self.detection.antigravity.is_configured:
            ag_status += " (Configured)"
        ag_cb = tk.Checkbutton(
            ai_card,
            text=f"Google Antigravity — [{ag_status}]",
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
        codex_status = "Detected" if self.detection.codex.installed else "Not detected"
        if self.detection.codex.is_configured:
            codex_status += " (Configured)"
        codex_cb = tk.Checkbutton(
            ai_card,
            text=f"OpenAI Codex (CLI / IDE) — [{codex_status}]",
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
            text="⚙ Advanced Settings (Workspace & Ports)",
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
            text="Install & Connect  ➔",
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
            text="Repair Existing Setup",
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
        win.title("Advanced Settings")
        win.geometry("520x280")
        win.configure(bg=ModernTheme.BG)
        win.transient(self.root)
        win.grab_set()

        lbl = tk.Label(win, text="Custom Workspace Directory:", fg=ModernTheme.TEXT_MAIN, bg=ModernTheme.BG)
        lbl.pack(anchor="w", padx=20, pady=(20, 4))

        ent = tk.Entry(win, textvariable=self.var_workspace, width=50)
        ent.pack(anchor="w", padx=20)

        p_lbl = tk.Label(win, text="Local Bridge Port (Default 9876):", fg=ModernTheme.TEXT_MAIN, bg=ModernTheme.BG)
        p_lbl.pack(anchor="w", padx=20, pady=(16, 4))

        p_ent = tk.Entry(win, textvariable=self.var_port, width=15)
        p_ent.pack(anchor="w", padx=20)

        ok_btn = tk.Button(win, text="Save Settings", bg=ModernTheme.PRIMARY, fg="#fff", command=win.destroy)
        ok_btn.pack(side="bottom", pady=20)

    # =========================================================================
    # SCREEN B: CONSENT / REVIEW
    # =========================================================================
    def show_screen_review(self):
        self.clear_screen()
        frame = tk.Frame(self.container, bg=ModernTheme.BG)
        frame.pack(fill="both", expand=True)
        self.current_frame = frame

        title = tk.Label(
            frame,
            text="Review Installation Changes",
            font=("Segoe UI", 16, "bold"),
            fg=ModernTheme.TEXT_MAIN,
            bg=ModernTheme.BG,
        )
        title.pack(anchor="w", pady=(0, 8))

        desc = tk.Label(
            frame,
            text="The installer will execute the following verified modifications on your system:",
            font=("Segoe UI", 9),
            fg=ModernTheme.TEXT_MUTED,
            bg=ModernTheme.BG,
        )
        desc.pack(anchor="w", pady=(0, 16))

        box = tk.Text(frame, height=12, bg=ModernTheme.SURFACE, fg=ModernTheme.TEXT_MAIN, bd=1, padx=12, pady=12)
        box.pack(fill="both", expand=True)

        summary_lines = [
            f"1. Target Blender: {self.detection.recommended_blender.display_name if self.detection.recommended_blender else 'None'}",
            f"2. Addon: Install 'blenderagent_bridge' extension into user profile extensions repository.",
            f"3. Standalone MCP Launcher: Place binary into AppData\\Local\\Programs\\BlenderAgentBridge\\bin",
            f"4. Workspace: Use writable directory at '{self.var_workspace.get()}' (no Program Files access).",
            f"5. Security: Generate ephemeral Bearer token secured with Windows DPAPI and private ACLs.",
        ]
        if self.var_antigravity.get():
            summary_lines.append("6. Google Antigravity: Register 'blenderagent-bridge' in ~/.gemini/config/mcp_config.json.")
        if self.var_codex.get():
            summary_lines.append("7. OpenAI Codex: Register [mcp_servers.blenderagent-bridge] in ~/.codex/config.toml.")

        if self.detection.recommended_blender and self.detection.recommended_blender.is_running:
            summary_lines.append("\n⚠ Note: Blender is currently running. The extension will install safely into your user profile without interrupting unsaved projects.")

        box.insert("1.0", "\n".join(summary_lines))
        box.configure(state="disabled")

        # Buttons
        btn_bar = tk.Frame(frame, bg=ModernTheme.BG)
        btn_bar.pack(side="bottom", fill="x", pady=(16, 0))

        btn_confirm = tk.Button(
            btn_bar,
            text="Confirm & Apply  ➔",
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
            text="Back",
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
        self.clear_screen()
        frame = tk.Frame(self.container, bg=ModernTheme.BG)
        frame.pack(fill="both", expand=True)
        self.current_frame = frame

        title = tk.Label(
            frame,
            text="Installing BlenderAgent Bridge...",
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
            ("verify_package", "Verify installation packages"),
            ("stage_directories", "Stage user workspace and directories"),
            ("install_runtime", "Provision standalone MCP runtime"),
            ("install_addon", "Install Blender extension"),
            ("register_antigravity", "Configure Google Antigravity"),
            ("register_codex", "Configure OpenAI Codex"),
            ("init_session", "Initialize secure cryptographic session"),
            ("verify_mcp", "Verify MCP registration integrity"),
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
                    detail = f"\n\nPaso fallido: {s.name}\nDetalle: {s.message}"
                    break
        messagebox.showerror(
            "Installation Error",
            f"Installation did not complete successfully.{detail}\n\nRevisa el registro en:\n%LOCALAPPDATA%\\BlenderAgentBridge\\installer.log",
        )
        self.show_screen_welcome()

    # =========================================================================
    # SCREEN D: CONNECTED / DASHBOARD
    # =========================================================================
    def show_screen_dashboard(self):
        self.clear_screen()
        frame = tk.Frame(self.container, bg=ModernTheme.BG)
        frame.pack(fill="both", expand=True)
        self.current_frame = frame

        header = tk.Label(
            frame,
            text="✔ Ready to Use!",
            font=("Segoe UI", 18, "bold"),
            fg=ModernTheme.SUCCESS,
            bg=ModernTheme.BG,
        )
        header.pack(anchor="w", pady=(0, 4))

        sub = tk.Label(
            frame,
            text="BlenderAgent Bridge is successfully installed and integrated with your AI clients.",
            font=("Segoe UI", 9),
            fg=ModernTheme.TEXT_MUTED,
            bg=ModernTheme.BG,
        )
        sub.pack(anchor="w", pady=(0, 16))

        # Component health list
        card = tk.LabelFrame(
            frame,
            text="  Component Status  ",
            font=("Segoe UI", 10, "bold"),
            fg=ModernTheme.TEXT_MAIN,
            bg=ModernTheme.SURFACE,
            bd=1,
            relief="solid",
        )
        card.pack(fill="x", pady=4, ipady=8, padx=2)

        items = [
            ("✔ Blender Extension:", "Installed and active in user repository"),
            ("✔ MCP Server:", "Registered and verified in client configuration"),
            ("✔ Secure Session:", "Token protected with Windows DPAPI and private ACLs"),
            ("✔ Workspace:", str(self.var_workspace.get())),
        ]
        for title, val in items:
            r = tk.Frame(card, bg=ModernTheme.SURFACE)
            r.pack(fill="x", padx=16, pady=2)
            tk.Label(r, text=title, font=("Segoe UI", 9, "bold"), fg=ModernTheme.SUCCESS, bg=ModernTheme.SURFACE).pack(side="left")
            tk.Label(r, text=f" {val}", font=("Segoe UI", 9), fg=ModernTheme.TEXT_MAIN, bg=ModernTheme.SURFACE).pack(side="left")

        # Example prompt
        p_frame = tk.LabelFrame(frame, text="  Try this prompt in Antigravity or Codex  ", bg=ModernTheme.SURFACE, fg=ModernTheme.TEXT_MAIN)
        p_frame.pack(fill="x", pady=12, ipady=8, padx=2)

        prompt_text = "Create a blue metallic cube named 'TestCube' in Blender at [2, 0, 1] using BlenderAgent Bridge."
        p_box = tk.Entry(p_frame, width=70, font=("Consolas", 9), bg=ModernTheme.BG, fg=ModernTheme.TEXT_MAIN)
        p_box.insert(0, prompt_text)
        p_box.pack(side="left", padx=12, fill="x", expand=True)

        def copy_prompt():
            self.root.clipboard_clear()
            self.root.clipboard_append(prompt_text)
            messagebox.showinfo("Copied", "Example prompt copied to clipboard!")

        cp_btn = tk.Button(p_frame, text="Copy", bg=ModernTheme.PRIMARY, fg="#fff", command=copy_prompt)
        cp_btn.pack(side="right", padx=12)

        # Action Buttons Bar
        act_bar = tk.Frame(frame, bg=ModernTheme.BG)
        act_bar.pack(side="bottom", fill="x", pady=(12, 0))

        btn_test = tk.Button(
            act_bar,
            text="Test Connection",
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
            text="Repair",
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
            text="Uninstall",
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
                    version = health_info.get("version", "0.2.2")

                    if not token:
                        messagebox.showwarning(
                            "Connection Test",
                            f"HTTP server is reachable at http://127.0.0.1:{port} (v{version}), "
                            f"but no session token was found on disk.\n\n"
                            f"Restart Blender or check that BlenderAgent Bridge extension is enabled.",
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
                                "Connection Test",
                                f"✔ Bridge ACTIVE & FULLY AUTHENTICATED!\n\n"
                                f"• URL: http://127.0.0.1:{port}\n"
                                f"• Version: v{version}\n"
                                f"• Active Object: {active_obj}\n"
                                f"• Scene Objects: {obj_count}\n\n"
                                f"MCP tools are fully operational for AI agents.",
                            )
                            return
                        else:
                            err_msg = payload.get("error", {}).get("message", "Unknown error")
                            messagebox.showerror(
                                "Connection Test",
                                f"Bridge reachable, but command execution returned error:\n{err_msg}",
                            )
                            return
                    elif auth_res.status_code in (401, 403):
                        messagebox.showerror(
                            "Connection Test",
                            f"HTTP server is reachable on port {port}, but AUTHENTICATION REJECTED (HTTP {auth_res.status_code}).\n\n"
                            f"The stored session token does not match the running Blender instance.\n"
                            f"Restart Blender to re-synchronize session credentials.",
                        )
                        return
                    else:
                        messagebox.showerror(
                            "Connection Test",
                            f"Bridge server reachable, but returned unexpected HTTP {auth_res.status_code} during test command.",
                        )
                        return
        except httpx.ConnectError:
            messagebox.showwarning(
                "Connection Test",
                f"Bridge server is not currently listening on port {port}.\n\n"
                f"Open Blender to start the bridge automatically.",
            )
            return
        except Exception as err:
            messagebox.showwarning(
                "Connection Test",
                f"Could not connect to Bridge on port {port}: {err}\n\n"
                f"Open Blender to start the bridge automatically.",
            )
            return

        messagebox.showwarning(
            "Connection Test",
            f"Bridge server is not currently listening on port {port}.\n\n"
            f"Open Blender to start the bridge automatically.",
        )

    def trigger_repair(self):
        confirm = messagebox.askyesno("Repair", "Do you want to re-verify and repair all registrations and files?")
        if confirm:
            self.show_screen_progress()

    def trigger_uninstall(self):
        confirm = messagebox.askyesno(
            "Confirm Uninstall",
            "This will remove the extension and AI client registrations.\nYour projects and renders will NOT be deleted. Proceed?",
        )
        if confirm:
            orch = InstallationOrchestrator()
            success, logs = orch.uninstall(keep_workspace=True)
            messagebox.showinfo("Uninstalled", "\n".join(logs))
            self.show_screen_welcome()


def launch_gui():
    """Application entrypoint for the graphical installer."""
    root = tk.Tk()
    app = InstallerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    launch_gui()
