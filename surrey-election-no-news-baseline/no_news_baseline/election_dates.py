"""Parse the ``election_date`` string used throughout the data contract.

The single date parser for the candidate pipeline: chronological ordering
feeds the split design and the "source_date_precedes_target" leakage rule,
so there is exactly one implementation to get right and test.

This module does not import the extractor's internal Python package
(README, "The modelling layer... does not import the extractor's internal
Python modules"); it is a small, independently-written parser for the same
plain-text date format the extractor happens to publish.
"""

from __future__ import annotations

from datetime import datetime

# The extractor publishes election_date as either a spelled-out British date
# ("2 May 2013") or an ISO date ("2013-05-02"), depending on which source
# layer produced the value. Both are accepted.
_SUPPORTED_FORMATS = ("%d %B %Y", "%Y-%m-%d")


def parse_election_date(value: str) -> datetime:
    for date_format in _SUPPORTED_FORMATS:
        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            pass
    raise ValueError(f"Unsupported election date: {value!r}")
