"""Importing this package registers every task generator.

Order follows the design doc's build order (16.5) rather than the exam numbering,
so a partially built package still imports cleanly.
"""

from egegen.generators import t01, t02, t04, t05, t07, t08, t10, t11, t12, t13, t14, t16, t19, t20, t21, t22  # noqa: F401

__all__ = ["t01", "t02", "t04", "t05", "t07", "t08", "t10", "t11", "t12", "t13", "t14", "t16", "t19", "t20", "t21", "t22"]
