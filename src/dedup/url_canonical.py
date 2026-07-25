"""Phase 5 / Step 2 - URL canonicalisation and URL-group resolution
(pure logic; the runner does the IO).

Contract: original URLs are preserved byte-for-byte; canonicalisation
produces a SEPARATE comparison key, every transformation applied is
named in the output, and anything the rules cannot handle honestly
lands in review instead of being guessed. No network requests, ever -
redirect/canonical evidence is used only where the collection stage
already stored it.

Canonicalisation rules, in application order (each named when it
fires):

    wayback_unwrapped   web.archive.org/web/<ts>/<url> -> <url>, with
                        the capture timestamp preserved separately.
                        This is the repository's dominant "archive
                        variant" case (the robots-restricted local
                        publishers were collected via Wayback), and
                        unwrapping is what lets an archived capture
                        and a live fetch of the same page meet in one
                        group.
    scheme_https        http -> https (comparison key only; no claim
                        the live site serves both).
    host_lowercased     hostname lowercased - NEVER the path, which
                        can be case-sensitive.
    mobile_host         leading "m." or "amp." stripped from the host.
    amp_path            trailing /amp or .amp stripped from the path.
    default_port        :80 / :443 removed.
    fragment_removed    #... removed (fragments never reach servers).
    tracking_params     documented list removed: utm_*, fbclid, gclid,
                        mc_cid, mc_eid, CMP, ICID, ito, ns_campaign,
                        ns_source, print. Anything NOT on the list is
                        retained - an unknown parameter may identify a
                        distinct article (specification item 3).
    params_sorted       surviving query parameters sorted by key.
    slashes_collapsed   internal // in the path collapsed.
    trailing_slash      one trailing slash stripped (except root).

Malformed URLs (no scheme+host after repair attempts) canonicalise to
"" and are flagged malformed_url -> review; they never join a group.

Group identity: URL-<first 12 hex of sha256(canonical)> - a pure
function of the canonical string, so future releases can add members
or new groups but can never rename an untouched group.

Relationship classification within a group (content evidence comes
from Step 1's body hashes; URL equality alone never decides an
article relationship):

    unique_url                      only member of its group.
    same_url_same_content           same canonical URL, same body hash.
    same_url_content_changed       same canonical URL (no variant
                                    rules involved), different body -
                                    a POSSIBLE update, not a duplicate.
    url_variant_probable_same_page  URLs matched only after variant
                                    rules (wayback/amp/mobile) AND
                                    bodies differ - probably the same
                                    page seen through different doors;
                                    weaker claim, review-flagged.
    different_url_same_exact_content Step 1 exact cluster spanning
                                    multiple canonical URLs.
    ambiguous_url_relationship      malformed URL or missing body
                                    evidence inside a multi-member
                                    group.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

RULE_VERSION = "url-canon-v1.0-2026-07-27"

TRACKING_EXACT = {"fbclid", "gclid", "mc_cid", "mc_eid", "cmp", "icid",
                  "ito", "ns_campaign", "ns_source", "print"}
WAYBACK = re.compile(
    r"^https?://web\.archive\.org/web/(\d{4,14})(?:[a-z_*]*)/(.+)$", re.I)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonicalise(url: str) -> dict:
    """Deterministically canonicalise one URL. Returns the canonical
    comparison key, the named transformations applied, any flags, and
    the wayback capture timestamp when one was unwrapped."""
    transforms: list[str] = []
    flags: list[str] = []
    capture_ts = ""
    u = (url or "").strip()

    if not u:
        return {"canonical": "", "transforms": [], "capture_ts": "",
                "flags": ["malformed_url"]}

    m = WAYBACK.match(u)
    if m:
        capture_ts = m.group(1)
        u = m.group(2)
        if not u.lower().startswith(("http://", "https://")):
            u = "https://" + u.lstrip("/")
        transforms.append("wayback_unwrapped")

    try:
        parts = urlsplit(u)
    except ValueError:
        return {"canonical": "", "transforms": transforms,
                "capture_ts": capture_ts, "flags": ["malformed_url"]}
    if not parts.scheme or not parts.netloc:
        return {"canonical": "", "transforms": transforms,
                "capture_ts": capture_ts, "flags": ["malformed_url"]}

    scheme = parts.scheme.lower()
    if scheme == "http":
        scheme, _ = "https", transforms.append("scheme_https")

    host = parts.netloc
    if host != host.lower():
        transforms.append("host_lowercased")
    host = host.lower()
    for prefix in ("m.", "amp."):
        if host.startswith(prefix) and host.count(".") >= 2:
            host = host[len(prefix):]
            transforms.append("mobile_host")
            break
    for port, sch in ((":80", "https"), (":443", "https")):
        if host.endswith(port):
            host = host.rsplit(":", 1)[0]
            transforms.append("default_port")

    path = parts.path or "/"
    if "//" in path:
        path = re.sub(r"/{2,}", "/", path)
        transforms.append("slashes_collapsed")
    lowered = path.lower()
    if lowered.endswith("/amp") or lowered.endswith(".amp"):
        path = path[:-4] or "/"
        transforms.append("amp_path")
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/") or "/"
        transforms.append("trailing_slash")

    if parts.fragment:
        transforms.append("fragment_removed")

    kept, removed = [], []
    for k, v in parse_qsl(parts.query, keep_blank_values=True):
        kl = k.lower()
        if kl.startswith("utm_") or kl in TRACKING_EXACT:
            removed.append(k)
        else:
            kept.append((k, v))
    if removed:
        transforms.append("tracking_params:" + ",".join(sorted(removed)))
    if kept != sorted(kept):
        transforms.append("params_sorted")
    query = urlencode(sorted(kept))

    canonical = urlunsplit((scheme, host, path, query, ""))
    return {"canonical": canonical, "transforms": transforms,
            "capture_ts": capture_ts, "flags": flags}


VARIANT_RULES = {"wayback_unwrapped", "mobile_host", "amp_path"}


def resolve_url_groups(records: list[dict]) -> dict:
    """Group records by canonical URL and classify relationships.

    ``records``: [{article_id, original_url, body_hash,
    retrieved_at}] - body_hash comes from Step 1's mapping, so URL and
    content evidence stay two independent witnesses.
    """
    rows = []
    for rec in sorted(records, key=lambda r: r["article_id"]):
        c = canonicalise(rec.get("original_url", ""))
        rows.append({**rec, **c,
                     "group_id": ("URL-" + sha256(c["canonical"])[:12])
                     if c["canonical"] else "",
                     "flags": list(c["flags"])})

    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["group_id"]:
            groups[r["group_id"]].append(r)

    # cross-URL exact-content map (Step 1 evidence)
    body_urls: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        if r.get("body_hash") and r["canonical"]:
            body_urls[r["body_hash"]].add(r["canonical"])

    for gid, members in groups.items():
        if len(members) == 1:
            r = members[0]
            if r.get("body_hash") and len(body_urls[r["body_hash"]]) > 1:
                r["relationship"] = "different_url_same_exact_content"
                r["flags"].append("exact_content_elsewhere")
            else:
                r["relationship"] = "unique_url"
            r["group_size"] = 1
            continue
        hashes = {m.get("body_hash") or "" for m in members}
        variant_merge = any(set(m["transforms"]) & VARIANT_RULES
                            for m in members)
        for m in members:
            m["group_size"] = len(members)
            if "" in hashes:
                m["relationship"] = "ambiguous_url_relationship"
                m["flags"].append("missing_body_evidence_in_group")
            elif len(hashes) == 1:
                m["relationship"] = "same_url_same_content"
            elif variant_merge:
                m["relationship"] = "url_variant_probable_same_page"
                m["flags"].append("variant_merge_content_differs")
            else:
                m["relationship"] = "same_url_content_changed"
                m["flags"].append("possible_updated_version")

    for r in rows:
        if not r["group_id"]:
            r["relationship"] = "ambiguous_url_relationship"
            r["group_size"] = 0
        r["flags"] = sorted(set(r["flags"]))

    group_list = [{"group_id": gid, "size": len(ms),
                   "canonical_url": ms[0]["canonical"],
                   "member_ids": sorted(m["article_id"] for m in ms),
                   "relationships": sorted({m["relationship"] for m in ms})}
                  for gid, ms in sorted(groups.items())]
    return {"mapping": rows, "groups": group_list,
            "rule_version": RULE_VERSION}
