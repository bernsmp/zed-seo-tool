---
name: zed-seo-setup
description: >
  Set up the Zed SEO Cowork workspace and verify the official Semrush connector.
  Use when Carlos says "set up Zed SEO", "install the SEO tool", "connect
  Semrush", "first run", or when another Zed SEO skill finds no workspace marker.
metadata:
  version: "0.1.0"
---

# Set Up Zed SEO

Make the current Cowork Project folder the durable workspace. Do not create or store any API key.

## 1. Confirm the project folder

Use the folder attached to the current Cowork Project. It must be a dedicated Zed SEO folder, not Carlos's home folder or a broad company drive. Refer to it as `$WORKSPACE` in this skill, but substitute its actual absolute path in every command. Never execute an unset shell variable.

If no folder is attached, stop and ask Carlos to create a dedicated Cowork Project from the included workspace template.

## 2. Initialize durable state

Run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/jobctl.py" init --workspace "$WORKSPACE"
```

Confirm that `clients`, `imports`, `jobs`, `exports`, and `incidents` exist and that `.zed-seo-workspace.json` was created.

## 3. Verify SEMrush

Check that the verified **Semrush** connector from Claude's connector directory is enabled. Use it for one small, read-only query against a domain Carlos names. Report the exact domain, database, and number of rows returned.

If the connector is unavailable, direct Carlos to **Customize → Connectors → Semrush → Connect**. Do not ask for an API key and do not use a key pasted into chat.

## 4. Run the workspace doctor

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/jobctl.py" doctor --workspace "$WORKSPACE"
```

## 5. Close

State:

- workspace path;
- connector status;
- number of client profiles;
- incomplete jobs, if any;
- the next action, normally creating the first client profile.
