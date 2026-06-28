"""A tiny, dependency-free DOM built on the standard-library HTML parser.

The EU AI Act HTML from EUR-Lex is well-structured XHTML, but it contains the
usual web cruft (unclosed ``<col>``/``<meta>`` tags, ``<br>``, entities). Rather
than pull in ``lxml`` or ``beautifulsoup4`` we build the minimal element tree we
need to navigate by ``id``/``class`` and extract text. Keeping the SDK
zero-dependency makes it trivial to vendor or publish.

The public surface is intentionally small:

* :class:`Element` -- a node with ``tag``, ``attrs``, ``children`` and helpers
  (:meth:`Element.text`, :meth:`Element.find_all`, :meth:`Element.get_by_id`...).
* :func:`parse` -- turn an HTML string into the root :class:`Element`.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from html import unescape

# Tags that never have children / are never closed in HTML.
_VOID_TAGS = frozenset(
    {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }
)

# Tags we drop entirely (content is irrelevant to the legislation text).
_SKIP_TAGS = frozenset({"script", "style", "head", "noscript"})


class Element:
    """A single DOM node (an HTML element or a text node)."""

    __slots__ = ("tag", "attrs", "children", "parent", "_text")

    def __init__(self, tag: str, attrs: dict[str, str] | None = None):
        self.tag = tag
        self.attrs: dict[str, str] = attrs or {}
        self.children: list[Element] = []
        self.parent: Element | None = None
        # For text nodes (tag == "#text") this holds the raw string.
        self._text: str | None = None

    # -- construction helpers ------------------------------------------------
    def append(self, child: "Element") -> None:
        child.parent = self
        self.children.append(child)

    # -- attribute access ----------------------------------------------------
    @property
    def id(self) -> str | None:
        return self.attrs.get("id")

    @property
    def classes(self) -> list[str]:
        return self.attrs.get("class", "").split()

    def has_class(self, name: str) -> bool:
        return name in self.classes

    @property
    def is_text(self) -> bool:
        return self.tag == "#text"

    # -- text extraction -----------------------------------------------------
    def text(self, separator: str = "") -> str:
        """Recursively collected, whitespace-normalised text of this subtree."""
        parts: list[str] = []
        self._collect_text(parts)
        raw = separator.join(parts)
        return _normalise_ws(raw)

    def _collect_text(self, out: list[str]) -> None:
        if self.is_text:
            if self._text:
                out.append(self._text)
            return
        if self.tag in _SKIP_TAGS:
            return
        for child in self.children:
            child._collect_text(out)

    def own_text(self) -> str:
        """Text of direct ``#text`` and inline children, excluding block tables.

        Used to read a provision's lead/chapeau text without dragging in the
        text of nested point tables.
        """
        parts: list[str] = []
        for child in self.children:
            if child.is_text:
                if child._text:
                    parts.append(child._text)
            elif child.tag not in ("table", "div"):
                child._collect_text(parts)
        return _normalise_ws("".join(parts))

    # -- traversal -----------------------------------------------------------
    def iter(self):
        """Depth-first iterator over all descendant elements (not text nodes)."""
        for child in self.children:
            if not child.is_text:
                yield child
                yield from child.iter()

    def find_all(self, predicate) -> list["Element"]:
        return [el for el in self.iter() if predicate(el)]

    def find(self, predicate) -> "Element | None":
        for el in self.iter():
            if predicate(el):
                return el
        return None

    def get_by_id(self, _id: str) -> "Element | None":
        return self.find(lambda el: el.attrs.get("id") == _id)

    def children_elements(self) -> list["Element"]:
        return [c for c in self.children if not c.is_text]

    def direct_descendants(self, tag: str, *, stop_tags=()):
        """Yield descendant elements with ``tag``, not crossing ``stop_tags``.

        Finds the *outermost* matching elements: once a match (or a stop tag) is
        found on a branch, recursion into it stops. This is how we grab a
        container's own point ``<table>`` elements without descending into the
        tables nested inside a point's content.
        """
        result: list[Element] = []

        def walk(node: Element):
            for child in node.children_elements():
                if child.tag == tag:
                    result.append(child)
                elif child.tag in stop_tags:
                    continue
                else:
                    walk(child)

        walk(self)
        return result

    def __repr__(self) -> str:
        if self.is_text:
            return f"#text({self._text!r:.30})"
        ident = self.attrs.get("id") or ".".join(self.classes)
        return f"<{self.tag} {ident}>"


def _normalise_ws(text: str) -> str:
    # EUR-Lex uses non-breaking spaces (\xa0) liberally; treat as normal spaces.
    text = text.replace("\xa0", " ").replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip()


class _TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Element("#root")
        self._stack: list[Element] = [self.root]
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        el = Element(tag, {k: (v or "") for k, v in attrs})
        self._stack[-1].append(el)
        if tag not in _VOID_TAGS:
            self._stack.append(el)

    def handle_startendtag(self, tag, attrs):
        # Self-closing like <br/>; treat as void.
        if tag in _SKIP_TAGS or self._skip_depth:
            return
        el = Element(tag, {k: (v or "") for k, v in attrs})
        self._stack[-1].append(el)

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag in _VOID_TAGS:
            return
        # Pop until we close the matching tag (tolerant of mis-nesting).
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i].tag == tag:
                del self._stack[i:]
                return
        # No match: ignore stray close tag.

    def handle_data(self, data):
        if self._skip_depth or not data:
            return
        node = Element("#text")
        node._text = data
        self._stack[-1].append(node)

    def handle_entityref(self, name):  # pragma: no cover - convert_charrefs on
        self.handle_data(unescape(f"&{name};"))

    def handle_charref(self, name):  # pragma: no cover - convert_charrefs on
        self.handle_data(unescape(f"&#{name};"))


def parse(html: str) -> Element:
    """Parse an HTML document into a :class:`Element` tree and return the root."""
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    return builder.root
