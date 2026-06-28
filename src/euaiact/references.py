"""Detect and resolve cross-references in provision text.

The EU AI Act HTML does **not** hyperlink internal cross-references — phrases
like "referred to in Annex III", "Article 6(2)", or "paragraph 3, point (a)"
are plain prose. For formalization work we need these as explicit edges between
provision ids, so this module:

1. :func:`extract_references` -- regex-scans text for references and returns
   structured :class:`~euaiact.model.CrossReference` objects.
2. :func:`resolve` -- maps a reference to concrete provision id(s), using an
   index of existing ids and (for relative refs like "paragraph 3") the
   *context* provision in which the text appears.

Resolution is deliberately conservative: it only emits a ``target_id`` when the
id exists in the parsed Act, so spurious edges are avoided. References to *other*
legal acts (Regulations/Directives/Decisions) are flagged ``external=True``.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

from .model import CrossReference, Provision, ProvisionType as PT
from .parser import roman_to_int

# --------------------------------------------------------------------------- #
# Regexes (ordered; earlier, more specific patterns win their span).
# --------------------------------------------------------------------------- #
_ROMAN = r"[IVXLCDM]+"

# "Article 6(2), point (a)" / "Article 5(1)" / "Article 9 to 15" / "Articles 9, 10 and 11"
_ARTICLE_RE = re.compile(
    r"Articles?\s+"
    r"(?P<num>\d+)"
    r"(?:\s*\((?P<par>\d+)\))?"
    r"(?:\s*,?\s*point\s*\((?P<point>[a-z0-9]+)\))?"
    r"(?:\s*(?P<rng>to|and|,)\s*(?P<num2>\d+))?",
    re.I,
)

# "Annex III" / "Annex III, point 1" / "Annexes I to XII"
_ANNEX_RE = re.compile(
    rf"Annex(?:es)?\s+(?P<rom>{_ROMAN})"
    r"(?:\s*,?\s*point\s*(?P<point>\(?[a-z0-9]+\)?))?"
    rf"(?:\s+(?P<rng>to|and)\s+(?P<rom2>{_ROMAN}))?",
    re.I,
)

# Relative references inside the same article/paragraph.
_PARAGRAPH_RE = re.compile(r"paragraphs?\s+(?P<num>\d+)(?:\s*(?:to|and|,)\s*(?P<num2>\d+))?", re.I)
_POINT_RE = re.compile(r"points?\s+\((?P<p>[a-z0-9]+)\)(?:\s*(?:to|and|,)\s*\((?P<p2>[a-z0-9]+)\))?", re.I)
_RECITAL_RE = re.compile(r"recitals?\s+(?P<num>\d+)", re.I)

# Other EU acts -> external.
_EXTERNAL_RE = re.compile(
    r"(?:Regulation|Directive|Decision)s?\s+"
    r"(?:\((?:EU|EC|EEC|Euratom)\)\s*)?"
    r"(?:No\s*)?\d+/\d+(?:/[A-Z]+)?",
    re.I,
)


def _expand_int_range(a: int, b: int) -> list[int]:
    if b < a:
        a, b = b, a
    return list(range(a, b + 1))


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #
def extract_references(text: str) -> list[CrossReference]:
    """Return cross-references found in ``text`` (unresolved target ids)."""
    refs: list[CrossReference] = []
    spans: list[tuple[int, int]] = []

    def overlaps(s: int, e: int) -> bool:
        return any(s < oe and os < e for os, oe in spans)

    for m in _EXTERNAL_RE.finditer(text):
        spans.append(m.span())
        refs.append(CrossReference(raw=m.group(0), kind="external", external=True))

    for m in _ARTICLE_RE.finditer(text):
        if overlaps(*m.span()):
            continue
        spans.append(m.span())
        refs.append(CrossReference(raw=m.group(0).strip(), kind="article"))

    for m in _ANNEX_RE.finditer(text):
        if overlaps(*m.span()):
            continue
        spans.append(m.span())
        refs.append(CrossReference(raw=m.group(0).strip(), kind="annex"))

    for regex, kind in ((_PARAGRAPH_RE, "paragraph"), (_POINT_RE, "point"),
                        (_RECITAL_RE, "recital")):
        for m in regex.finditer(text):
            if overlaps(*m.span()):
                continue
            spans.append(m.span())
            refs.append(CrossReference(raw=m.group(0).strip(), kind=kind))

    return refs


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #
def resolve(
    ref: CrossReference,
    ids: Iterable[str] | set[str],
    context: Optional[Provision] = None,
) -> CrossReference:
    """Fill ``ref.target_ids`` with ids that exist in ``ids``.

    ``context`` supplies the article/paragraph for relative references such as
    "paragraph 3" or "point (a)".
    """
    idset = ids if isinstance(ids, set) else set(ids)
    if ref.external:
        return ref

    targets: list[str] = []
    raw = ref.raw

    if ref.kind == "article":
        m = _ARTICLE_RE.search(raw)
        if m:
            nums = [int(m.group("num"))]
            if m.group("num2") and (m.group("rng") or "").lower() == "to":
                nums = _expand_int_range(int(m.group("num")), int(m.group("num2")))
            elif m.group("num2"):
                nums.append(int(m.group("num2")))
            for n in nums:
                base = f"art_{n}"
                tid = base
                if m.group("par"):
                    tid = f"{base}.par_{int(m.group('par'))}"
                    if m.group("point"):
                        tid = f"{tid}.pt_{m.group('point').strip('()')}"
                targets.append(tid if tid in idset else base)

    elif ref.kind == "annex":
        m = _ANNEX_RE.search(raw)
        if m:
            roms = [m.group("rom")]
            if m.group("rom2") and (m.group("rng") or "").lower() == "to":
                a, b = roman_to_int(m.group("rom")), roman_to_int(m.group("rom2"))
                from .parser import int_to_roman
                roms = [int_to_roman(i) for i in _expand_int_range(a, b)]
            elif m.group("rom2"):
                roms.append(m.group("rom2"))
            for rom in roms:
                base = f"anx_{rom.upper()}"
                tid = base
                if m.group("point"):
                    tid = f"{base}.pt_{m.group('point').strip('()')}"
                targets.append(tid if tid in idset else base)

    elif ref.kind == "paragraph" and context is not None:
        art = context if context.type == PT.ARTICLE else context.ancestor_of_type(PT.ARTICLE)
        if art is not None:
            m = _PARAGRAPH_RE.search(raw)
            nums = [int(m.group("num"))]
            if m.group("num2"):
                nums = _expand_int_range(int(m.group("num")), int(m.group("num2")))
            for n in nums:
                targets.append(f"{art.id}.par_{n}")

    elif ref.kind == "point" and context is not None:
        base = context if context.type in (PT.PARAGRAPH, PT.POINT, PT.ARTICLE, PT.ANNEX) \
            else context.ancestor_of_type(PT.PARAGRAPH)
        if base is not None:
            m = _POINT_RE.search(raw)
            pts = [m.group("p")]
            if m.group("p2"):
                pts.append(m.group("p2"))
            for p in pts:
                targets.append(f"{base.id}.pt_{p}")

    elif ref.kind == "recital":
        m = _RECITAL_RE.search(raw)
        if m:
            targets.append(f"rct_{int(m.group('num'))}")

    ref.target_ids = [t for t in dict.fromkeys(targets) if t in idset]
    return ref
