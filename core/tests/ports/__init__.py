"""Port contract tests (spec §6). One module per port, exercising every adapter
that implements it against a shared contract so adapters never silently drift
(spec §6 step 1: both pymupdf_parser and docling_parser share the DocumentParser
contract test).
"""
