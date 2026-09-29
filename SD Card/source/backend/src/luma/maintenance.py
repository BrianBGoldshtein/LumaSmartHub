"""Operator-only backup/restore. Backups contain private OAuth tokens."""
import argparse
import os
from pathlib import Path

from .storage import Storage


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["backup", "restore", "check"])
    parser.add_argument("--data-dir", default=os.environ.get("LUMA_DATA_DIR", "/var/lib/luma"))
    parser.add_argument("--file", type=Path)
    parser.add_argument("--offline", action="store_true", help="Confirm all Luma services have been stopped before restore")
    args = parser.parse_args()
    if args.operation != "check" and not args.file:
        parser.error("--file is required")
    if args.operation == "restore" and not args.offline:
        parser.error("Stop Luma services, then pass --offline to restore")
    database = Path(args.data_dir) / "luma.db"
    if not database.is_file():
        parser.error("The Luma database does not exist")
    storage = Storage(database)
    if args.operation == "backup":
        storage.backup(args.file)
        print("Backup verified. It contains private account tokens: keep it secure.")
    elif args.operation == "restore":
        storage.restore(args.file.resolve())
        print("Backup restored. Restart Luma; phone presence must be proven again.")
    else:
        if not storage.integrity_check():
            raise SystemExit("Database integrity check failed")
        print("Database integrity: ok")


if __name__ == "__main__":
    main()
