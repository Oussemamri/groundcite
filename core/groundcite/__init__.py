"""GroundCite — grounded Q&A over aerospace & engineering standards.

Hexagonal core package. Layer order (imports flow downward only, spec §4):

    apps / cli  ->  container  ->  services  ->  ports  ->  domain
                                   adapters  ->  ports  ->  domain

Core never imports an adapter; ``container.build_services`` is the only place
adapters are wired from config. See ``GROUNDCITE_PROJECT_SPEC.md``.
"""

__version__ = "0.1.0"
