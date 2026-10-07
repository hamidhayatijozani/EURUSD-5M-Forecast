"""Autonomous, fail-closed repository supervisor for mechanical CI repair.

It may repair only a narrowly defined class of source corruption: literal
backslash-n sequences occurring outside Python string literals. It never
changes model parameters, forecasts, tests, claims, or research data.
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "research" / "autonomous_supervisor.log"


def repair_literal_newlines(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    out: list[str] = []
    changed = False
    i = 0
    quote: str | None = None
    triple = False
    escaped = False

    while i < len(text):
        ch = text[i]
        if quote is not None:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif triple:
                if text.startswith(quote * 3, i):
                    out.extend(text[i + 1:i + 3])
                    i += 2
                    quote = None
                    triple = False
            elif ch == quote:
                quote = None
            i += 1
            continue

        if text.startswith('"""', i) or text.startswith("'''", i):
            quote = text[i]
            triple = True
            out.append(text[i:i + 3])
            i += 3
            continue
        if ch in {'"', "'"}:
            quote = ch
            triple = False
            out.append(ch)
            i += 1
            continue

        if ch == "\\" and i + 1 < len(text) and text[i + 1] == "n":
            out.append("\n")
            changed = True
            i += 2
            continue

        out.append(ch)
        i += 1

    if changed:
        path.write_text("".join(out), encoding="utf-8")
    return changed


def compile_tree() -> tuple[bool, str]:
    proc = subprocess.run(
        ["python", "-m", "compileall", "-q", "scripts", "engine", "claimlab", "tests"],
        cwd=ROOT, text=True, capture_output=True,
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()


def main() -> int:
    ok, detail = compile_tree()
    repaired = False
    target = ROOT / "scripts" / "live_minute_loop.py"
    if not ok and target.exists():
        repaired = repair_literal_newlines(target)
        if repaired:
            ok, detail = compile_tree()

    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    status = "PASS" if ok else "FAIL"
    AUDIT.write_text(
        f"status={status}\nrepaired_literal_newlines={repaired}\n"
        f"compile_detail={detail}\n",
        encoding="utf-8",
    )
    if not ok:
        print(detail)
        return 1
    print(f"AUTONOMOUS_SUPERVISOR_{status}: repaired={repaired}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
