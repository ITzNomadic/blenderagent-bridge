"""3D Viewport sidebar panel for BlenderAgent Bridge with bilingual UI support."""

from __future__ import annotations

try:
    import bpy
    from bpy.types import Panel
except ImportError:
    bpy = None
    Panel = object

from .security import audit_logger
from .server import bridge_server


def _is_spanish() -> bool:
    """Detect whether Blender UI or host system is configured in Spanish."""
    if bpy is not None:
        try:
            loc = getattr(bpy.app.translations, "locale", "")
            if loc.startswith("es"):
                return True
            elif loc.startswith("en"):
                return False
        except Exception:
            pass
    try:
        import locale
        loc = (locale.getlocale()[0] or "").lower()
        if loc.startswith("es"):
            return True
    except Exception:
        pass
    return False


class VIEW3D_PT_BlenderAgentBridgePanel(Panel):
    """Main Sidebar Panel for BlenderAgent Bridge status and monitoring."""

    bl_label = "BlenderAgent Bridge"
    bl_idname = "VIEW3D_PT_blenderagent_bridge"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BlenderAgent"

    def draw(self, context):
        layout = self.layout
        es = _is_spanish()

        # 1. Connection Status Banner
        is_running = bridge_server.is_running
        box_status = layout.box()
        row = box_status.row(align=True)
        if is_running:
            lbl_active = "Estado: ACTIVO" if es else "Status: ACTIVE"
            row.label(text=lbl_active, icon="CHECKMARK")
            row.label(text=f"Port: {bridge_server.port}", icon="URL")
        else:
            lbl_stopped = "Estado: DETENIDO" if es else "Status: STOPPED"
            lbl_offline = "Desconectado" if es else "Offline"
            row.label(text=lbl_stopped, icon="CANCEL")
            row.label(text=lbl_offline, icon="ERROR")

        # 2. Control Operators (Start / Stop)
        row_ctrl = layout.row(align=True)
        row_ctrl.scale_y = 1.3
        if not is_running:
            lbl_start = "Iniciar Puente" if es else "Start Bridge"
            row_ctrl.operator("wm.blenderagent_start_bridge", text=lbl_start, icon="PLAY")
        else:
            lbl_stop = "Detener Puente" if es else "Stop Bridge"
            row_ctrl.operator("wm.blenderagent_stop_bridge", text=lbl_stop, icon="PAUSE")

        # 3. Activity & Metrics
        layout.separator()
        box_activity = layout.box()
        header_row = box_activity.row()
        lbl_proc = f"Procesados: {audit_logger.total_count} comandos" if es else f"Processed: {audit_logger.total_count} commands"
        header_row.label(text=lbl_proc, icon="CONSOLE")
        header_row.operator("wm.blenderagent_clear_log", text="", icon="TRASH")

        # 4. Compact Operational Log
        recent = audit_logger.get_recent(5)
        if recent:
            log_col = box_activity.column(align=True)
            for entry in recent:
                row_entry = log_col.row(align=True)
                icon = "CHECKMARK" if entry["status"] in ("SUCCESS", "ACTIVE") else "ERROR"
                row_entry.label(text=f"{entry['time']} [{entry['command']}]", icon=icon)
                row_entry.label(text=entry["summary"][:24])
        else:
            lbl_no_ops = "Sin operaciones recientes" if es else "No recent operations"
            box_activity.label(text=lbl_no_ops, icon="INFO")


class VIEW3D_PT_BlenderAgentBridgeAdvancedPanel(Panel):
    """Collapsible Advanced Settings subpanel kept closed during normal usage."""

    bl_label = "Ajustes Avanzados" if _is_spanish() else "Advanced Settings"
    bl_idname = "VIEW3D_PT_blenderagent_bridge_advanced"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BlenderAgent"
    bl_parent_id = "VIEW3D_PT_blenderagent_bridge"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        scene = context.scene
        props_target = wm if hasattr(wm, "blenderagent_port") else scene
        es = _is_spanish()

        col = layout.column(align=True)
        lbl_port = "Puerto" if es else "Port"
        lbl_ws = "Espacio de trabajo" if es else "Workspace"
        col.prop(props_target, "blenderagent_port", text=lbl_port)
        col.prop(props_target, "blenderagent_workspace_dir", text=lbl_ws)

        layout.separator()
        row = layout.row()
        lbl_reset = "Restablecer Credencial" if es else "Reset Credential"
        row.operator("wm.blenderagent_regenerate_token", text=lbl_reset, icon="FILE_REFRESH")


PANEL_CLASSES = [
    VIEW3D_PT_BlenderAgentBridgePanel,
    VIEW3D_PT_BlenderAgentBridgeAdvancedPanel,
]
