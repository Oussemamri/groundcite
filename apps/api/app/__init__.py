"""GroundCite FastAPI app (spec §9).

Interface layer: routes are thin (parse -> service -> serialize), errors are
RFC-7807 problem JSON, and response models are mapped explicitly from domain
entities (never shared). P5 ships only ``GET /healthz``; the ``/api/v1`` surface
lands in Week 4.
"""
