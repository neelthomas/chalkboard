"""
fix_encoding.py - keep the source tree pure ASCII.

Editing files through PowerShell round-trips (Get-Content -Raw |
Set-Content -Encoding utf8) re-encodes already-encoded bytes and adds BOMs.
A JavaScript escape became a literal middot, then mojibake, and the page
rendered "Meridian League A. Harbourside".

Chasing the bytes is the wrong fix. Keeping every source file ASCII is the
right one, because then no round-trip through any tool can corrupt
anything. Non-ASCII output belongs in escapes the language understands.

    python tools/fix_encoding.py           strip BOMs, repair known damage
    python tools/fix_encoding.py --check   report only, non-zero if dirty
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ("src", "tests", "tools")

BACKSLASH = chr(92)

# Mojibake seen in the wild -> the ASCII escape that means the same thing.
REPAIRS = {
    bytes([0xC3, 0x82, 0xC2, 0xB7]): (BACKSLASH + "u00b7").encode(),
    bytes([0xC2, 0xB7]): (BACKSLASH + "u00b7").encode(),
    bytes([0xC3, 0xA2, 0xC2, 0x80, 0xC2, 0x93]): (BACKSLASH + "u2013").encode(),
    bytes([0xE2, 0x80, 0x93]): (BACKSLASH + "u2013").encode(),
}

BOM = bytes([0xEF, 0xBB, 0xBF])


def sources():
    for folder in TARGETS:
        for path in sorted((ROOT / folder).rglob("*.py")):
            if "__pycache__" not in path.parts:
                yield path


def main() -> int:
    check_only = "--check" in sys.argv
    dirty = 0

    for path in sources():
        original = path.read_bytes()
        raw = original

        if raw.startswith(BOM):
            raw = raw[len(BOM):]
        for broken, fixed in REPAIRS.items():
            raw = raw.replace(broken, fixed)

        leftover = [(i, hex(b)) for i, b in enumerate(raw) if b > 127]
        rel = path.relative_to(ROOT)

        if leftover:
            dirty += 1
            print(f"  {rel}: {len(leftover)} non-ASCII byte(s), "
                  f"first at offset {leftover[0][0]} ({leftover[0][1]})")
        elif raw != original:
            dirty += 1
            print(f"  {rel}: repaired")

        if raw != original and not check_only:
            path.write_bytes(raw)

    if not dirty:
        print("  clean: all source files are ASCII with no BOM")
    return 1 if (check_only and dirty) else 0


if __name__ == "__main__":
    raise SystemExit(main())
