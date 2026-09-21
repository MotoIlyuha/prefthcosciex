"""Procedural task generators for the Russian EGE-2027 informatics exam.

Every task instance is a pure function of its seed: the same seed always yields
byte-identical statements, attachments and answers. There are no static task
banks anywhere in this package.
"""

from egegen.core.registry import get_generator, list_generators, registry
from egegen.core.types import Attachment, Instance

__all__ = ["Attachment", "Instance", "get_generator", "list_generators", "registry"]
__version__ = "0.1.0"
