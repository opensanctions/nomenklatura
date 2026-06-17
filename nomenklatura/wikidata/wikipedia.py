import logging
from typing import Dict, List, Optional, Set
from urllib.parse import quote
from requests import Session
from rigour.langs import PREFERRED_LANGS
from rigour.territories import get_territory
from followthemoney import StatementEntity

from nomenklatura.cache import Cache
from nomenklatura.wikidata.lang import LangText
from nomenklatura.wikidata.model import Item

log = logging.getLogger(__name__)

# Wikimedia asks bots to avoid the action API for page content and hit the
# CDN-cached REST endpoints instead. `page/summary` returns the lead paragraph
# as plaintext — enough to tell a reviewer who a candidate is (country, role,
# period) without dragging a whole article into view.
SUMMARY_API = "https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
SUMMARY_CACHE_DAYS = 100
# Per-item ceiling on summaries fetched: each is a REST call, and a handful of
# languages already gives enough context. Other languages stay reachable via the
# item's wikipediaUrl links, so this is a ceiling, not a target.
MAX_SUMMARIES = 5


def fetch_summary(
    cache: Cache, session: Session, lang: str, title: str
) -> Optional[str]:
    """Fetch the lead-paragraph plaintext of a Wikipedia article.

    Reach for this to give a reconciliation reviewer a one-glance "who is this"
    for a candidate Wikidata item. `lang` is the Wikipedia subdomain code (the
    `en` of `enwiki`), `title` the page title. Returns None for a missing page
    or one without an extract (e.g. a disambiguation page); both outcomes are
    cached as an empty string so repeated runs don't re-request them.
    """
    api_url = SUMMARY_API.format(
        lang=lang, title=quote(title.replace(" ", "_"), safe="")
    )
    cached = cache.get(api_url, max_age=SUMMARY_CACHE_DAYS)
    if cached is not None:
        return cached or None  # "" is the cached "no summary" sentinel
    res = session.get(api_url)
    if res.status_code == 404:
        cache.set(api_url, "")
        return None
    res.raise_for_status()
    extract = res.json().get("extract") or ""
    cache.set(api_url, extract)
    return extract or None


def preferred_langs(entity: StatementEntity) -> List[str]:
    """Order Wikipedia languages by relevance to a person, best first.

    The person's own country languages come first — a national politician's
    native-language article is usually the richest source — then the globally
    preferred languages, for a reviewer who can't read the native one. Returns
    ISO 639-3 codes, deduplicated in priority order; feed it to
    `item_wikipedia_summaries`.
    """
    langs: List[str] = []
    for country in entity.countries:
        territory = get_territory(country)
        if territory is not None:
            langs.extend(territory.langs)
    langs.extend(PREFERRED_LANGS)
    seen: Set[str] = set()
    ordered: List[str] = []
    for lang in langs:
        if lang not in seen:
            seen.add(lang)
            ordered.append(lang)
    return ordered


def item_wikipedia_summaries(
    cache: Cache,
    session: Session,
    item: Item,
    langs: List[str],
    limit: int = MAX_SUMMARIES,
) -> List[LangText]:
    """Fetch lead-paragraph summaries for an item's Wikipedia articles.

    Reach for this when preparing a reconciliation candidate for human review:
    it walks the item's Wikipedia sitelinks whose language is in `langs`
    (caller-supplied, see `preferred_langs`), in that order, and fetches each
    one's summary — capped at `limit` to bound the per-candidate REST calls.
    Languages outside `langs` are skipped rather than used as filler; the
    reviewer can still open the item's other articles via its wikipediaUrl
    links. Each result is a LangText tagged with the article's language, so it
    lands on `summary` with the right lang.
    """
    by_lang: Dict[str, str] = {}
    titles: Dict[str, str] = {}
    for link in item.wikilinks:
        if link.lang is None or link.wiki_site is None or link.lang in by_lang:
            continue
        by_lang[link.lang] = link.wiki_site
        titles[link.lang] = link.title
    summaries: List[LangText] = []
    for lang in langs:
        if len(summaries) >= limit:
            break
        wiki_site = by_lang.get(lang)
        if wiki_site is None:
            continue
        extract = fetch_summary(cache, session, wiki_site, titles[lang])
        if extract is None:
            continue
        text = LangText(extract, lang)
        if text.text is not None:
            summaries.append(text)
    return summaries
