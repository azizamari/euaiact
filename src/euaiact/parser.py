"""Parse the EUR-Lex HTML of the EU AI Act into a :class:`Provision` tree.

The mapping from the EUR-Lex "CONVEX" HTML to our model:

================================  ===================================  =====================
HTML                              meaning                              ProvisionType
================================  ===================================  =====================
``p.oj-doc-ti`` (top)             regulation title                     TITLE
``div#pbl_1``                     preamble wrapper                     PREAMBLE
``div.eli-subdivision#cit_N``     citation ("Having regard to ...")    CITATION
``div.eli-subdivision#rct_N``     recital (N)                          RECITAL
``div#cpt_<ROMAN>``               CHAPTER                              CHAPTER
``div#cpt_X.sct_N``               SECTION                              SECTION
``div.eli-subdivision#art_N``     Article N                            ARTICLE
``div#NNN.MMM``                   numbered paragraph                   PARAGRAPH
nested ``<table>`` (marker|body)  point (a)/(i)/(1)                    POINT
``div.eli-container#anx_<ROMAN>`` ANNEX                                ANNEX
``p.oj-note`` (after ``<hr>``)    official footnote                    (Footnote)
================================  ===================================  =====================
"""

from __future__ import annotations

import re

from ._dom import Element, parse as parse_dom
from .model import Footnote, Provision, ProvisionType as PT

