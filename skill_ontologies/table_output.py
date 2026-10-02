"""Small aligned, wrapping tables for the ontology CLI reports."""

from textwrap import wrap


def print_table(
    title: str,
    headers: tuple[str, ...],
    rows: list[tuple[str, ...]],
    max_widths: tuple[int, ...],
) -> None:
    """Print rows with aligned columns, wrapping long cell contents."""
    if not rows:
        return
    widths = [
        min(limit, max(len(header), *(len(row[index]) for row in rows)))
        for index, (header, limit) in enumerate(zip(headers, max_widths))
    ]
    print(f"\n{title}")
    print(" | ".join(header.ljust(width) for header, width in zip(headers, widths)))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        cells = [
            [part for line in (value.splitlines() or [""]) for part in (wrap(line, width) or [""])]
            for value, width in zip(row, widths)
        ]
        for line_index in range(max(map(len, cells))):
            print(
                " | ".join(
                    (cell[line_index] if line_index < len(cell) else "").ljust(width)
                    for cell, width in zip(cells, widths)
                )
            )
