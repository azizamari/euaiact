"""Typed data model for the EU AI Act.

The whole Act is represented as a tree of :class:`Provision` nodes. A single
node type (discriminated by :class:`ProvisionType`) keeps traversal,
serialisation and search uniform, while convenience accessors on
:class:`~euaiact.act.AIAct` give ergonomic, legally-named entry points
(``act.article(9)``, ``act.annex("III")`` ...).

Every node carries:

* ``id``      -- a stable, machine canonical path id, e.g. ``art_9.par_2.pt_a``.
* ``eli_id``  -- the raw id from the EUR-Lex HTML when present (provenance).
* ``citation``-- a human, legal-style label, e.g. ``Article 9(2), point (a)``.

These three together give every provision a stable handle for formalization
work (extraction, cross-reference edges, gold annotations) and a traceable link
back to the official source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator, Optional


class ProvisionType(str, Enum):
    """The kind of structural unit a :class:`Provision` represents."""

    DOCUMENT = "document"           # the whole Act (root)
    TITLE = "title"                 # the document title block
    PREAMBLE = "preamble"           # wrapper for citations + recitals
    CITATION = "citation"           # "Having regard to ..."
    RECITAL = "recital"             # numbered recital (1)-(180)
    CHAPTER = "chapter"             # CHAPTER I .. XIII
    SECTION = "section"             # SECTION n within a chapter
    ARTICLE = "article"             # Article 1 .. 113
    PARAGRAPH = "paragraph"         # numbered paragraph within an article
    POINT = "point"                 # (a)/(i)/(1) point, possibly nested
    ANNEX = "annex"                 # ANNEX I .. XIII
    SIGNATURE = "signature"         # closing signature block

    def __str__(self) -> str:  # nicer repr in f-strings
        return self.value


@dataclass
class Footnote:
    """An official footnote (OJ note) from the bottom of the document."""

    id: str           # canonical, e.g. "fn_5"
    number: str       # the printed marker, e.g. "5"
    text: str         # resolved footnote text
    eli_id: str = ""  # raw "ntr.." id

    def to_dict(self) -> dict:
        return {"id": self.id, "number": self.number, "text": self.text, "eli_id": self.eli_id}


@dataclass
class CrossReference:
    """A reference detected in provision text (e.g. "Article 6(2)", "Annex III").

    ``target_ids`` is filled by the resolver when the reference can be mapped to
    concrete provision id(s); ``external`` marks references to *other* legal acts
    (e.g. "Regulation (EU) 2016/679") which live outside this document.
    """

    raw: str                         # the exact matched substring
    kind: str                        # article|annex|paragraph|point|recital|external
    target_ids: list[str] = field(default_factory=list)
    external: bool = False

    def to_dict(self) -> dict:
        return {
            "raw": self.raw,
            "kind": self.kind,
            "target_ids": list(self.target_ids),
            "external": self.external,
        }


@dataclass
class Provision:
    """A single structural unit of the Act and its subtree."""

    id: str
    type: ProvisionType
    number: str = ""                 # "9", "2", "a", "III" ... (no decoration)
    heading: str = ""                # title/heading, e.g. "Risk management system"
    text: str = ""                   # own lead/chapeau text (excludes children)
    eli_id: str = ""                 # raw EUR-Lex id, if any
    citation: str = ""               # human legal label, e.g. "Article 9(2)"
    children: list["Provision"] = field(default_factory=list)
    footnote_ids: list[str] = field(default_factory=list)
    parent: Optional["Provision"] = field(default=None, repr=False, compare=False)

    # -- tree wiring ---------------------------------------------------------
    def add(self, child: "Provision") -> "Provision":
        child.parent = self
        self.children.append(child)
        return child

    # -- navigation ----------------------------------------------------------
    def walk(self, *, include_self: bool = True) -> Iterator["Provision"]:
        """Depth-first iteration over this provision and its descendants."""
        if include_self:
            yield self
        for child in self.children:
            yield from child.walk()

    def descendants(self) -> Iterator["Provision"]:
        return self.walk(include_self=False)

    def ancestors(self) -> Iterator["Provision"]:
        node = self.parent
        while node is not None:
            yield node
            node = node.parent

    def siblings(self) -> list["Provision"]:
        if self.parent is None:
            return []
        return [c for c in self.parent.children if c is not self]

    def of_type(self, *types: ProvisionType) -> list["Provision"]:
        """All descendants (and self) matching any of ``types``."""
        wanted = set(types)
        return [p for p in self.walk() if p.type in wanted]

    def ancestor_of_type(self, ptype: ProvisionType) -> Optional["Provision"]:
        for node in self.ancestors():
            if node.type == ptype:
                return node
        return None

    # -- text ----------------------------------------------------------------
    def full_text(self, *, indent: bool = True) -> str:
        """Readable text of the whole subtree (chapeau + nested points)."""
        lines: list[str] = []
        self._render(lines, depth=0, indent=indent)
        return "\n".join(line for line in lines if line.strip())

    def _render(self, lines: list[str], depth: int, indent: bool) -> None:
        pad = ("    " * depth) if indent else ""
        prefix = ""
        if self.type == ProvisionType.POINT and self.number:
            prefix = f"({self.number}) " if not self.number[0].isdigit() else f"{self.number}. "
        head = self.heading
        if head and self.type in (ProvisionType.ARTICLE, ProvisionType.CHAPTER,
                                  ProvisionType.SECTION, ProvisionType.ANNEX):
            label = self.citation or self.id
            lines.append(f"{pad}{label} — {head}" if head else f"{pad}{label}")
        if self.text:
            lines.append(f"{pad}{prefix}{self.text}")
        child_depth = depth + 1 if self.type != ProvisionType.DOCUMENT else depth
        for child in self.children:
            child._render(lines, child_depth, indent)

    @property
    def plain_text(self) -> str:
        """Flattened text of the subtree on a single logical run (no numbering)."""
        chunks = [p.text for p in self.walk() if p.text]
        return " ".join(chunks)

    # -- serialisation -------------------------------------------------------
    def to_dict(self, *, include_children: bool = True) -> dict:
        data: dict = {
            "id": self.id,
            "type": self.type.value,
            "number": self.number,
            "citation": self.citation,
        }
        if self.heading:
            data["heading"] = self.heading
        if self.text:
            data["text"] = self.text
        if self.eli_id:
            data["eli_id"] = self.eli_id
        if self.footnote_ids:
            data["footnote_ids"] = list(self.footnote_ids)
        if include_children and self.children:
            data["children"] = [c.to_dict() for c in self.children]
        return data

    def __repr__(self) -> str:
        label = self.citation or self.id
        head = f" {self.heading!r}" if self.heading else ""
        return f"<Provision {self.type} {label}{head}>"
