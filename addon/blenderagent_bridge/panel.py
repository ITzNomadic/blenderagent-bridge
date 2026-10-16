"""3D Viewport sidebar panel for BlenderAgent Bridge."""

from __future__ import annotations

try:
    import bpy
    from bpy.types import Panel
except ImportError:
    bpy = None
    Panel = object

from .security import audit_logger
from .server import bridge_server


class VIEW3D_PT_BlenderAgentBridgePanel(Panel):
    """Sidebar Panel for BlenderAgent Bridge status, configuration, and monitoring."""

    bl_label = "BlenderAgent Bridge"
    bl_idname = "VIEW3D_PT_blenderagent_bridge"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BlenderAgent"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # 1. Connection Status Banner
        is_running = bridge_server.is_running
        box_status = layout.box()
        row = box_status.row(align=True)
        if is_running:
            row.label(text="Status: ACTIVE", icon="CHECKMARK")
            row.label(text=f"Port: {bridge_server.port}", icon="URL")
        else:
            row.label(text="Status: STOPPED", icon="CANCEL")
            row.label(text="Offline", icon="ERROR")

        # 2. Control Operators (Start / Stop)
        row_ctrl = layout.row(align=True)
        row_ctrl.scale_y = 1.3
        if not is_running:
            row_ctrl.operator("wm.blenderagent_start_bridge", text="Start Bridge", icon="PLAY")
        else:
            row_ctrl.operator("wm.blenderagent_stop_bridge", text="Stop Bridge", icon="PAUSE")

        # 3. Connection & Workspace Configuration
        layout.separator()
        box_config = layout.box()
        box_config.label(text="Configuration", icon="PREFERENCES")

        wm = context.window_manager
        props_target = wm if hasattr(wm, "blenderagent_port") else scene

        col = box_config.column(align=True)
        col.prop(props_target, "blenderagent_port", text="Port")
        col.prop(props_target, "blenderagent_workspace_dir", text="Workspace")

        # 4. Activity & Metrics
        layout.separator()
        box_activity = layout.box()
        header_row = box_activity.row()
        header_row.label(text=f"Processed: {audit_logger.total_count} commands", icon="CONSOLE")
        header_row.operator("wm.blenderagent_clear_log", text="", icon="TRASH")

        # 5. Compact Operational Log
        recent = audit_logger.get_recent(5)
        if recent:
            log_col = box_activity.column(align=True)
            for entry in recent:
                row_entry = log_col.row(align=True)
                icon = "CHECKMARK" if entry["status"] in ("SUCCESS", "ACTIVE") else "ERROR"
                row_entry.label(text=f"{entry['time']} [{entry['command']}]", icon=icon)
                row_entry.label(text=entry["summary"][:24])
        else:
            box_activity.label(text="No recent operations", icon="INFO")

        # 6. Advanced Diagnostics
        layout.separator()
        box_diag = layout.box()
        row_diag = box_diag.row(align=True)
        row_diag.label(text="Diagnostics", icon="SETTINGS")
        row_diag.operator("wm.blenderagent_regenerate_token", text="Reset Credential", icon="FILE_REFRESH")


PANEL_CLASSES = [
    VIEW3D_PT_BlenderAgentBridgePanel,
]