# --------------------------------------------------------------------------- #
# Roman numerals (chapters and annexes are numbered I .. XIII).
# --------------------------------------------------------------------------- #
_ROMAN_VALUES = [
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
    (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
    (5, "V"), (4, "IV"), (1, "I"),
]


def int_to_roman(n: int) -> str:
    out = []
    for value, sym in _ROMAN_VALUES:
        while n >= value:
            out.append(sym)
            n -= value
    return "".join(out)


def roman_to_int(s: str) -> int:
    s = s.upper()
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total, prev = 0, 0
    for ch in reversed(s):
        cur = vals.get(ch, 0)
        total += -cur if cur < prev else cur
        prev = cur
    return total


_NUM_PREFIX_RE = re.compile(r"^\s*\(?\s*(\d+)\s*[.)]\s*")          # "1.   " / "(1) "
_MARKER_RE = re.compile(r"^\s*\(?\s*([0-9]+|[a-z]+|[ivxlcdm]+)\s*[.)]?\s*$", re.I)
_CPT_RE = re.compile(r"^cpt_([IVXLCDM]+)$")
_SCT_RE = re.compile(r"^cpt_[IVXLCDM]+\.sct_(\d+)$")
_ART_RE = re.compile(r"^art_(\d+)$")
_PARA_RE = re.compile(r"^(\d{3})\.(\d{3})$")
_ANX_RE = re.compile(r"^anx_([IVXLCDM]+)$")


# --------------------------------------------------------------------------- #
# Small DOM helpers
# --------------------------------------------------------------------------- #
def _direct_paragraph_text(el: Element) -> str:
    """Join the text of ``<p>`` elements directly in ``el`` (not inside tables)."""
    ps = el.direct_descendants("p", stop_tags=("table",))
    return " ".join(p.text() for p in ps if p.text()).strip()


def _strip_num_prefix(text: str) -> str:
    return _NUM_PREFIX_RE.sub("", text, count=1).strip()


def _parse_marker(raw: str) -> str:
    """Turn a point marker cell ("(a)", "1.", "(iv)") into a bare token."""
    m = _MARKER_RE.match(raw.strip())
    if m:
        return m.group(1)
    return raw.strip().strip("().").strip()


def _collect_footnote_ids(el: Element) -> list[str]:
    """Footnote markers referenced inside ``el`` -> ["fn_5", ...] (de-duped)."""
    ids: list[str] = []
    for a in el.find_all(lambda e: e.tag == "a" and e.attrs.get("id", "").startswith("ntc")):
        m = re.match(r"ntc(\d+)", a.attrs["id"])
        if m:
            fid = f"fn_{int(m.group(1))}"
            if fid not in ids:
                ids.append(fid)
    return ids


# --------------------------------------------------------------------------- #
# Points (recursive)
# --------------------------------------------------------------------------- #
def _point_citation(parent: Provision, marker: str) -> str:
    base = parent.citation or parent.id
    if parent.type == PT.POINT:
        return f"{base}({marker})"
    return f"{base}, point ({marker})"


def _parse_points(container: Element, parent: Provision) -> None:
    """Find this container's top-level point tables and attach them to ``parent``."""
    tables = container.direct_descendants("table", stop_tags=("table",))
    for table in tables:
        for tr in table.direct_descendants("tr", stop_tags=("table",)):
            cells = tr.direct_descendants("td", stop_tags=("table",))
            if len(cells) < 2:
                continue
            marker = _parse_marker(cells[0].text())
            body = cells[1]
            lead = _direct_paragraph_text(body)
            pid = f"{parent.id}.pt_{marker}"
            point = Provision(
                id=pid,
                type=PT.POINT,
                number=marker,
                text=lead,
                citation=_point_citation(parent, marker),
                footnote_ids=_collect_footnote_ids(body),
            )
            parent.add(point)
            _parse_points(body, point)  # nested sub-points


# --------------------------------------------------------------------------- #
# Articles
# --------------------------------------------------------------------------- #
def _article_heading(el: Element) -> str:
    title = el.find(lambda e: e.tag == "p" and e.has_class("oj-sti-art"))
    return title.text() if title else ""


def _parse_paragraph(div: Element, article: Provision) -> Provision:
    m = _PARA_RE.match(div.id or "")
    par_no = str(int(m.group(2))) if m else (div.id or "")
    lead_p = div.find(lambda e: e.tag == "p" and e.has_class("oj-normal"))
    raw = lead_p.text() if lead_p else ""
    text = _strip_num_prefix(raw)
    para = Provision(
        id=f"{article.id}.par_{par_no}",
        type=PT.PARAGRAPH,
        number=par_no,
        text=text,
        eli_id=div.id or "",
        citation=f"{article.citation}({par_no})",
        footnote_ids=_collect_footnote_ids(div),
    )
    _parse_points(div, para)
    return para


def _parse_article(el: Element) -> Provision:
    m = _ART_RE.match(el.id or "")
    num = m.group(1) if m else (el.id or "")
    article = Provision(
        id=f"art_{num}",
        type=PT.ARTICLE,
        number=num,
        heading=_article_heading(el),
        eli_id=el.id or "",
        citation=f"Article {num}",
    )

    # Numbered paragraphs (div#NNN.MMM) are the common case.
    para_divs = [
        c for c in el.children_elements()
        if c.tag == "div" and _PARA_RE.match(c.id or "")
    ]
    if para_divs:
        # Any chapeau text before the first numbered paragraph.
        chapeau = el.direct_descendants("p", stop_tags=("div", "table"))
        chap = [p.text() for p in chapeau if p.has_class("oj-normal") and p.text()]
        article.text = " ".join(chap).strip()
        for div in para_divs:
            article.add(_parse_paragraph(div, article))
    else:
        # Unnumbered body: chapeau text + point tables (e.g. Article 3 definitions).
        article.text = _direct_paragraph_text(el)
        article.footnote_ids = _collect_footnote_ids(el)
        _parse_points(el, article)
    return article


# --------------------------------------------------------------------------- #
# Chapters / sections
# --------------------------------------------------------------------------- #
def _section_heading(el: Element) -> str:
    title = el.find(
        lambda e: e.tag == "p" and e.has_class("oj-ti-section-2")
    )
    return title.text() if title else ""


def _nearest_section(article_el: Element) -> Element | None:
    node = article_el.parent
    while node is not None:
        if node.id and _SCT_RE.match(node.id):
            return node
        node = node.parent
    return None


def _parse_chapter(el: Element, root: Element) -> Provision:
    m = _CPT_RE.match(el.id or "")
    roman = m.group(1) if m else (el.id or "")
    chapter = Provision(
        id=f"cpt_{roman}",
        type=PT.CHAPTER,
        number=str(roman_to_int(roman)),
        heading=_section_heading(el),
        eli_id=el.id or "",
        citation=f"Chapter {roman}",
    )

    # Build section nodes for this chapter, keyed by their element.
    section_provisions: dict[str, Provision] = {}
    for sct in el.find_all(lambda e: e.id and _SCT_RE.match(e.id or "")):
        sm = _SCT_RE.match(sct.id)
        sec = Provision(
            id=sct.id,
            type=PT.SECTION,
            number=sm.group(1),
            heading=_section_heading(sct),
            eli_id=sct.id,
            citation=f"Chapter {roman}, Section {sm.group(1)}",
        )
        section_provisions[sct.id] = sec
        chapter.add(sec)

    # Attach articles to their section (if any) or directly to the chapter.
    for art_el in el.find_all(lambda e: e.id and _ART_RE.match(e.id or "")):
        article = _parse_article(art_el)
        sct_el = _nearest_section(art_el)
        if sct_el is not None and sct_el.id in section_provisions:
            section_provisions[sct_el.id].add(article)
        else:
            chapter.add(article)
    return chapter


# --------------------------------------------------------------------------- #
# Recitals / citations / annexes
# --------------------------------------------------------------------------- #
def _parse_recital(el: Element) -> Provision:
    num = (el.id or "").replace("rct_", "")
    cells = el.direct_descendants("td", stop_tags=("table",))
    text = cells[1].text() if len(cells) >= 2 else _direct_paragraph_text(el)
    return Provision(
        id=f"rct_{num}",
        type=PT.RECITAL,
        number=num,
        text=text,
        eli_id=el.id or "",
        citation=f"Recital {num}",
        footnote_ids=_collect_footnote_ids(el),
    )


def _parse_citation(el: Element) -> Provision:
    num = (el.id or "").replace("cit_", "")
    return Provision(
        id=f"cit_{num}",
        type=PT.CITATION,
        number=num,
        text=_direct_paragraph_text(el),
        eli_id=el.id or "",
        citation=f"Citation {num}",
        footnote_ids=_collect_footnote_ids(el),
    )


def _parse_annex(el: Element) -> Provision:
    m = _ANX_RE.match(el.id or "")
    roman = m.group(1) if m else (el.id or "")
    titles = el.direct_descendants("p", stop_tags=("table", "div"))
    doc_titles = [p.text() for p in titles if p.has_class("oj-doc-ti")]
    heading = doc_titles[1] if len(doc_titles) > 1 else ""
    annex = Provision(
        id=f"anx_{roman}",
        type=PT.ANNEX,
        number=str(roman_to_int(roman)),
        heading=heading,
        eli_id=el.id or "",
        citation=f"Annex {roman}",
    )
    # Lead text: oj-normal paragraphs that sit directly under the annex.
    lead = [
        p.text() for p in el.direct_descendants("p", stop_tags=("table",))
        if p.has_class("oj-normal") and p.text()
    ]
    annex.text = " ".join(lead).strip()
    annex.footnote_ids = _collect_footnote_ids(el)
    _parse_points(el, annex)
    return annex


# --------------------------------------------------------------------------- #
# Footnotes
# --------------------------------------------------------------------------- #
def _parse_footnotes(root: Element) -> dict[str, Footnote]:
    notes: dict[str, Footnote] = {}
    for p in root.find_all(lambda e: e.tag == "p" and e.has_class("oj-note")):
        anchor = p.find(
            lambda e: e.tag == "a" and e.attrs.get("id", "").startswith("ntr")
        )
        if not anchor:
            continue
        m = re.match(r"ntr(\d+)", anchor.attrs["id"])
        if not m:
            continue
        number = m.group(1)
        full = p.text()
        # Drop the leading "(N)" marker to leave the note body.
        body = re.sub(rf"^\(?\s*{number}\s*\)?\s*", "", full).strip()
        fid = f"fn_{int(number)}"
        notes[fid] = Footnote(
            id=fid, number=number, text=body, eli_id=anchor.attrs["id"]
        )
    return notes


# --------------------------------------------------------------------------- #
# Top-level
# --------------------------------------------------------------------------- #
def parse_html(html: str) -> tuple[Provision, dict[str, Footnote]]:
    """Parse the Act HTML; return ``(root_document, footnotes_by_id)``."""
    root = parse_dom(html)

    document = Provision(
        id="aiact",
        type=PT.DOCUMENT,
        number="2024/1689",
        citation="Regulation (EU) 2024/1689",
    )

    # Document title: the oj-doc-ti lines that appear (in document order) before
    # the preamble. Later oj-doc-ti elements are annex titles, so we stop at pbl.
    pbl = root.get_by_id("pbl_1")
    title_lines: list[str] = []
    for el in root.iter():
        if el is pbl:
            break
        if el.tag == "p" and el.has_class("oj-doc-ti") and el.text():
            title_lines.append(el.text())
    if title_lines:
        # The most descriptive line ("laying down harmonised rules ... (AI Act)").
        document.heading = max(title_lines, key=len)
        document.add(
            Provision(id="title", type=PT.TITLE, text=" / ".join(title_lines))
        )

    # Preamble: citations + recitals.
    if pbl is not None:
        preamble = Provision(id="preamble", type=PT.PREAMBLE, citation="Preamble")
        document.add(preamble)
        for el in pbl.find_all(lambda e: (e.id or "").startswith("cit_")):
            preamble.add(_parse_citation(el))
        for el in pbl.find_all(lambda e: re.match(r"^rct_\d+$", e.id or "")):
            preamble.add(_parse_recital(el))

    # Enacting terms: chapters (in document order) with their articles.
    seen_chapters = set()
    for el in root.find_all(lambda e: e.id and _CPT_RE.match(e.id or "")):
        if el.id in seen_chapters:
            continue
        seen_chapters.add(el.id)
        document.add(_parse_chapter(el, root))

    # Annexes.
    for el in root.find_all(lambda e: e.id and _ANX_RE.match(e.id or "")):
        document.add(_parse_annex(el))

    footnotes = _parse_footnotes(root)
    return document, footnotes
