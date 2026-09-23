"""Importing this package registers every task generator.

Each module calls :func:`egegen.core.registry.register` at import time, so a plain
``import egegen.generators`` is enough to make all 27 available.
"""

from egegen.generators import (  # noqa: F401  (the import is the registration)
    t01,
    t02,
    t03,
    t04,
    t05,
    t06,
    t07,
    t08,
    t09,
    t10,
    t11,
    t12,
    t13,
    t14,
    t15,
    t16,
    t17,
    t18,
    t19,
    t20,
    t21,
    t22,
    t23,
    t24,
    t25,
    t26,
    t27,
)

__all__ = [f"t{n:02d}" for n in range(1, 28)]
