"""Audit PACKAGE_PIN ownership across Navigator constraint files."""

import re
from pathlib import Path


_PORT = re.compile(r"\[get_ports\s+(?:\{([^}]+)\}|([^\]\s]+))\]")
_DICT_PIN = re.compile(r"\bPACKAGE_PIN\s+([A-Z][0-9]+)\b")


def _assignments(lines):
    for line in lines:
        line = line.split("#", 1)[0].strip()
        if not line or "PACKAGE_PIN" not in line:
            continue
        port = _PORT.search(line)
        pin = _DICT_PIN.search(line)
        if not port or not pin:
            raise ValueError("Unrecognized PACKAGE_PIN constraint: " + line)
        yield port.group(1) or port.group(2), pin.group(1)


def read_package_pins(path):
    """Return package-pin assignments from a vendor-style or local XDC."""
    path = Path(path)
    values = {}
    for port, pin in _assignments(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        if port in values and values[port] != pin:
            raise ValueError("Conflicting assignments for " + port)
        values[port] = pin
    return values


def audit_constraints(paths, *, extra_lines=(), required_ports=(), assignments=None):
    """Report package-pin collisions and missing required ports."""
    entries = []
    for path in paths:
        path = Path(path)
        entries.extend(_assignments(path.read_text(encoding="utf-8", errors="replace").splitlines()))
    entries.extend(_assignments(extra_lines))
    if assignments is not None:
        entries.extend(assignments.items())
    by_pin = {}
    by_port = {}
    problems = []
    for port, pin in entries:
        if pin in by_pin and by_pin[pin] != port:
            problems.append(f"PACKAGE_PIN {pin}: {by_pin[pin]} conflicts with {port}")
        if port in by_port and by_port[port] != pin:
            problems.append(f"port {port}: {by_port[port]} conflicts with {pin}")
        by_pin[pin] = port
        by_port[port] = pin
    for port in sorted(set(required_ports) - set(by_port)):
        problems.append(f"missing required port {port}")
    return problems
