from functools import partial
from typing import Optional
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from followthemoney import StatementEntity
from followthemoney.settings import USER_AGENT
from rigour.ids.wikidata import is_qid

# Retry on server errors plus the rate-limit / Retry-After statuses (429, 503).
# urllib3 honours the Retry-After header for these by default, which is how we
# back off cleanly when Wikidata throttles us.
RETRY_STATUSES = [500, 502, 504] + list(Retry.RETRY_AFTER_STATUS_CODES)
HTTP_TIMEOUT = 90


def entity_qid(entity: StatementEntity) -> Optional[str]:
    """Return the Wikidata QID an entity is already linked to, if any.

    Reach for this before searching Wikidata for a person: an entity may carry
    its QID either as its own id (Wikidata-sourced entities) or in a
    `wikidataId` property (cross-referenced ones). The id wins — it's the
    stronger assertion — and we fall back to the property. Returns None when the
    entity isn't linked yet, i.e. it's a reconciliation candidate.
    """
    if entity.id is not None and is_qid(entity.id):
        return entity.id
    for value in entity.get("wikidataId", quiet=True):
        if is_qid(value):
            return value
    return None


def make_session(
    user_agent: str = USER_AGENT,
    total_retries: int = 3,
    backoff_factor: float = 1.0,
    backoff_max: int = 120,
    timeout: int = HTTP_TIMEOUT,
) -> Session:
    """Build a requests Session configured for talking to the Wikidata APIs.

    Reach for this whenever hitting Wikidata directly: the default requests
    User-Agent gets a 403 from Wikimedia, and unauthenticated clients get rate
    limited under load. The session sets a descriptive User-Agent and a retry
    policy that backs off on server errors and honours `Retry-After` on
    429/503, so callers survive throttling without bespoke loops.

    The configuration is inspired by zavod's crawler session but tuned for an
    API client: it verifies TLS (Wikidata serves valid certs, unlike the long
    tail of crawler targets) and uses a much shorter, API-appropriate timeout.
    """
    session = Session()
    session.headers["User-Agent"] = user_agent
    session.request = partial(session.request, timeout=timeout)  # type: ignore
    retries = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,
        backoff_max=backoff_max,
        status_forcelist=RETRY_STATUSES,
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
