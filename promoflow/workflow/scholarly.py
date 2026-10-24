"""Small client for OpenAlex, the free scholarly database (free key: openalex.org/settings/api). No Scopus.

Used by the Research Agent (verified h-index / citations) and, separately, by the Reviewer Outreach agent (referee
search, author profiles, co-author lists). Each agent calls it on its own. Plain `urllib`, so no new library is
needed.

Every network function takes a `get_json` argument. The real one calls the internet; tests pass a fake that returns
canned replies, so the tests need no key and no network.

Errors are split in three, because they mean different things for the applicant:
  NotFound    - the database answered "no such author"           -> a real finding, worth a warning
  NoAccess    - no key, or the key is refused (401/403)           -> our problem, never held against the applicant
  Unavailable - network down, timeout, rate limit, odd reply      -> our problem, never held against the applicant
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from promoflow import config

OPENALEX = "https://api.openalex.org"
TIMEOUT_SECONDS = 15


class NotFound(Exception):
    pass


class NoAccess(Exception):
    pass


class Unavailable(Exception):
    pass


def get_json(url: str, headers: dict | None = None) -> dict:
    """GET a URL and parse the JSON reply, translating failures into the three error types above."""
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "PromoFlow/0.1",
                                               **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise NotFound(url) from e
        if e.code in (401, 403):
            raise NoAccess(f"HTTP {e.code}") from e
        raise Unavailable(f"HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise Unavailable(f"{type(e).__name__}: {e}") from e


@dataclass
class AuthorProfile:
    """What we keep about one researcher (applicant or candidate referee)."""
    source: str                                   # always "openalex"
    external_id: str                              # e.g. "A5023888391"
    name: str | None = None
    h_index: int | None = None
    citations: int | None = None
    works: int | None = None
    topics: list[str] = field(default_factory=list)
    institutions: list[dict] = field(default_factory=list)   # [{"id", "name", "country"}], most recent first
    coauthors: list[str] = field(default_factory=list)       # OpenAlex ids of recent co-authors (filled on request)

    @property
    def country(self) -> str | None:
        return self.institutions[0]["country"] if self.institutions else None


# ---- OpenAlex ---------------------------------------------------------------------------------------------------

def _short_id(openalex_id: str | None) -> str | None:
    """"https://openalex.org/A123" -> "A123"."""
    return openalex_id.rstrip("/").rsplit("/", 1)[-1] if openalex_id else None


def _openalex_url(path: str, params: dict | None = None) -> str:
    params = dict(params or {})
    if config.OPENALEX_API_KEY:
        params["api_key"] = config.OPENALEX_API_KEY
    query = urllib.parse.urlencode(params, safe=":|,")
    return f"{OPENALEX}{path}" + (f"?{query}" if query else "")


def _profile_from_openalex(a: dict) -> AuthorProfile:
    insts = []
    for inst in a.get("last_known_institutions") or []:
        insts.append({"id": _short_id(inst.get("id")), "name": inst.get("display_name"),
                      "country": inst.get("country_code")})
    for aff in a.get("affiliations") or []:                       # older affiliations, for the conflict check
        inst = aff.get("institution") or {}
        entry = {"id": _short_id(inst.get("id")), "name": inst.get("display_name"),
                 "country": inst.get("country_code")}
        if entry["id"] and all(entry["id"] != i["id"] for i in insts):
            insts.append(entry)
    stats = a.get("summary_stats") or {}
    return AuthorProfile(
        source="openalex", external_id=_short_id(a.get("id")), name=a.get("display_name"),
        h_index=stats.get("h_index"), citations=a.get("cited_by_count"), works=a.get("works_count"),
        topics=[t.get("display_name") for t in (a.get("topics") or [])[:15] if t.get("display_name")],
        institutions=insts)


def openalex_author(ref: str, get: Callable = get_json) -> AuthorProfile:
    """One author by OpenAlex id ("A123" or the full URL) or by ORCID ("0000-0002-1825-0097")."""
    ref = ref.strip()
    if ref.count("-") == 3 and len(ref) == 19:                    # an ORCID
        path = f"/authors/orcid:{ref}"
    else:
        path = f"/authors/{_short_id(ref)}"
    return _profile_from_openalex(get(_openalex_url(path)))


def openalex_authors(ids: list[str], get: Callable = get_json) -> list[AuthorProfile]:
    """Many authors at once (50 per request)."""
    out = []
    ids = [i for i in dict.fromkeys(_short_id(x) for x in ids) if i]
    for start in range(0, len(ids), 50):
        chunk = ids[start:start + 50]
        data = get(_openalex_url("/authors", {"filter": "ids.openalex:" + "|".join(chunk), "per_page": 50}))
        out += [_profile_from_openalex(a) for a in data.get("results", [])]
    return out


def openalex_coauthor_ids(author_id: str, since_year: int, get: Callable = get_json) -> set[str]:
    """Everyone who co-wrote a paper with this author since `since_year` (for the conflict-of-interest check)."""
    me = _short_id(author_id)
    data = get(_openalex_url("/works", {
        "filter": f"author.id:{me},from_publication_date:{since_year}-01-01",
        "select": "id,authorships", "per_page": 200}))
    found = set()
    for work in data.get("results", []):
        for au in work.get("authorships") or []:
            other = _short_id((au.get("author") or {}).get("id"))
            if other and other != me:
                found.add(other)
    return found


def openalex_candidate_ids(search: str, since_year: int, exclude: set[str], limit: int = 40,
                           get: Callable = get_json) -> list[str]:
    """Authors who published recently on the topic, most active first. `search` is the topic text (fine
    specialization + keywords)."""
    data = get(_openalex_url("/works", {
        "search": search, "filter": f"from_publication_date:{since_year}-01-01",
        "select": "id,authorships", "per_page": 100}))
    counts: Counter = Counter()
    for work in data.get("results", []):
        for au in work.get("authorships") or []:
            aid = _short_id((au.get("author") or {}).get("id"))
            if aid and aid not in exclude:
                counts[aid] += 1
    return [aid for aid, _ in counts.most_common(limit)]

