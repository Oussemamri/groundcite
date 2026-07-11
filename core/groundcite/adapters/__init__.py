"""Adapters layer (spec §4).

Concrete implementations of the ports, one module per adapter, grouped by the
port it implements. Adapters import ``domain`` + ``ports`` only — NEVER
``services`` (spec §4 dependency rule). Every module here is an empty typed stub
until its Week; ``container.build_services`` selects one per port from config,
so adding a new backend = one new module here + one config value (spec §11, §16).
"""
