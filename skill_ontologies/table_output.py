"""Small aligned, wrapping tables for the ontology CLI reports."""

from textwrap import wrap

# When set (record_tables), every printed table is also appended here unwrapped,
# as (title, headers, rows), for logs that keep the full cell contents.
_recorded: list[tuple[str, tuple[str, ...], list[tuple[str, ...]]]] | None = None


def record_tables(sink: list | None) -> None:
    """Start (a list) or stop (None) recording printed tables."""
    global _recorded
    _recorded = sink


def _wrap_line(line: str, width: int) -> list[str]:
    """Wrap one line, keeping its leading indent (plus two spaces) on continuation lines."""
    indent = line[: len(line) - len(line.lstrip(" "))]
    return wrap(line, width, subsequent_indent=indent + "  ", drop_whitespace=True) or [""]


def print_table(
    title: str,
    headers: tuple[str, ...],
    rows: list[tuple[str, ...]],
    max_widths: tuple[int, ...],
    record_rows: list[tuple[str, ...]] | None = None,
) -> None:
    """Print rows with aligned columns, wrapping long cell contents.

    Cells may hold several lines; indented lines stay indented when wrapped.
    record_rows, when given, is what gets recorded instead of rows (the full
    contents behind a shortened terminal display).
    When any cell spans several lines, rows are separated by a rule.
    """
    if not rows:
        return
    if _recorded is not None:
        _recorded.append((title, tuple(headers), [tuple(row) for row in (record_rows if record_rows is not None else rows)]))
    widths = [
        min(limit, max(len(header), *(len(line) for row in rows for line in (row[index].splitlines() or [""]))))
        for index, (header, limit) in enumerate(zip(headers, max_widths))
    ]
    rule = "-+-".join("-" * width for width in widths)
    multiline = any("\n" in cell for row in rows for cell in row)
    print(f"\n{title}")
    print(" | ".join(header.ljust(width) for header, width in zip(headers, widths)))
    print(rule)
    for row_index, row in enumerate(rows):
        if multiline and row_index:
            print(rule.replace("-", "·").replace("+", "·"))
        cells = [
            [part for line in (value.splitlines() or [""]) for part in _wrap_line(line, width)]
            for value, width in zip(row, widths)
        ]
        for line_index in range(max(map(len, cells))):
            print(
                " | ".join(
                    (cell[line_index] if line_index < len(cell) else "").ljust(width)
                    for cell, width in zip(cells, widths)
                )
            )
