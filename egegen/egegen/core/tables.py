"""Tabular assets: CSV for the in-app grid and Pyodide, ODS for practice on a PC.

The exam ships tasks 3, 9, 18 and 22 as ``.ods`` files, so the app offers the very
same bytes for download while using the CSV twin inside the mini-grid and the
browser Python runtime.
"""

from __future__ import annotations

import io
from collections.abc import Sequence

from odf.opendocument import OpenDocumentSpreadsheet
from odf.table import Table, TableCell, TableRow
from odf.text import P

Cell = str | int | float | None


def to_csv(rows: Sequence[Sequence[Cell]], *, delimiter: str = ",") -> bytes:
    """CSV without the ``csv`` module's platform-dependent line endings.

    Byte-identical output for a given seed matters: the instance's asset hash is part
    of what the anti-cheat re-check compares.
    """
    out: list[str] = []
    for row in rows:
        cells: list[str] = []
        for value in row:
            if value is None:
                cells.append("")
            else:
                text = str(value)
                if delimiter in text or '"' in text or "\n" in text:
                    text = '"' + text.replace('"', '""') + '"'
                cells.append(text)
        out.append(delimiter.join(cells))
    return ("\n".join(out) + "\n").encode("utf-8")


def to_ods(rows: Sequence[Sequence[Cell]], *, sheet_name: str = "Лист1") -> bytes:
    """An OpenDocument spreadsheet holding one sheet of ``rows``."""
    doc = OpenDocumentSpreadsheet()
    table = Table(name=sheet_name)
    for row in rows:
        tr = TableRow()
        for value in row:
            if value is None:
                tc = TableCell()
            elif isinstance(value, bool):
                tc = TableCell(valuetype="boolean", booleanvalue=value)
            elif isinstance(value, int | float):
                tc = TableCell(valuetype="float", value=value)
                tc.addElement(P(text=str(value)))
            else:
                tc = TableCell(valuetype="string")
                tc.addElement(P(text=str(value)))
            tr.addElement(tc)
        table.addElement(tr)
    doc.spreadsheet.addElement(table)
    buffer = io.BytesIO()
    doc.write(buffer)
    return buffer.getvalue()


def to_txt(lines: Sequence[str | int]) -> bytes:
    return ("\n".join(str(x) for x in lines) + "\n").encode("utf-8")


def preview(rows: Sequence[Sequence[Cell]], limit: int = 8) -> str:
    """A small Markdown table for the statement body."""
    if not rows:
        return ""
    head, *body = rows
    widths = [str(c) if c is not None else "" for c in head]
    out = ["| " + " | ".join(widths) + " |"]
    out.append("|" + "|".join("---" for _ in head) + "|")
    for row in body[:limit]:
        out.append("| " + " | ".join("" if c is None else str(c) for c in row) + " |")
    if len(body) > limit:
        out.append(f"| … | ({len(body) - limit} строк скрыто) |" if len(head) > 1 else "| … |")
    return "\n".join(out)
