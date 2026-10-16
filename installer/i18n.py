"""Internationalization (i18n) and system language detection for BlenderAgent Bridge."""

from __future__ import annotations

import locale
import sys
from typing import Dict


def detect_system_language() -> str:
    """Detect whether system UI language is English ('en') or Spanish ('es').

    Defaults to 'en' when English or any non-Spanish language is detected.
    """
    try:
        if sys.platform == "win32":
            import ctypes
            # GetUserDefaultUILanguage returns a Windows LANGID
            # 0x09 is LANG_ENGLISH (e.g. 0x0409 en-US, 0x0809 en-GB)
            # 0x0A is LANG_SPANISH (e.g. 0x0C0A es-ES, 0x080A es-MX)
            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0xFF
            if lang_id == 0x09:
                return "en"
            elif lang_id == 0x0A:
                return "es"

        # Fallback to standard python locale
        loc = (locale.getlocale()[0] or "").lower()
        if loc.startswith("es"):
            return "es"
        elif loc.startswith("en"):
            return "en"
    except Exception:
        pass
    return "en"


TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "en": {
        "app_title": "{app_name} v{version} — Installer & AI Setup",
        "beta_badge": "BETA / EXPERIMENTAL",
        "subtitle": "Connect Blender to your AI assistants (Google Antigravity & OpenAI Codex)",
        "blender_card_title": "  3D Environment (Blender)  ",
        "blender_detected": "Detected: {display_name}",
        "blender_not_found": "No compatible Blender installation found (Requires Blender 4.2+ or 5.2).",
        "ai_card_title": "  AI Clients Integration  ",
        "antigravity_label": "Google Antigravity — [{status}]",
        "codex_label": "OpenAI Codex (CLI / IDE) — [{status}]",
        "status_detected": "Detected",
        "status_not_detected": "Not detected",
        "status_configured": " (Configured)",
        "adv_settings_btn": "⚙ Advanced Settings (Workspace & Ports)",
        "adv_settings_title": "Advanced Settings",
        "custom_workspace_lbl": "Custom Workspace Directory:",
        "port_lbl": "Local Bridge Port (Default 9876):",
        "btn_save_settings": "Save Settings",
        "btn_install": "Install & Connect  ➔",
        "btn_repair": "Repair Existing Setup",
        
        # Screen B: Review
        "review_title": "Review Installation Changes",
        "review_summary": "The installer will execute the following verified modifications on your system:",
        "review_item_blender": "1. Target Blender: {name}",
        "review_item_addon": "2. Addon: Install 'blenderagent_bridge' extension into user profile extensions repository.",
        "review_item_mcp": "3. Standalone MCP Server: Provision binary into AppData\\Local\\Programs\\BlenderAgentBridge\\bin",
        "review_item_workspace": "4. Workspace: Use writable directory at '{path}' (no Program Files access).",
        "review_item_security": "5. Security: Generate ephemeral Bearer token secured with Windows DPAPI and private ACLs.",
        "review_item_ag": "6. Google Antigravity: Register 'blenderagent-bridge' in ~/.gemini/config/mcp_config.json.",
        "review_item_codex": "7. OpenAI Codex: Register [mcp_servers.blenderagent-bridge] in ~/.codex/config.toml.",
        "review_blender_running": "\n⚠ Note: Blender is currently running. The extension will install safely into your user profile without interrupting unsaved projects.",
        "btn_confirm": "Confirm & Apply  ➔",
        "btn_back": "Back",

        # Screen C: Progress
        "progress_title": "Installing BlenderAgent Bridge...",
        "step_verify_package": "Verify installation packages",
        "step_stage_directories": "Stage user workspace and directories",
        "step_install_runtime": "Provision standalone MCP runtime",
        "step_install_addon": "Install Blender extension",
        "step_register_antigravity": "Configure Google Antigravity",
        "step_register_codex": "Configure OpenAI Codex",
        "step_init_session": "Initialize secure cryptographic session",
        "step_verify_mcp": "Verify MCP registration integrity",
        "install_failed_title": "Installation Error",
        "install_failed_msg": "Installation did not complete successfully.{detail}\n\nPlease check log at:\n%LOCALAPPDATA%\\BlenderAgentBridge\\installer.log",

        # Screen D: Dashboard
        "dashboard_title": "✔ Ready to Use!",
        "dashboard_sub": "BlenderAgent Bridge is successfully installed and integrated with your AI clients.",
        "comp_status_title": "  Component Status  ",
        "comp_addon_title": "✔ Blender Extension:",
        "comp_addon_desc": "Installed and active in user repository",
        "comp_mcp_title": "✔ MCP Server:",
        "comp_mcp_desc": "Registered and verified in client configuration",
        "comp_sec_title": "✔ Secure Session:",
        "comp_sec_desc": "Token protected with Windows DPAPI and private ACLs",
        "comp_ws_title": "✔ Workspace:",
        "prompt_card_title": "  Try this prompt in Antigravity or Codex  ",
        "btn_copy": "Copy",
        "copied_title": "Copied",
        "copied_msg": "Example prompt copied to clipboard!",
        "btn_test": "Test Connection",
        "btn_uninst": "Uninstall",

        # Dialogs & Tests
        "repair_confirm_title": "Repair",
        "repair_confirm_msg": "Do you want to re-verify and repair all registrations and files?",
        "uninst_confirm_title": "Confirm Uninstall",
        "uninst_confirm_msg": "This will remove the extension and AI client registrations.\nYour projects and renders will NOT be deleted. Proceed?",
        "uninst_done_title": "Uninstalled",
        "conn_test_title": "Connection Test",
        "conn_test_success": "✔ Bridge ACTIVE & FULLY AUTHENTICATED!\n\n• URL: http://127.0.0.1:{port}\n• Version: v{version}\n• Active Object: {active_obj}\n• Scene Objects: {obj_count}\n\nMCP tools are fully operational for AI agents.",
        "conn_test_no_token": "HTTP server is reachable at http://127.0.0.1:{port} (v{version}), but no session token was found on disk.\n\nRestart Blender or check that BlenderAgent Bridge extension is enabled.",
        "conn_test_rejected": "HTTP server is reachable on port {port}, but AUTHENTICATION REJECTED (HTTP {code}).\n\nThe stored session token does not match the running Blender instance.\nRestart Blender to re-synchronize session credentials.",
        "conn_test_offline": "Bridge server is not currently listening on port {port}.\n\nOpen Blender to start the bridge automatically.",
        "lang_switch_btn": "🌐 English",
    },
    "es": {
        "app_title": "{app_name} v{version} — Instalador y Configuración IA",
        "beta_badge": "BETA / EXPERIMENTAL",
        "subtitle": "Conecta Blender con tus asistentes de IA (Google Antigravity y OpenAI Codex)",
        "blender_card_title": "  Entorno 3D (Blender)  ",
        "blender_detected": "Detectado: {display_name}",
        "blender_not_found": "No se encontró una instalación compatible de Blender (Requiere Blender 4.2+ o 5.2).",
        "ai_card_title": "  Integración de Clientes de IA  ",
        "antigravity_label": "Google Antigravity — [{status}]",
        "codex_label": "OpenAI Codex (CLI / IDE) — [{status}]",
        "status_detected": "Detectado",
        "status_not_detected": "No detectado",
        "status_configured": " (Configurado)",
        "adv_settings_btn": "⚙ Ajustes Avanzados (Espacio de trabajo y Puertos)",
        "adv_settings_title": "Ajustes Avanzados",
        "custom_workspace_lbl": "Directorio Personalizado de Trabajo:",
        "port_lbl": "Puerto Local del Puente (Por defecto 9876):",
        "btn_save_settings": "Guardar Ajustes",
        "btn_install": "Instalar y Conectar  ➔",
        "btn_repair": "Reparar Instalación Existente",

        # Screen B: Review
        "review_title": "Confirmar Cambios de Instalación",
        "review_summary": "El instalador ejecutará las siguientes modificaciones verificadas en tu sistema:",
        "review_item_blender": "1. Blender Objetivo: {name}",
        "review_item_addon": "2. Extensión: Instalar 'blenderagent_bridge' en el repositorio de usuario.",
        "review_item_mcp": "3. Servidor MCP Autónomo: Instalar binario en AppData\\Local\\Programs\\BlenderAgentBridge\\bin",
        "review_item_workspace": "4. Espacio de Trabajo: Usar directorio con permisos en '{path}' (sin acceso a Program Files).",
        "review_item_security": "5. Seguridad: Generar token Bearer efímero protegido con DPAPI y ACLs privadas.",
        "review_item_ag": "6. Google Antigravity: Registrar 'blenderagent-bridge' en ~/.gemini/config/mcp_config.json.",
        "review_item_codex": "7. OpenAI Codex: Registrar [mcp_servers.blenderagent-bridge] en ~/.codex/config.toml.",
        "review_blender_running": "\n⚠ Nota: Blender está actualmente en ejecución. La extensión se instalará de forma segura en tu perfil sin interrumpir tus proyectos abiertos.",
        "btn_confirm": "Confirmar y Aplicar  ➔",
        "btn_back": "Atrás",

        # Screen C: Progress
        "progress_title": "Instalando BlenderAgent Bridge...",
        "step_verify_package": "Verificar paquetes de instalación",
        "step_stage_directories": "Preparar espacio de trabajo y directorios",
        "step_install_runtime": "Instalar servidor MCP autónomo",
        "step_install_addon": "Instalar extensión de Blender",
        "step_register_antigravity": "Configurar Google Antigravity",
        "step_register_codex": "Configurar OpenAI Codex",
        "step_init_session": "Inicializar sesión criptográfica segura",
        "step_verify_mcp": "Verificar integridad del registro MCP",
        "install_failed_title": "Error de Instalación",
        "install_failed_msg": "La instalación no se completó correctamente.{detail}\n\nPor favor revisa el registro en:\n%LOCALAPPDATA%\\BlenderAgentBridge\\installer.log",

        # Screen D: Dashboard
        "dashboard_title": "✔ ¡Listo para Usar!",
        "dashboard_sub": "BlenderAgent Bridge se ha instalado e integrado correctamente con tus clientes de IA.",
        "comp_status_title": "  Estado de los Componentes  ",
        "comp_addon_title": "✔ Extensión de Blender:",
        "comp_addon_desc": "Instalada y activa en el repositorio de usuario",
        "comp_mcp_title": "✔ Servidor MCP:",
        "comp_mcp_desc": "Registrado y verificado en la configuración de clientes",
        "comp_sec_title": "✔ Sesión Segura:",
        "comp_sec_desc": "Token protegido con Windows DPAPI y ACLs privadas",
        "comp_ws_title": "✔ Espacio de Trabajo:",
        "prompt_card_title": "  Prueba este comando en Antigravity o Codex  ",
        "btn_copy": "Copiar",
        "copied_title": "Copiado",
        "copied_msg": "¡Comando de ejemplo copiado al portapapeles!",
        "btn_test": "Probar Conexión",
        "btn_uninst": "Desinstalar",

        # Dialogs & Tests
        "repair_confirm_title": "Reparar",
        "repair_confirm_msg": "¿Deseas volver a verificar y reparar todos los registros y archivos?",
        "uninst_confirm_title": "Confirmar Desinstalación",
        "uninst_confirm_msg": "Esto eliminará la extensión y las configuraciones de IA.\nTus proyectos y renders NO serán eliminados. ¿Continuar?",
        "uninst_done_title": "Desinstalado",
        "conn_test_title": "Prueba de Conexión",
        "conn_test_success": "✔ ¡Puente ACTIVO Y TOTALMENTE AUTENTICADO!\n\n• URL: http://127.0.0.1:{port}\n• Versión: v{version}\n• Objeto Activo: {active_obj}\n• Objetos en Escena: {obj_count}\n\nLas herramientas MCP están 100% operativas para los agentes de IA.",
        "conn_test_no_token": "El servidor HTTP responde en http://127.0.0.1:{port} (v{version}), pero no se encontró un token en disco.\n\nReinicia Blender o comprueba que la extensión BlenderAgent Bridge esté habilitada.",
        "conn_test_rejected": "El servidor HTTP responde en el puerto {port}, pero la AUTENTICACIÓN FUE RECHAZADA (HTTP {code}).\n\nEl token de sesión almacenado no coincide con la instancia de Blender en ejecución.\nReinicia Blender para resincronizar las credenciales.",
        "conn_test_offline": "El servidor del puente no está escuchando actualmente en el puerto {port}.\n\nAbre Blender para iniciar el puente automáticamente.",
        "lang_switch_btn": "🌐 Español",
    },
}


def get_text(key: str, lang: str = "en", **kwargs) -> str:
    """Retrieve localized string by key and language code."""
    bundle = TRANSLATIONS.get(lang, TRANSLATIONS["en"])
    text = bundle.get(key, TRANSLATIONS["en"].get(key, key))
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text
