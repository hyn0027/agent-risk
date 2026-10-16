"""Small aligned, wrapping tables for the ontology CLI reports."""

from textwrap import wrap


def _wrap_line(line: str, width: int) -> list[str]:
    """Wrap one line, keeping its leading indent (plus two spaces) on continuation lines."""
    indent = line[: len(line) - len(line.lstrip(" "))]
    return wrap(line, width, subsequent_indent=indent + "  ", drop_whitespace=True) or [""]


def print_table(
    title: str,
    headers: tuple[str, ...],
    rows: list[tuple[str, ...]],
    max_widths: tuple[int, ...],
) -> None:
    """Print rows with aligned columns, wrapping long cell contents.

    Cells may hold several lines; indented lines stay indented when wrapped.
    When any cell spans several lines, rows are separated by a rule.
    """
    if not rows:
        return
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
