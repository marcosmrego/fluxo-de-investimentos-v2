"""Safe command-line surfaces for investment audit artifacts."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
from typing import Any

from investment_audit.catalog.backup_manifest import create_manifest, verify_manifest, write_manifest
from investment_audit.catalog.schema_export import write_catalog


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only investment audit tools")
    commands = parser.add_subparsers(dest="command", required=True)

    catalog = commands.add_parser(
        "catalog-export", help="export PostgreSQL catalog metadata", allow_abbrev=False
    )
    catalog.add_argument(
        "--dsn-env", default="DATABASE_URL", metavar="NAME",
        help="name of the environment variable containing the DSN (default: DATABASE_URL)",
    )
    catalog.add_argument("--output", required=True)
    catalog.add_argument("--execute", action="store_true", help="connect and write the export")

    manifest = commands.add_parser("backup-manifest", help="hash existing dump files")
    manifest.add_argument("files", nargs="+")
    manifest.add_argument("--base-dir", required=True)
    manifest.add_argument("--output", required=True)
    manifest.add_argument("--execute", action="store_true", help="write the manifest")

    verify = commands.add_parser("backup-verify", help="verify files against a manifest")
    verify.add_argument("manifest")
    verify.add_argument("--base-dir", required=True)
    return parser


def _default_connect(dsn: str) -> Any:
    import psycopg2

    return psycopg2.connect(dsn)


def main(argv: Sequence[str] | None = None, *, connect: Callable[[str], Any] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "catalog-export":
        if not args.execute:
            print(json.dumps({"command": args.command, "dry_run": True, "output": args.output}))
            return 0
        try:
            dsn = os.environ.get(args.dsn_env)
            if not dsn:
                raise RuntimeError("database connection environment is not configured")
            connection = (connect or _default_connect)(dsn)
            try:
                result = write_catalog(connection, args.output)
            finally:
                connection.close()
        except Exception:
            # Driver exceptions may reproduce a DSN. Keep credentials out of CLI output.
            print("catalog export failed", file=sys.stderr)
            return 2
        print(json.dumps({"written": args.output, "sha256": result["sha256"]}))
        return 0

    if args.command == "backup-manifest":
        if args.execute:
            manifest = write_manifest(args.files, args.output, base_dir=args.base_dir)
        else:
            manifest = create_manifest(args.files, base_dir=args.base_dir)
        print(json.dumps({
            "command": args.command,
            "dry_run": not args.execute,
            "file_count": len(manifest["files"]),
            **({"written": args.output} if args.execute else {}),
        }))
        return 0

    result = verify_manifest(args.manifest, base_dir=args.base_dir)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
