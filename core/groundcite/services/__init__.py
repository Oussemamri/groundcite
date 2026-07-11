"""Application services (spec §4).

Orchestration logic. Services depend on ``domain`` + ``ports`` only and never
import an adapter — concrete adapters are injected by ``container.build_services``
(spec §4 dependency rule). Bodies land in Weeks 1–4; here they are typed shells.
"""

from groundcite.services.ask import AskService
from groundcite.services.eval import EvalService
from groundcite.services.ingestion import IngestionService
from groundcite.services.library import LibraryService

__all__ = ["AskService", "EvalService", "IngestionService", "LibraryService"]
