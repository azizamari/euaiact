# Contributing to euaiact

Thanks for your interest! This is a small, focused, **zero-dependency** library —
contributions that keep it that way are very welcome.

## Development setup

```bash
git clone https://github.com/azizamari/euaiact
cd euaiact
python -m venv .venv && source .venv/bin/activate
pip install -e . pytest
pytest -q
```

Python ≥ 3.9. The library itself has **no runtime dependencies** (standard
library only) — please don't add any. Test/dev tooling is fine.

## Architecture

```
src/euaiact/
  _dom.py        Minimal DOM on stdlib html.parser (no lxml/bs4). Element tree
                 with find_all / get_by_id / direct_descendants / text helpers.
  model.py       Provision (single node type, discriminated by ProvisionType),
                 Footnote, CrossReference — pure dataclasses + tree/text helpers.
  navigation.py  Ergonomic child accessors installed onto Provision
                 (.paragraph(n), .point(x), .article(n)).
  parser.py      HTML → Provision tree + footnotes. The mapping table at the top
                 documents every HTML class/id the parser relies on.
  references.py  Regex extraction + conservative resolution of cross-references
                 (the source does NOT hyperlink internal refs).
  act.py         AIAct facade: load / collections / accessors / search / graph / to_json.
  __main__.py    CLI (python -m euaiact ...).
  data/          Bundled consolidated HTML (free EU law).
```

### How the EUR-Lex HTML maps (load-bearing facts)

- One main `div.eli-container` holds title → preamble (`#pbl_1`: `cit_N`, `rct_N`)
  → chapters (`#cpt_<ROMAN>`) → sections (`#cpt_X.sct_N`) → articles
  (`div.eli-subdivision#art_N`). Annexes are separate `div.eli-container#anx_<ROMAN>`.
- Numbered paragraphs are `div#NNN.MMM` (zero-padded article.paragraph).
- **Points are nested `<table>`**: row = `[marker-td, content-td]`; content holds
  lead text + nested point tables (recursive).
- Footnotes: `p.oj-note` after an `<hr>`; caller `a[id^=ntc]`, definition `a[id^=ntr]`.
- Cross-references are **plain prose**, not links — handled in `references.py`.

## Invariants the tests protect

113 articles · 180 recitals · 7 citations · 13 chapters · 16 sections ·
13 annexes · 58 footnotes · 68 definitions in Article 3 · 8 high-risk areas in
Annex III. If you change the parser, run `pytest` — these counts catch
regressions against the bundled markup.

## Guidelines

- Keep the core dependency-free; prefer stdlib.
- Reference resolution is intentionally conservative — it only emits a
  `target_id` when the id exists in the parsed Act. Don't make it speculative.
- Add/adjust a test for any parser or API change.
- Conventional-commit style messages (`feat:`, `fix:`, `docs:`, `test:`,
  `chore:`) are appreciated.

## Licence

By contributing you agree your contributions are licensed under the project's MIT
License.
