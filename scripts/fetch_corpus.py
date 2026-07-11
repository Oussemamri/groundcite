"""Download the demo corpus from official sources (spec §13, prep task P1).

PDFs never enter git (size + license, spec §13). This script fetches from
official sources into a git-ignored corpus directory; ``documents.license_note``
is mandatory on ingest. Default corpus: 14 CFR Part 25 (US public domain) + two
released NASA standards; EASA CS-25 via fetch only after verifying redistribution.

Not implemented in the P5 skeleton (built in Week 1 / prep P1).
"""

from __future__ import annotations


def main() -> None:
    raise NotImplementedError("fetch_corpus is implemented in prep task P1 / Week 1 (spec §13).")


if __name__ == "__main__":
    main()
