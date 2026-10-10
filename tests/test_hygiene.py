"""
Source hygiene.

Every source file stays pure ASCII with no BOM. Non-ASCII output belongs in
escapes the language understands, not in raw bytes.

This exists because it already went wrong: editing files through PowerShell
round-trips re-encoded already-encoded bytes and added BOMs, turning a
JavaScript escape into a literal middot and then into mojibake. The viewer
rendered "Meridian League A. Harbourside" and nothing failed - the page
just quietly looked broken. ASCII-only makes that unrepresentable.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOM = bytes([0xEF, 0xBB, 0xBF])


def sources() -> list[Path]:
    out = []
    for folder in ("src", "tests", "tools"):
        for path in sorted((ROOT / folder).rglob("*.py")):
            if "__pycache__" not in path.parts:
                out.append(path)
    return out


@pytest.mark.parametrize("path", sources(), ids=lambda p: str(p.name))
def test_source_is_ascii_without_bom(path: Path):
    raw = path.read_bytes()
    assert not raw.startswith(BOM), f"{path.name} has a UTF-8 BOM"
    bad = [(i, hex(b)) for i, b in enumerate(raw) if b > 127]
    assert not bad, (
        f"{path.name} has {len(bad)} non-ASCII byte(s), "
        f"first at offset {bad[0][0]} ({bad[0][1]})"
    )
