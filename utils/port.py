from __future__ import annotations

import socket
from typing import List


def find_free_port(preferred_range: tuple[int, int] | None = None, limit: int = 10) -> int:
    """Find an available TCP port on 127.0.0.1.

    Two strategies:
      1. If *preferred_range* is given (e.g. ``(8000, 9000)``), scan that
         range sequentially and return the first *limit* available ports.
         Raise ``RuntimeError`` if none found.
      2. If *preferred_range* is ``None`` (default), ask the OS to assign
         any ephemeral port via ``bind(("127.0.0.1", 0))``.

    Returns a single port number, ready to be passed to any server binding
    call.  The caller SHOULD still handle ``OSError`` / ``AddressInUse``
    at bind-time because a race is always possible.
    """
    if preferred_range is not None:
        start, end = preferred_range
        for port in range(start, end + 1):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.5)
                result = sock.connect_ex(("127.0.0.1", port))
                if result != 0:
                    return port
        raise RuntimeError(
            f"No available port in range {preferred_range} "
            f"(scanned first {limit} candidates)"
        )

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def scan_available_ports(start_port: int = 8000, end_port: int = 9000, limit: int = 10) -> List[int]:
    """Return up to *limit* available ports in [*start_port*, *end_port*]."""
    available: list[int] = []
    for port in range(start_port, end_port + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            result = sock.connect_ex(("127.0.0.1", port))
            if result != 0:
                available.append(port)
                if len(available) >= limit:
                    break
    return available
