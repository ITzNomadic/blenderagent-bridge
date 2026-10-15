# BlenderAgent Bridge v0.2.0 — User Installation Guide

## Overview

**BlenderAgent Bridge v0.2.0** features a **One-Click Windows Installer** (`BlenderAgentBridge-Setup.exe`). End users can connect Blender directly to **Google Antigravity** and **OpenAI Codex** without installing Python, cloning GitHub repositories, or configuring JSON files.

---

## Prerequisites

- **Operating System:** Windows 10 or 11 (64-bit).
- **Blender:** Blender 4.2+ LTS, 4.5 LTS, or **Blender 5.2 LTS**.
- **AI Clients:** Google Antigravity and/or OpenAI Codex.
- **Python:** *NOT required.* A standalone runtime is bundled with the installer.

---

## 3-Step Quick Start

### 1. Download & Launch
Download `BlenderAgentBridge-Setup.exe` and double-click to launch.

### 2. Verify & Select
The installer automatically detects:
- Installed Blender versions (including Blender 5.2).
- Google Antigravity configuration.
- OpenAI Codex configuration.

Check the assistants you want to connect to Blender and click **Install & Connect**.

### 3. Start Modeling with AI
Open Blender. In Antigravity or Codex, simply type:
> *"Create a blue metallic cube named 'MyCube' at [2, 0, 1] in Blender using BlenderAgent Bridge."*

The assistant will execute the instruction in real time.

---

## Key Features & Safety

- **Zero-Configuration Tokens:** Ephemeral Bearer tokens are cryptographically generated and protected with Windows DPAPI and user-restricted ACLs. You never need to copy or paste tokens.
- **Foreign Config Preservation:** Existing MCP servers in `mcp_config.json` and `config.toml` (e.g., `node_repl`, custom servers) are preserved intact.
- **Safe Non-Destructive Workspace:** Defaults to `%LOCALAPPDATA%\BlenderAgentBridge\workspace` avoiding administrative elevation issues and never touching `C:\Program Files`.
- **Integrated Repair:** Click **Repair** in the installer dashboard at any time to re-validate and heal configurations.
- **Clean Uninstall:** Unregistering cleanly removes the MCP entries and add-on without deleting your scenes or renders.

---

## Deliverables & Checksums

| File | Description |
| :--- | :--- |
| `BlenderAgentBridge-Setup.exe` | One-Click Graphical Installer and Manager |
| `blenderagent-mcp.exe` | Standalone MCP Server Launcher (stdio JSON-RPC 2.0) |
| `blenderagent_bridge.zip` | Official Blender 4.2+ / 5.2 extension package |
| `SHA256SUMS.txt` | Cryptographic SHA-256 verification hashes |
