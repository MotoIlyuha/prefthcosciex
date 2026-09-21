"""Reusable algorithm kernels shared by several generators.

Keeping Dijkstra, the game analyser and the polygon test here (rather than inside
one generator) lets tasks 1/23, 19-21 and 6 share a single audited implementation,
while each generator still ships its own independent naive cross-check.
"""
