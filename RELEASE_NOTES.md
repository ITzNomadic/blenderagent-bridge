# BlenderAgent Bridge v0.2.2-beta (Beta / Experimental)

Welcome to the **v0.2.2-beta** release of **BlenderAgent Bridge**! This release marks our first public beta release, providing a fully automated, secure Model Context Protocol (MCP) bridge connecting 3D modeling in Blender directly to autonomous AI agents (Google Antigravity, OpenAI Codex, Claude Desktop, Cursor, and custom agent loops).

> [!WARNING]
> **Beta / Experimental Status**: This software is released under the MIT license as an active beta. While it passes all 86 rigorous automated security and concurrency test suites, we invite community feedback, bug reports, and pull requests to help shape the stable 1.0 release.

---

### What's New in v0.2.2-beta:

1. **Automatic System Language Detection (i18n)**:
   - The installer wizard and Blender 3D Viewport panel automatically detect your operating system's language via Windows LANGID.
   - If your system is in **English**, the entire UI displays in English by default.
   - If your system is in **Spanish**, the interface displays in Spanish.
   - An interactive header switch (`🌐 Language / Idioma`) allows you to switch languages instantly at runtime.

2. **Automated Cryptographic Token Synchronization**:
   - Zero manual credential configuration or button clicking required.
   - On initialization, a 32-character cryptographically secure token is generated and persisted to user-private files with restricted Windows NTFS ACLs.
   - Blender and the MCP server automatically discover and authenticate without manual user intervention.

3. **Streamlined, Clutter-Free Interface**:
   - The Blender sidebar panel has been decluttered: sensitive tokens and internal keys are removed from the main operational view while maintaining rigorous internal Bearer authentication.
   - Emergency credential reset is preserved in an advanced diagnostics section.

4. **One-Click Windows Setup (`BlenderAgentBridge-Setup.exe`)**:
   - Zero-command installation: automatically discovers Blender 4.2+ / 5.2, registers the standalone MCP server for Google Antigravity and OpenAI Codex, and configures an isolated user-space workspace.
   - No global Python installation required on the host system.

5. **Hardened Security & Concurrency Verification**:
   - 86 automated unit and integration tests passing with 100% success rate.
   - Robust defenses against DNS rebinding, CSRF (`Host` and `Origin` validation), Windows ADS path traversal (`:`), and non-finite IEEE 754 float attacks (NaN/Infinity).
   - In-flight idempotency caching preventing duplicate executions during network hiccups or timeouts.

---

### Quick Installation:
1. Download **`BlenderAgentBridge-Setup.exe`** below.
2. Run the executable and follow the on-screen wizard.
3. Open Blender and start building with your AI agent!

For manual developer setups and full source code, download **`BlenderAgentBridge-v0.2.2-Windows.zip`**.

---

### Checksums (SHA-256):
- `BlenderAgentBridge-Setup.exe`: `a6b66dd905c375f80584de9d3e8bbf8a4c71ed851c501fc49ae39597b9b504e8`
- `BlenderAgentBridge-v0.2.2-Windows.zip`: `964e6e742b9063b9907a6a4372bd7e850c6d4211872e75a5cc2ff5eea52b641f`
