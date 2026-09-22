"""Tabular assets: CSV for the in-app grid and Pyodide, ODS for practice on a PC.

The exam ships tasks 3, 9, 18 and 22 as ``.ods`` files, so the app offers the very
same bytes for download while using the CSV twin inside the mini-grid and the
browser Python runtime.

The OpenDocument writer here is deliberately hand-rolled. A spreadsheet produced
from a seed must be byte-identical every time — the instance's asset hash is part of
what the anti-cheat re-check compares — and a general-purpose writer stamps in
timestamps, emits namespaces in an order that depends on module-global state, and
costs a few hundred milliseconds on a thousand rows.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Sequence
from xml.sax.saxutils import escape

Cell = str | int | float | None

_FIXED_TIME = (2027, 1, 1, 0, 0, 0)
_NS = (
    'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
    'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
    'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
    'office:version="1.3"'
)
_MANIFEST = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<manifest:manifest '
    'xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" '
    'manifest:version="1.3">'
    '<manifest:file-entry manifest:full-path="/" '
    'manifest:media-type="application/vnd.oasis.opendocument.spreadsheet"/>'
    '<manifest:file-entry manifest:full-path="content.xml" '
    'manifest:media-type="text/xml"/>'
    '<manifest:file-entry manifest:full-path="styles.xml" '
    'manifest:media-type="text/xml"/>'
    "</manifest:manifest>"
)
_STYLES = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    f"<office:document-styles {_NS}></office:document-styles>"
)


def to_csv(rows: Sequence[Sequence[Cell]], *, delimiter: str = ",") -> bytes:
    """CSV without the ``csv`` module's platform-dependent line endings."""
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
    return to_ods_multi({sheet_name: rows})


def to_ods_multi(sheets: dict[str, Sequence[Sequence[Cell]]]) -> bytes:
    """An OpenDocument spreadsheet with several named sheets.

    Task 3 ships three linked tables, which is how the exam presents it.
    """
    body: list[str] = ['<?xml version="1.0" encoding="UTF-8"?>\n']
    body.append(f"<office:document-content {_NS}><office:body><office:spreadsheet>")
    for sheet_name, rows in sheets.items():
        body.append(f'<table:table table:name="{escape(sheet_name)}">')
        for row in rows:
            body.append("<table:table-row>")
            body.extend(_cell(value) for value in row)
            body.append("</table:table-row>")
        body.append("</table:table>")
    body.append("</office:spreadsheet></office:body></office:document-content>")
    content = "".join(body)

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        # The mimetype entry must come first and be stored uncompressed.
        _write(archive, "mimetype", b"application/vnd.oasis.opendocument.spreadsheet",
               compress=False)
        _write(archive, "META-INF/manifest.xml", _MANIFEST.encode("utf-8"))
        _write(archive, "styles.xml", _STYLES.encode("utf-8"))
        _write(archive, "content.xml", content.encode("utf-8"))
    return out.getvalue()


def _cell(value: Cell) -> str:
    if value is None:
        return "<table:table-cell/>"
    if isinstance(value, bool):
        flag = "true" if value else "false"
        return (
            f'<table:table-cell office:value-type="boolean" '
            f'office:boolean-value="{flag}"><text:p>{flag}</text:p></table:table-cell>'
        )
    if isinstance(value, int | float):
        return (
            f'<table:table-cell office:value-type="float" office:value="{value}">'
            f"<text:p>{value}</text:p></table:table-cell>"
        )
    text = escape(str(value))
    return (
        '<table:table-cell office:value-type="string">'
        f"<text:p>{text}</text:p></table:table-cell>"
    )


def _write(archive: zipfile.ZipFile, name: str, data: bytes, *, compress: bool = True) -> None:
    info = zipfile.ZipInfo(name, date_time=_FIXED_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    info.external_attr = 0o600 << 16
    archive.writestr(info, data)


def to_txt(lines: Sequence[str | int]) -> bytes:
    return ("\n".join(str(x) for x in lines) + "\n").encode("utf-8")


def preview(rows: Sequence[Sequence[Cell]], limit: int = 8) -> str:
    """A small Markdown table for the statement body."""
    if not rows:
        return ""
    head, *body = rows
    out = ["| " + " | ".join("" if c is None else str(c) for c in head) + " |"]
    out.append("|" + "|".join("---" for _ in head) + "|")
    for row in body[:limit]:
        out.append("| " + " | ".join("" if c is None else str(c) for c in row) + " |")
    if len(body) > limit:
        out.append(
            "| … | " + " | ".join("" for _ in head[2:]) + f" | ({len(body) - limit} строк скрыто) |"
            if len(head) > 2
            else f"| … | ({len(body) - limit} строк скрыто) |"
        )
    return "\n".join(out)
