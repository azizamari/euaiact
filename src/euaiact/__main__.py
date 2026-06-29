"""Command-line interface: ``python -m euaiact`` / ``euaiact``.

Examples::

    euaiact stats                       # provision counts
    euaiact show art_9                  # print a provision's text
    euaiact show "Article 5(1)(a)"      # also accepts citation-like ids via id
    euaiact search "human oversight"    # full-text search
    euaiact search "risk" --type article
    euaiact export aiact.json           # whole Act -> JSON
    euaiact graph edges.json            # internal cross-reference graph -> JSON
"""

from __future__ import annotations

import argparse
import json
import sys

from .act import AIAct
from .model import ProvisionType as PT

_SEARCH_TYPE_CHOICES = tuple(t.value for t in PT)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="euaiact", description="EU AI Act SDK")
    parser.add_argument("--file", help="path to an EU AI Act HTML file (defaults to bundled)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("stats", help="print provision counts")

    p_show = sub.add_parser("show", help="print a provision by id / eli id")
    p_show.add_argument("id")
    p_show.add_argument("--no-indent", action="store_true")

    p_search = sub.add_parser("search", help="full-text search")
    p_search.add_argument("query")
    p_search.add_argument("--regex", action="store_true")
    p_search.add_argument("--subtree", action="store_true", help="match whole subtree text")
    p_search.add_argument(
        "--type",
        dest="types",
        action="append",
        choices=_SEARCH_TYPE_CHOICES,
        help="limit matches to a provision type; repeat to include multiple types",
    )

    p_export = sub.add_parser("export", help="serialise the whole Act to JSON")
    p_export.add_argument("out")

    p_graph = sub.add_parser("graph", help="export the internal cross-reference graph")
    p_graph.add_argument("out")

    args = parser.parse_args(argv)
    act = AIAct.from_file(args.file) if args.file else AIAct.load()

    if args.cmd == "stats":
        for k, v in act.stats().items():
            print(f"{k:>10}: {v}")
    elif args.cmd == "show":
        prov = act.get(args.id)
        if prov is None:
            print(f"not found: {args.id}", file=sys.stderr)
            return 1
        print(prov.full_text(indent=not args.no_indent))
    elif args.cmd == "search":
        types = [PT(t) for t in args.types] if args.types else None
        hits = act.search(args.query, regex=args.regex, whole_subtree=args.subtree, types=types)
        for p in hits:
            print(f"{p.id:<22} {p.citation}")
        print(f"\n{len(hits)} match(es).", file=sys.stderr)
    elif args.cmd == "export":
        act.to_json(args.out)
        print(f"wrote {args.out}", file=sys.stderr)
    elif args.cmd == "graph":
        edges = act.reference_graph()
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(edges, fh, ensure_ascii=False, indent=2)
        print(f"wrote {len(edges)} edges to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
