"""Write samples/student_grades_app.zip from the sample folder (for manual upload demos)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from codemind.ingestion.zip_loader import zip_directory  # noqa: E402

if __name__ == "__main__":
    out = ROOT / "samples" / "student_grades_app.zip"
    out.write_bytes(zip_directory(ROOT / "samples" / "student_grades_app"))
    print(f"wrote {out} ({out.stat().st_size} bytes)")
