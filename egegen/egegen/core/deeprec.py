"""Running deep recursion safely.

``sys.setrecursionlimit`` raises CPython's *counter*, not the actual C stack, so a
few thousand frames still overflow. Running the call on a thread with a large stack
is the portable way out, and it is what the method card tells students to do when
the iterative rewrite is not obvious.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable

STACK_BYTES = 64 * 1024 * 1024
RECURSION_LIMIT = 200_000


def run_deep[T](fn: Callable[[], T]) -> T:
    """Call ``fn`` on a thread with a 64 MB stack and a raised recursion limit."""
    previous_limit = sys.getrecursionlimit()
    previous_stack = threading.stack_size()
    result: list[T] = []
    error: list[BaseException] = []

    def target() -> None:
        try:
            result.append(fn())
        except BaseException as exc:
            error.append(exc)

    sys.setrecursionlimit(RECURSION_LIMIT)
    threading.stack_size(STACK_BYTES)
    try:
        worker = threading.Thread(target=target)
        worker.start()
        worker.join()
    finally:
        threading.stack_size(previous_stack)
        sys.setrecursionlimit(previous_limit)
    if error:
        raise error[0]
    return result[0]
