"""Parse the ``election_date`` string used throughout the data contract.

Extracted because a third piece of code (``temporal_validation.py``) needs
the same chronological-ordering logic that ``naive_benchmarks.py`` already
duplicated from the extractor's own parser. A date-parsing bug is exactly
the kind of thing that would silently break the "source_date_precedes_
target" leakage rule, so there should be exactly one implementation to get
right and test, not three.

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
