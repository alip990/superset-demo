"""Generate calendar anchors with two independent development libraries."""
from pathlib import Path
import jdatetime
from persiantools.jdatetime import JalaliDate

def generate():
    rows = {}
    for year in range(1350, 1552):
        a = jdatetime.date(year, 1, 1).togregorian()
        b = JalaliDate(year, 1, 1).to_gregorian()
        if a != b:
            raise RuntimeError(f"Calendar libraries disagree for {year}: {a} != {b}")
        rows[year] = a.isoformat()
    assert rows[1403] == "2024-03-20"
    assert rows[1404] == "2025-03-21"
    assert rows[1405] == "2026-03-21"
    assert jdatetime.date(1403,12,30).togregorian().isoformat() == "2025-03-20"
    assert JalaliDate(1403,12,30).to_gregorian().isoformat() == "2025-03-20"
    target = Path(__file__).resolve().parents[1] / "src/superset_jalali_sql/nowruz.py"
    target.write_text("# Generated, do not edit. Run scripts/generate_nowruz.py.\nNOWRUZ = {\n" + "".join(f"    {y}: {d!r},\n" for y,d in rows.items()) + "}\n")

if __name__ == "__main__":
    generate()
