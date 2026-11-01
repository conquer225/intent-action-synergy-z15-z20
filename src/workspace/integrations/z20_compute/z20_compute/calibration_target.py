"""A4 calibration target matching the stereo calibrator's inner-corner contract."""

import argparse
from math import isfinite
from pathlib import Path


def a4_checkerboard_svg(*, columns=9, rows=6, square_mm=25, margin_mm=10):
    """Return a landscape A4 SVG with physical-size chessboard squares.

    ``columns`` and ``rows`` count inner corners, as in OpenCV's
    ``findChessboardCornersSB``. Print at 100% and measure a square before
    using its size to establish stereo depth in metres.
    """
    if (type(columns) is not int or type(rows) is not int or min(columns, rows) < 3
            or not isfinite(square_mm) or square_mm <= 0
            or not isfinite(margin_mm) or margin_mm < 0):
        raise ValueError("invalid inner-corner count, square size, or margin")
    board_width = (columns + 1) * square_mm
    board_height = (rows + 1) * square_mm
    if board_width + 2 * margin_mm > 297 or board_height + 2 * margin_mm > 210:
        raise ValueError("checkerboard does not fit landscape A4 with margin")
    left = (297 - board_width) / 2
    top = (210 - board_height) / 2
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="297mm" height="210mm" '
        'viewBox="0 0 297 210">',
        '<rect x="0" y="0" width="297" height="210" fill="white"/>',
    ]
    for row in range(rows + 1):
        for column in range(columns + 1):
            if (row + column) % 2 == 0:
                x = left + column * square_mm
                y = top + row * square_mm
                parts.append(
                    f'<rect x="{x:g}" y="{y:g}" width="{square_mm:g}" '
                    f'height="{square_mm:g}" fill="black"/>'
                )
    parts.append('</svg>')
    return '\n'.join(parts) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create a printable stereo checkerboard")
    parser.add_argument("output", type=Path)
    parser.add_argument("--columns", type=int, default=9, help="inner corners")
    parser.add_argument("--rows", type=int, default=6, help="inner corners")
    parser.add_argument("--square-mm", type=float, default=25)
    args = parser.parse_args(argv)
    args.output.write_text(a4_checkerboard_svg(
        columns=args.columns, rows=args.rows, square_mm=args.square_mm), encoding="utf-8")


if __name__ == "__main__":
    main()
