"""Deterministic, read-only PostgreSQL schema introspection."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


CATALOG_QUERIES = {
    "tables": """SELECT /* tables */ n.nspname AS schema, c.relname AS name, c.relpersistence AS persistence,
               pg_get_userbyid(c.relowner) AS owner
        FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind IN ('r','p','f') AND n.nspname NOT IN ('pg_catalog','information_schema')""",
    "columns": """SELECT /* columns */ table_schema AS schema, table_name, column_name AS name,
               ordinal_position AS position, data_type, udt_schema, udt_name,
               is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema NOT IN ('pg_catalog','information_schema')""",
    "constraints": """SELECT /* constraints */ n.nspname AS schema, c.relname AS table_name, x.conname AS name,
               x.contype AS type, pg_catalog.pg_get_constraintdef(x.oid, true) AS definition
        FROM pg_catalog.pg_constraint x JOIN pg_catalog.pg_class c ON c.oid=x.conrelid
        JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname NOT IN ('pg_catalog','information_schema')""",
    "indexes": """SELECT /* indexes */ schemaname AS schema, tablename AS table_name, indexname AS name, indexdef AS definition
        FROM pg_catalog.pg_indexes WHERE schemaname NOT IN ('pg_catalog','information_schema')""",
    "triggers": """SELECT /* triggers */ n.nspname AS schema, c.relname AS table_name, t.tgname AS name,
               pg_catalog.pg_get_triggerdef(t.oid, true) AS definition
        FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
        JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        WHERE NOT t.tgisinternal AND n.nspname NOT IN ('pg_catalog','information_schema')""",
    "views": """SELECT /* views */ schemaname AS schema, viewname AS name, viewowner AS owner, definition
        FROM pg_catalog.pg_views WHERE schemaname NOT IN ('pg_catalog','information_schema')""",
    "sequences": """SELECT /* sequences */ schemaname AS schema, sequencename AS name, sequenceowner AS owner,
               data_type, start_value, min_value, max_value, increment_by, cycle, cache_size
        FROM pg_catalog.pg_sequences WHERE schemaname NOT IN ('pg_catalog','information_schema')""",
    "functions": """SELECT /* functions */ n.nspname AS schema, p.proname AS name,
               pg_catalog.pg_get_function_identity_arguments(p.oid) AS arguments,
               pg_catalog.pg_get_userbyid(p.proowner) AS owner,
               pg_catalog.pg_get_functiondef(p.oid) AS definition
        FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname NOT IN ('pg_catalog','information_schema')""",
    "extensions": """SELECT /* extensions */ e.extname AS name, e.extversion AS version, n.nspname AS schema,
               pg_catalog.pg_get_userbyid(e.extowner) AS owner
        FROM pg_catalog.pg_extension e JOIN pg_catalog.pg_namespace n ON n.oid=e.extnamespace""",
    "owners": """SELECT /* owners */ n.nspname AS schema, c.relname AS object_name, c.relkind AS object_type,
               pg_catalog.pg_get_userbyid(c.relowner) AS owner
        FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname NOT IN ('pg_catalog','information_schema')""",
    "grants": """SELECT /* grants */ table_schema AS schema, table_name AS object_name, 'table' AS object_type,
               grantor, grantee, privilege_type, is_grantable
        FROM information_schema.table_privileges
        WHERE table_schema NOT IN ('pg_catalog','information_schema')
        UNION ALL
        SELECT routine_schema, routine_name, 'routine', grantor, grantee, privilege_type, is_grantable
        FROM information_schema.routine_privileges
        WHERE routine_schema NOT IN ('pg_catalog','information_schema')""",
}


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return value.hex()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def export_catalog(connection: Any) -> dict[str, Any]:
    """Read catalog metadata using an existing DB-API connection; never commits."""
    cursor = connection.cursor()
    catalog: dict[str, list[dict[str, Any]]] = {}
    try:
        for section, sql in CATALOG_QUERIES.items():
            cursor.execute(sql)
            columns = [item[0] for item in cursor.description]
            rows = [dict(zip(columns, (_json_value(value) for value in row))) for row in cursor.fetchall()]
            catalog[section] = sorted(rows, key=lambda row: _canonical(row))
    finally:
        cursor.close()
    return {"catalog": catalog, "sha256": hashlib.sha256(_canonical(catalog)).hexdigest()}


def write_catalog(connection: Any, output: str | Path) -> dict[str, Any]:
    result = export_catalog(connection)
    Path(output).write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return result
