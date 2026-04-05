"""Install vector-graph Claude Code hook.

Usage:
    vector-graph --install-hook

Creates ~/.claude/hooks/vector-graph-check.sh and prints the settings.json
snippet to add. Does NOT modify settings.json (user should review and add).
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

HOOK_SCRIPT = r'''#!/bin/bash
# vector-graph PreToolUse hook — checks file risk before Edit/Write
# Queries the running vector-graph server at localhost:5555
# Outputs NOTHING for LOW/MEDIUM (0 token cost)
# Outputs 1-line warning for HIGH/CRITICAL (~30 tokens)
# Fails silently if server is not running

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin);print(d.get('input',{}).get('file_path',''))
except:
    pass
" 2>/dev/null)

[ -z "$FILE_PATH" ] && exit 0

REL_PATH=$(echo "$FILE_PATH" | rev | cut -d'/' -f1-3 | rev)
RESULT=$(curl -s --max-time 1 "http://127.0.0.1:5555/api/quick-check?file=${REL_PATH}" 2>/dev/null)
[ -z "$RESULT" ] && exit 0

RISK=$(echo "$RESULT" | python3 -c "import sys,json;print(json.load(sys.stdin).get('risk','LOW'))" 2>/dev/null)

if [ "$RISK" = "CRITICAL" ] || [ "$RISK" = "HIGH" ]; then
    DEPS=$(echo "$RESULT" | python3 -c "import sys,json;print(json.load(sys.stdin).get('dependents',0))" 2>/dev/null)
    echo "[vector-graph] $(basename $FILE_PATH): ${RISK} risk (${DEPS} dependents). Run tests after."
fi
exit 0
'''

SETTINGS_SNIPPET = '''{
  "matcher": "Edit|Write",
  "hooks": [
    {
      "type": "command",
      "command": "bash ~/.claude/hooks/vector-graph-check.sh",
      "timeout": 3,
      "statusMessage": "Checking impact..."
    }
  ]
}'''


def install_hook() -> None:
    """Install the vector-graph Claude Code hook."""
    hook_dir = Path.home() / ".claude" / "hooks"
    hook_dir.mkdir(parents=True, exist_ok=True)

    hook_path = hook_dir / "vector-graph-check.sh"
    hook_path.write_text(HOOK_SCRIPT)
    hook_path.chmod(hook_path.stat().st_mode | stat.S_IEXEC)

    print(f"Hook installed: {hook_path}")
    print()
    print("Add this to your ~/.claude/settings.json under hooks.PreToolUse:")
    print()
    print(SETTINGS_SNIPPET)
    print()
    print("Or run: vector-graph --install-hook --auto")


def install_hook_auto() -> None:
    """Install hook AND auto-configure settings.json."""
    import json

    install_hook()

    settings_path = Path.home() / ".claude" / "settings.json"
    if not settings_path.exists():
        print(f"Settings file not found: {settings_path}")
        return

    settings = json.loads(settings_path.read_text())

    hook_entry = {
        "matcher": "Edit|Write",
        "hooks": [
            {
                "type": "command",
                "command": "bash ~/.claude/hooks/vector-graph-check.sh",
                "timeout": 3,
                "statusMessage": "Checking impact...",
            }
        ],
    }

    hooks = settings.setdefault("hooks", {})
    pre_tool = hooks.setdefault("PreToolUse", [])

    # Check if already installed
    for entry in pre_tool:
        if any("vector-graph" in (h.get("command", "") ) for h in entry.get("hooks", [])):
            print("Hook already configured in settings.json.")
            return

    pre_tool.append(hook_entry)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    print(f"Settings updated: {settings_path}")
