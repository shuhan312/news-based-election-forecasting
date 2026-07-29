"""Local SQLite store for the news layer.

Holds raw articles, model extractions, human corrections and the audit trail
linking them. Its one structural commitment is that a correction is inserted
rather than applied, so the model's original output survives every review and
"do not overwrite the AI value" is a property of the schema rather than a rule
somebody has to follow.

No credential of any kind is ever written here.
"""

from .schema import PROVENANCE_AI, PROVENANCE_REVIEWED, REVIEW_STATUSES, connect
from .store import NewsStore, ResolvedValue

__all__ = ["NewsStore", "ResolvedValue", "connect",
           "REVIEW_STATUSES", "PROVENANCE_AI", "PROVENANCE_REVIEWED"]
