"""Validation and normalisation helpers for official Surrey election URLs."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SURREY_HOST = "mycouncil.surreycc.gov.uk"
INDEX_PATH = "/mgElectionElectionAreaResults.aspx"
AREA_PATH = "/mgElectionAreaResults.aspx"
ELECTION_RESULTS_PATH = "/mgElectionResults.aspx"
TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}


def _is_tracking_parameter(name: str) -> bool:
    lowered = name.casefold()
    return lowered.startswith("utm_") or lowered in TRACKING_PARAMETERS


def normalise_url(url: str) -> str:
    """Canonicalise an official URL while preserving non-tracking parameters."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("URL must be a non-empty string.")

    parsed = urlsplit(url.strip())
    if parsed.scheme.casefold() not in {"http", "https"}:
        raise ValueError("URL must use HTTP or HTTPS.")
    if parsed.username or parsed.password:
        raise ValueError("URL must not contain user credentials.")
    if (parsed.hostname or "").casefold() != SURREY_HOST:
        raise ValueError("URL must use the official Surrey County Council host.")

    port = parsed.port
    if port not in {None, 80, 443}:
        raise ValueError("URL must not use a non-standard port.")

    parameters = []
    seen = set()
    for name, value in parse_qsl(parsed.query, keep_blank_values=True):
        # Remove only known tracking fields. Unknown parameters are retained
        # because they may be meaningful to the council results application.
        if _is_tracking_parameter(name):
            continue
        # Official identifiers are canonicalised to make equivalent links equal.
        canonical_name = name.upper() if name.casefold() in {"eid", "id", "rpid", "xxr"} else name
        item = (canonical_name, value)
        if item not in seen:
            seen.add(item)
            parameters.append(item)
    # Stable parameter ordering allows reliable URL deduplication.
    parameters.sort(key=lambda item: (item[0].casefold(), item[1]))

    known_paths = {
        INDEX_PATH.casefold(): INDEX_PATH,
        AREA_PATH.casefold(): AREA_PATH,
    }
    canonical_path = known_paths.get(parsed.path.casefold(), parsed.path)
    return urlunsplit(("https", SURREY_HOST, canonical_path, urlencode(parameters), ""))


def _single_numeric_parameter(query: str, name: str) -> bool:
    # Reject missing or conflicting identifiers instead of choosing one value.
    values = [value for key, value in parse_qsl(query, keep_blank_values=True) if key == name]
    return len(values) == 1 and values[0].isdigit()


def validate_index_url(url: str) -> str:
    """Validate and return a canonical Surrey election index URL."""
    canonical = normalise_url(url)
    parsed = urlsplit(canonical)
    if parsed.path.casefold() != INDEX_PATH.casefold():
        raise ValueError("URL is not a Surrey election-area index URL.")
    if not _single_numeric_parameter(parsed.query, "EID"):
        raise ValueError("Election index URL must include a numeric EID parameter.")
    return canonical


def principal_election_url_to_index_url(url: str) -> str:
    """Convert an official election landing page into its area-index URL.

    The links supplied by the supervisor use ``mgElectionResults.aspx?ID=...``
    while the indexed discovery page uses the same official election identifier
    as ``mgElectionElectionAreaResults.aspx?EID=...``.  Converting only this
    exact Surrey path and one numeric ID lets users paste the supplied link
    without weakening host, path or identifier validation.
    """

    canonical = normalise_url(url)
    parsed = urlsplit(canonical)
    if parsed.path.casefold() != ELECTION_RESULTS_PATH.casefold():
        raise ValueError("URL is not a Surrey principal-election results URL.")
    if not _single_numeric_parameter(parsed.query, "ID"):
        raise ValueError("Election results URL must include one numeric ID parameter.")

    # RPID is navigation state from the council site and is not an election
    # identifier.  Starting a new query with EID alone avoids carrying that
    # session-like value into indexed discovery.
    election_id = next(
        value for name, value in parse_qsl(parsed.query) if name == "ID"
    )
    return urlunsplit(
        ("https", SURREY_HOST, INDEX_PATH, urlencode({"EID": election_id}), "")
    )


def normalise_area_result_url(url: str) -> str:
    """Validate and return a canonical Surrey ward or division result URL."""
    canonical = normalise_url(url)
    parsed = urlsplit(canonical)
    if parsed.path.casefold() != AREA_PATH.casefold():
        raise ValueError("URL is not a Surrey election-area result URL.")
    if not _single_numeric_parameter(parsed.query, "ID"):
        raise ValueError("Election-area result URL must include a numeric ID parameter.")
    return canonical
