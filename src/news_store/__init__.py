"""Local SQLite store for the news layer.

Holds raw articles, model extractions, human corrections and the audit trail
linking them. Its one structural commitment is that a correction is inserted
rather than applied, so the model's original output survives every review and
"do not overwrite the AI value" is a property of the schema rather than a rule
somebody has to follow.

No credential of any kind is ever written here.

Provenance of the requirements
------------------------------
The constraints this layer is built to satisfy - preserving both the model
value and the reviewed value, the five review statuses, per-article
traceability of every aggregated feature, and keeping credentials out of the
store, the logs and every export - were agreed with the project supervisor and
are recorded in the project brief. They are not restated at each point below;
what the comments give is the reasoning for the design chosen to meet them,
which is where the decisions actually are.
"""

from .schema import PROVENANCE_AI, PROVENANCE_REVIEWED, REVIEW_STATUSES, connect
from .store import NewsStore, ResolvedValue

__all__ = ["NewsStore", "ResolvedValue", "connect",
           "REVIEW_STATUSES", "PROVENANCE_AI", "PROVENANCE_REVIEWED"]
