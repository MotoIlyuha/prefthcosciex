"""Importing this package registers every task generator.

Order follows the design doc's build order (16.5) rather than the exam numbering,
so a partially built package still imports cleanly.
"""

from egegen.generators import t01, t02, t04, t05, t07, t08, t11  # noqa: F401

__all__ = ["t01", "t02", "t04", "t05", "t07", "t08", "t11"]
