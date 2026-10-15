"""Blender operators for controlling the BlenderAgent Bridge lifecycle."""

from __future__ import annotations

import bpy
from bpy.types import Operator

from .security import audit_logger, generate_session_token
from .server import bridge_server


class WM_OT_BlenderAgentStartBridge(Operator):
    """Start the BlenderAgent Bridge local HTTP server and main-thread task consumer."""

    bl_idname = "wm.blenderagent_start_bridge"
    bl_label = "Start Bridge"
    bl_description = "Start the BlenderAgent Bridge local server on 127.0.0.1"

    def execute(self, context):
        scene = context.scene
        port = scene.blenderagent_port
        token = scene.blenderagent_token.strip() or None
        workspace = scene.blenderagent_workspace_dir.strip() or None

        success, msg = bridge_server.start(port=port, token=token, workspace_dir=workspace)
        if success:
            scene.blenderagent_is_running = True
            scene.blenderagent_token = bridge_server.token
            self.report({"INFO"}, msg)
            return {"FINISHED"}
        else:
            scene.blenderagent_is_running = False
            self.report({"ERROR"}, msg)
            return {"CANCELLED"}


class WM_OT_BlenderAgentStopBridge(Operator):
    """Stop the BlenderAgent Bridge local HTTP server and clean up resources."""

    bl_idname = "wm.blenderagent_stop_bridge"
    bl_label = "Stop Bridge"
    bl_description = "Stop the BlenderAgent Bridge local server"

    def execute(self, context):
        success, msg = bridge_server.stop()
        context.scene.blenderagent_is_running = False
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class WM_OT_BlenderAgentRegenerateToken(Operator):
    """Generate a fresh session token for BlenderAgent Bridge."""

    bl_idname = "wm.blenderagent_regenerate_token"
    bl_label = "New Token"
    bl_description = "Generate a new cryptographic Bearer token"

    def execute(self, context):
        new_token = generate_session_token()
        context.scene.blenderagent_token = new_token
        if bridge_server.is_running:
            # Restart server with new token
            port = context.scene.blenderagent_port
            workspace = context.scene.blenderagent_workspace_dir
            bridge_server.stop()
            bridge_server.start(port=port, token=new_token, workspace_dir=workspace)
            self.report({"INFO"}, "Token regenerated and bridge restarted.")
        else:
            self.report({"INFO"}, "New token generated.")
        return {"FINISHED"}


class WM_OT_BlenderAgentClearLog(Operator):
    """Clear the BlenderAgent Bridge activity audit log."""

    bl_idname = "wm.blenderagent_clear_log"
    bl_label = "Clear Log"
    bl_description = "Clear the in-memory activity audit records"

    def execute(self, context):
        audit_logger.clear()
        self.report({"INFO"}, "Audit log cleared.")
        return {"FINISHED"}


OPERATOR_CLASSES = [
    WM_OT_BlenderAgentStartBridge,
    WM_OT_BlenderAgentStopBridge,
    WM_OT_BlenderAgentRegenerateToken,
    WM_OT_BlenderAgentClearLog,
]
