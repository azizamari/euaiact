"""Ergonomic child-accessor helpers attached to :class:`Provision`.

Kept separate from ``model.py`` so the data model stays a pure dataclass tree.
Importing :mod:`euaiact` installs these methods onto :class:`Provision`.
"""

from __future__ import annotations

from typing import Optional, Union

from .model import Provision, ProvisionType as PT


def _child_by_number(self: Provision, number: Union[str, int],
                     ptype: Optional[PT] = None) -> Optional[Provision]:
    target = str(number)
    for c in self.children:
        if c.number == target and (ptype is None or c.type == ptype):
            return c
    return None


def paragraph(self: Provision, number: Union[str, int]) -> Provision:
    """Return the numbered paragraph ``number`` of this article."""
    p = _child_by_number(self, number, PT.PARAGRAPH)
    if p is None:
        raise KeyError(f"{self.citation or self.id} has no paragraph {number}")
    return p


def point(self: Provision, marker: str) -> Provision:
    """Return the point with letter/number ``marker`` (e.g. ``"a"``, ``"i"``)."""
    p = _child_by_number(self, str(marker), PT.POINT)
    if p is None:
        raise KeyError(f"{self.citation or self.id} has no point ({marker})")
    return p


def article(self: Provision, number: Union[str, int]) -> Provision:
    """Return child article ``number`` (for chapters / sections)."""
    for a in self.of_type(PT.ARTICLE):
        if a.number == str(number):
            return a
    raise KeyError(f"{self.citation or self.id} has no Article {number}")


def child(self: Provision, number: Union[str, int]) -> Optional[Provision]:
    """Return the first child whose ``number`` matches (any type)."""
    return _child_by_number(self, number)


# Install onto Provision.
for _fn in (paragraph, point, article, child):
    setattr(Provision, _fn.__name__, _fn)
