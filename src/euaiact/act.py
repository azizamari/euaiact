"""The :class:`AIAct` facade -- the main entry point of the SDK.

Typical use::

    from euaiact import AIAct

    act = AIAct.load()                     # bundled consolidated text
    art9 = act.article(9)                  # -> Provision
    print(art9.heading)                    # "Risk management system"
    print(art9.paragraph(2).full_text())   # readable text of Art 9(2)

    for ref in act.references(art9.paragraph(2)):
        print(ref.raw, "->", ref.target_ids)

    act.to_json("aiact.json")              # whole tree, stable ids + edges
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, Iterator, Optional, Union

from .model import CrossReference, Footnote, Provision, ProvisionType as PT
from .parser import int_to_roman, parse_html, roman_to_int
from . import references as _refs

_DATA_FILE = Path(__file__).parent / "data" / "eu_ai_act_2024_1689_en.html"

RomanOrInt = Union[str, int]

_ARTICLE_CITATION_RE = re.compile(r"^Article\s+(?P<num>\d+)(?P<tail>.*)$", re.I)
_RECITAL_CITATION_RE = re.compile(r"^Recital\s+(?P<num>\d+)$", re.I)
_PREAMBLE_CITATION_RE = re.compile(r"^Citation\s+(?P<num>\d+)$", re.I)
_CHAPTER_CITATION_RE = re.compile(r"^Chapter\s+(?P<num>[IVXLCDM]+|\d+)(?P<tail>.*)$", re.I)
_ANNEX_CITATION_RE = re.compile(r"^Annex\s+(?P<num>[IVXLCDM]+|\d+)(?P<tail>.*)$", re.I)
_SECTION_TAIL_RE = re.compile(r"^,?\s*Section\s+(?P<num>\d+)$", re.I)
_PAREN_MARKER_RE = re.compile(r"\(([A-Za-z0-9]+)\)")


def _roman(value: RomanOrInt) -> str:
    if isinstance(value, int):
        return int_to_roman(value)
    return value.strip().upper()


def _normalise_lookup(text: str) -> str:
    text = text.replace("\xa0", " ").replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip().rstrip(".;")


def _citation_number_to_roman(value: str) -> str:
    if value.isdigit():
        return int_to_roman(int(value))
    return value.upper()


def _parse_point_markers(tail: str) -> Optional[list[str]]:
    tail = tail.strip()
    tail = re.sub(r"^,?\s*points?\s*", "", tail, flags=re.I).strip()
    if not tail:
        return []

    markers: list[str] = []
    if not tail.startswith("("):
        m = re.match(r"([A-Za-z0-9]+)", tail)
        if not m:
            return None
        markers.append(m.group(1))
        tail = tail[m.end():]

    pos = 0
    while pos < len(tail):
        if tail[pos].isspace():
            pos += 1
            continue
        m = _PAREN_MARKER_RE.match(tail, pos)
        if not m:
            return None
        markers.append(m.group(1))
        pos = m.end()
    return markers


def _append_points(base: str, markers: list[str]) -> str:
    for marker in markers:
        base = f"{base}.pt_{marker.lower()}"
    return base


def _citation_to_id(text: str) -> Optional[str]:
    """Translate common legal citations to canonical provision ids.

    This is intentionally narrow: it accepts familiar user-facing forms such as
    ``Article 5(1)(a)`` and ``Annex III, point 1(a)``. Existence is still checked
    by ``AIAct.get`` after translation, so unknown provisions do not become hits.
    """
    text = _normalise_lookup(text)

    m = _RECITAL_CITATION_RE.match(text)
    if m:
        return f"rct_{int(m.group('num'))}"

    m = _PREAMBLE_CITATION_RE.match(text)
    if m:
        return f"cit_{int(m.group('num'))}"

    m = _CHAPTER_CITATION_RE.match(text)
    if m:
        pid = f"cpt_{_citation_number_to_roman(m.group('num'))}"
        tail = m.group("tail").strip()
        if not tail:
            return pid
        sm = _SECTION_TAIL_RE.match(tail)
        if sm:
            return f"{pid}.sct_{int(sm.group('num'))}"
        return None

    m = _ANNEX_CITATION_RE.match(text)
    if m:
        pid = f"anx_{_citation_number_to_roman(m.group('num'))}"
        tail = m.group("tail").strip()
        if not tail:
            return pid
        markers = _parse_point_markers(tail)
        return _append_points(pid, markers) if markers else None

    m = _ARTICLE_CITATION_RE.match(text)
    if not m:
        return None

    pid = f"art_{int(m.group('num'))}"
    tail = m.group("tail").strip()
    if not tail:
        return pid

    par = _PAREN_MARKER_RE.match(tail)
    if par and par.group(1).isdigit():
        pid = f"{pid}.par_{int(par.group(1))}"
        tail = tail[par.end():].strip()
        if not tail:
            return pid

    markers = _parse_point_markers(tail)
    return _append_points(pid, markers) if markers else None


class AIAct:
    """A parsed, navigable EU AI Act (Regulation (EU) 2024/1689)."""

    def __init__(self, document: Provision, footnotes: dict[str, Footnote]):
        self.document = document
        self.footnotes = footnotes
        # Index every provision by id (canonical) and by eli_id (raw HTML id).
        self._by_id: dict[str, Provision] = {}
        self._by_eli: dict[str, Provision] = {}
        for p in document.walk():
            self._by_id[p.id] = p
            if p.eli_id:
                self._by_eli[p.eli_id] = p

    # -- construction --------------------------------------------------------
    @classmethod
    def load(cls) -> "AIAct":
        """Load the consolidated text bundled with the package."""
        return cls.from_file(_DATA_FILE)

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "AIAct":
        html = Path(path).read_text(encoding="utf-8")
        return cls.from_html(html)

    @classmethod
    def from_html(cls, html: str) -> "AIAct":
        document, footnotes = parse_html(html)
        return cls(document, footnotes)

    # -- collections ---------------------------------------------------------
    @property
    def title(self) -> str:
        return self.document.heading

    @property
    def chapters(self) -> list[Provision]:
        return [c for c in self.document.children if c.type == PT.CHAPTER]

    @property
    def articles(self) -> list[Provision]:
        return self.document.of_type(PT.ARTICLE)

    @property
    def recitals(self) -> list[Provision]:
        return self.document.of_type(PT.RECITAL)

    @property
    def citations(self) -> list[Provision]:
        return self.document.of_type(PT.CITATION)

    @property
    def annexes(self) -> list[Provision]:
        return [a for a in self.document.children if a.type == PT.ANNEX]

    @property
    def sections(self) -> list[Provision]:
        return self.document.of_type(PT.SECTION)

    # -- single-item accessors ----------------------------------------------
    def article(self, number: RomanOrInt) -> Provision:
        return self._require(f"art_{int(number)}", f"Article {number}")

    def recital(self, number: int) -> Provision:
        return self._require(f"rct_{int(number)}", f"Recital {number}")

    def citation(self, number: int) -> Provision:
        return self._require(f"cit_{int(number)}", f"Citation {number}")

    def chapter(self, number: RomanOrInt) -> Provision:
        rom = _roman(number)
        return self._require(f"cpt_{rom}", f"Chapter {number}")

    def annex(self, number: RomanOrInt) -> Provision:
        rom = _roman(number)
        return self._require(f"anx_{rom}", f"Annex {number}")

    def get(self, provision_id: str) -> Optional[Provision]:
        """Look up a provision by canonical id, raw EUR-Lex id, or legal citation."""
        found = self._by_id.get(provision_id) or self._by_eli.get(provision_id)
        if found is not None:
            return found
        citation_id = _citation_to_id(provision_id)
        return self._by_id.get(citation_id or "")

    def __getitem__(self, provision_id: str) -> Provision:
        p = self.get(provision_id)
        if p is None:
            raise KeyError(provision_id)
        return p

    def __contains__(self, provision_id: str) -> bool:
        return self.get(provision_id) is not None

    def _require(self, pid: str, label: str) -> Provision:
        p = self._by_id.get(pid)
        if p is None:
            raise KeyError(f"{label} (id={pid!r}) not found")
        return p

    # -- traversal & search --------------------------------------------------
    def walk(self) -> Iterator[Provision]:
        """Depth-first iteration over every provision in the Act."""
        return self.document.descendants()

    def provisions(self, *types: PT) -> list[Provision]:
        """Flat list of all provisions, optionally filtered by type."""
        if not types:
            return list(self.walk())
        wanted = set(types)
        return [p for p in self.walk() if p.type in wanted]

    def search(
        self,
        query: str,
        *,
        regex: bool = False,
        ignore_case: bool = True,
        types: Optional[Iterable[PT]] = None,
        whole_subtree: bool = False,
    ) -> list[Provision]:
        """Return provisions whose text matches ``query``.

        By default matches against each provision's *own* text; set
        ``whole_subtree=True`` to match against the flattened subtree text.
        """
        flags = re.IGNORECASE if ignore_case else 0
        pattern = re.compile(query if regex else re.escape(query), flags)
        wanted = set(types) if types else None
        hits: list[Provision] = []
        for p in self.walk():
            if wanted and p.type not in wanted:
                continue
            haystack = p.plain_text if whole_subtree else p.text
            if haystack and pattern.search(haystack):
                hits.append(p)
        return hits

    # -- footnotes -----------------------------------------------------------
    def footnote(self, ref: Union[str, int]) -> Optional[Footnote]:
        if isinstance(ref, int):
            ref = f"fn_{ref}"
        elif not ref.startswith("fn_"):
            ref = f"fn_{int(ref)}"
        return self.footnotes.get(ref)

    def footnotes_for(self, provision: Provision) -> list[Footnote]:
        return [self.footnotes[i] for i in provision.footnote_ids if i in self.footnotes]

    # -- cross references ----------------------------------------------------
    def references(self, provision: Provision, *, resolve: bool = True) -> list[CrossReference]:
        """Cross-references found in ``provision``'s own text.

        With ``resolve=True`` (default) each reference's ``target_ids`` are
        filled with provision ids that exist in this Act.
        """
        refs = _refs.extract_references(provision.text or "")
        if resolve:
            ids = set(self._by_id)
            for r in refs:
                _refs.resolve(r, ids, context=provision)
        return refs

    def reference_graph(self, *, types: Optional[Iterable[PT]] = None) -> list[dict]:
        """All resolved internal reference edges across the Act.

        Returns a list of ``{"source": id, "target": id, "kind": ...}`` dicts —
        the reference graph called for in the Stage-0 ingestion deliverable.
        """
        wanted = set(types) if types else {
            PT.ARTICLE, PT.PARAGRAPH, PT.POINT, PT.RECITAL, PT.ANNEX,
        }
        ids = set(self._by_id)
        edges: list[dict] = []
        seen: set[tuple[str, str, str]] = set()
        for p in self.walk():
            if p.type not in wanted or not p.text:
                continue
            for r in _refs.extract_references(p.text):
                if r.external:
                    continue
                _refs.resolve(r, ids, context=p)
                for tid in r.target_ids:
                    key = (p.id, tid, r.kind)
                    if tid != p.id and key not in seen:
                        seen.add(key)
                        edges.append({"source": p.id, "target": tid,
                                      "kind": r.kind, "raw": r.raw})
        return edges

    # -- serialisation -------------------------------------------------------
    def to_dict(self, *, footnotes: bool = True) -> dict:
        data = {
            "regulation": "Regulation (EU) 2024/1689",
            "title": self.title,
            "source": "EUR-Lex (OJ L, 2024/1689) — consolidated EU AI Act",
            "document": self.document.to_dict(),
        }
        if footnotes:
            data["footnotes"] = [f.to_dict() for f in self.footnotes.values()]
        return data

    def to_json(self, path: Optional[Union[str, Path]] = None, *, indent: int = 2) -> str:
        text = json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text

    def stats(self) -> dict[str, int]:
        """Counts of each provision type (handy for sanity checks / tests)."""
        out: dict[str, int] = {}
        for p in self.walk():
            out[p.type.value] = out.get(p.type.value, 0) + 1
        out["footnote"] = len(self.footnotes)
        return out

    def __repr__(self) -> str:
        return (f"<AIAct {len(self.articles)} articles, "
                f"{len(self.recitals)} recitals, {len(self.annexes)} annexes>")
