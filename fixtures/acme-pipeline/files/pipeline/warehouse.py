"""The warehouse connection and the few operations the loaders and the runner need.

The database driver comes with the scheduler image (module `warehouse_driver`); nothing here runs without it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pipeline.config import settings


def connect() -> Any:
    import warehouse_driver  # shipped with the scheduler image

    return warehouse_driver.connect(settings.WAREHOUSE_DSN, application_name="acme-pipeline")


def run_sql(path: str, params: dict[str, str]) -> int:
    """Run one SQL file with named parameters such as :load_date and return the rows it wrote."""
    sql = Path(path).read_text(encoding="utf-8")
    total = 0
    with connect() as connection:
        cursor = connection.cursor()
        for statement in [part for part in sql.split(";") if part.strip()]:
            cursor.execute(statement, params)
            total += max(cursor.rowcount, 0)
        connection.commit()
    return total


def query(sql: str, params: dict[str, str]) -> list[tuple[Any, ...]]:
    with connect() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, params)
        return list(cursor.fetchall())


def replace_partition(table: str, column: str, value: str, rows: list[dict[str, str]]) -> None:
    """Delete the rows of one load date from a bronze table and insert the delivered rows as text."""
    with connect() as connection:
        cursor = connection.cursor()
        cursor.execute(f"delete from {table} where {column} = :value", {"value": value})
        if rows:
            columns = [*rows[0], column]
            marks = ", ".join(f":{name}" for name in columns)
            cursor.executemany(
                f"insert into {table} ({', '.join(columns)}) values ({marks})",
                [{**row, column: value} for row in rows],
            )
        connection.commit()
