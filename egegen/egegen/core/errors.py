"""Exceptions raised by the generator framework."""

from __future__ import annotations


class EgegenError(Exception):
    """Base class for every error this package raises."""


class GeneratorNotFoundError(EgegenError):
    """No generator is registered for the requested task type."""


class UnknownSubtypeError(EgegenError):
    """The requested subtype is not offered by the generator."""


class ConfigError(EgegenError):
    """A YAML config under ``egegen/config`` is missing or malformed."""


class GenerationFailedError(EgegenError):
    """The generator could not build a valid instance for the given seed.

    Generators that reject candidates in a loop raise this after exhausting their
    attempt budget rather than returning a degenerate task.
    """
