#!/usr/bin/env python3
"""Inject project_state.json (the SSOT) into index.html's `const STATE = {...};` block.

Run this after editing project_state.json so the rendered dashboard matches the
single source of truth. Without it, the page keeps its stale embedded copy.

    python3 build.py
"""
import json
import re
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
STATE_JSON = DIR / "project_state.json"
INDEX_HTML = DIR / "index.html"


def main() -> int:
    # Parsing here also validates the JSON; a syntax error aborts before writing.
    state = json.loads(STATE_JSON.read_text(encoding="utf-8"))
    html = INDEX_HTML.read_text(encoding="utf-8")

    payload = "const STATE = " + json.dumps(state, ensure_ascii=False, indent=2) + ";"

    # Non-greedy match stops at the first line-start `};`. json.dumps(indent=2)
    # never emits a nested `};` (nested closes are `}` / `},`), so this is the
    # outermost terminator only.
    new_html, n = re.subn(
        r"const STATE = \{[\s\S]*?\n\};",
        lambda _m: payload,        # function replacer: avoids backslash/group-ref issues
        html,
        count=1,
    )
    if n != 1:
        print(f"ERROR: expected exactly 1 STATE block, replaced {n}. Aborting.", file=sys.stderr)
        return 1

    INDEX_HTML.write_text(new_html, encoding="utf-8")
    print(f"OK: injected project_state.json into index.html ({len(payload)} chars, updated {state['meta']['updated']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
