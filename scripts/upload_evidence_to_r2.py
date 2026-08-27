"""One-time (or repeatable) upload: pushes every file in
data/real_docs/SandBox-FI/checks/ to the configured Cloudflare R2
bucket, using the same relative-from-repo-root path as its object key --
exactly what match_receipts.py already writes into each transaction's
evidence_file column, so no database changes are needed after this runs.
Safe to re-run any time new checks are added; re-uploading a key just
overwrites it.

Usage:
  python scripts/upload_evidence_to_r2.py
"""
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "tools"))
import r2  # noqa: E402

CHECKS_DIR = ROOT / "data" / "real_docs" / "SandBox-FI" / "checks"


def main():
    if not r2.is_configured():
        print("R2_ACCOUNT_ID (and friends) are not set in .env -- nothing to do.")
        sys.exit(1)

    files = sorted(p for p in CHECKS_DIR.glob("**/*") if p.is_file())
    print(f"Uploading {len(files)} file(s) to R2...")
    for i, path in enumerate(files, 1):
        key = str(path.relative_to(ROOT)).replace("\\", "/")
        r2.upload_object(key, path.read_bytes())
        if i % 20 == 0 or i == len(files):
            print(f"  {i}/{len(files)}")
    print("Done.")


if __name__ == "__main__":
    main()
