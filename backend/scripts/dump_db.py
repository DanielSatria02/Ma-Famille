"""A plain SQL dump of the database, written to stdout.

The production VM has no `pg_dump`, and it cannot pull the postgres image
either: it has egress but no working resolver, and a pull needs a name. So
the backup is taken from inside a container that is already talking to the
database, with nothing but psycopg.

    podman exec -i <container> python - < dump_db.py > db.sql

The script is self-contained on purpose. It is fed to whatever python is in
the container, so it cannot rely on the application code that happens to be
installed there — the container is often running the previous release.
"""

from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any

import psycopg

SQL_TYPES = {
    "bigint": "bigint",
    "boolean": "boolean",
    "character varying": "text",
    "date": "date",
    "double precision": "double precision",
    "integer": "integer",
    "json": "json",
    "jsonb": "jsonb",
    "numeric": "numeric",
    "text": "text",
    "time without time zone": "time",
    "timestamp with time zone": "timestamptz",
    "timestamp without time zone": "timestamp",
    "uuid": "uuid",
}


def quote(value: Any) -> str:
    """A value as SQL text."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return "'" + value.isoformat() + "'"
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "'\\x" + bytes(value).hex() + "'"
    if isinstance(value, (dict, list, tuple)):
        import json

        return "'" + json.dumps(value, default=str).replace("'", "''") + "'"
    return "'" + str(value).replace("'", "''") + "'"


def main() -> int:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    # The application writes the driver in the URL; psycopg wants the plain one.
    url = url.replace("postgresql+psycopg://", "postgresql://")

    out = sys.stdout
    with psycopg.connect(url, connect_timeout=15) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' ORDER BY tablename"
            )
            tables = [row[0] for row in cursor.fetchall()]

            out.write("-- A dump of the Ma-Famille database.\n")
            out.write(f"-- Tables: {len(tables)}\n\n")

            for table in tables:
                cursor.execute(
                    "SELECT column_name, data_type, is_nullable, column_default "
                    "FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = %s "
                    "ORDER BY ordinal_position",
                    (table,),
                )
                column_info = cursor.fetchall()
                columns = [row[0] for row in column_info]

                cursor.execute(f'SELECT * FROM "{table}"')
                rows = cursor.fetchall()
                names = [column.name for column in cursor.description or []]

                # The column types, so the table can be created from scratch.
                out.write(f"CREATE TABLE IF NOT EXISTS {table} (\n")
                definitions = []
                for name, data_type, nullable, default in column_info:
                    if default is not None and "nextval" in str(default):
                        # SERIAL is a type of its own, not an addition.
                        piece = f'"{name}" SERIAL'
                    else:
                        piece = f'"{name}" {SQL_TYPES.get(data_type, "text")}'
                        if default is not None and str(default) != "":
                            piece += f" DEFAULT {default}"
                    if nullable == "NO":
                        piece += " NOT NULL"
                    definitions.append(piece)
                out.write(",\n    ".join(definitions))
                out.write("\n);\n")

                if rows:
                    out.write(f"DELETE FROM {table};\n")
                    column_list = ", ".join(f'"{name}"' for name in names)
                    out.write(f"INSERT INTO {table} ({column_list}) VALUES\n")
                    values = ",\n    ".join(
                        "(" + ", ".join(quote(value) for value in row) + ")" for row in rows
                    )
                    out.write("    " + values + ";\n")
                out.write("\n")

                # The sequence behind the id: without it the ids start over
                # and collide with the rows that were just inserted. Not every
                # table has an id — the migration table does not, and asking
                # for the sequence of a column that is not there is an error.
                sequence = None
                if "id" in columns:
                    cursor.execute("SELECT pg_get_serial_sequence(%s, 'id')", (table,))
                    sequence = cursor.fetchone()[0]
                if sequence:
                    out.write(
                        f"SELECT setval('{sequence}', "
                        f"COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false);\n\n"
                    )

    out.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
