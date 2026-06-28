"""euaiact -- a zero-dependency Python SDK for the EU AI Act.

Parse the official EUR-Lex text of Regulation (EU) 2024/1689 (the EU AI Act)
into a navigable tree of provisions with stable, traceable ids, and query it
from Python.

    >>> from euaiact import AIAct
    >>> act = AIAct.load()
    >>> act.article(9).heading
    'Risk management system'
    >>> [p.citation for p in act.article(5).paragraph(1).children][:3]
    ['Article 5(1), point (a)', 'Article 5(1), point (b)', 'Article 5(1), point (c)']

The Act is free EU law and the consolidated HTML is bundled with the package.
"""

from .act import AIAct
from .model import (
    CrossReference,
    Footnote,
    Provision,
    ProvisionType,
)
from . import navigation as _navigation  # noqa: F401  (installs Provision helpers)

__all__ = [
    "AIAct",
    "Provision",
    "ProvisionType",
    "Footnote",
    "CrossReference",
]

__version__ = "0.1.0"
