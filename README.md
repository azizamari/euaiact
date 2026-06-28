# euaiact

[![CI](https://github.com/azizamari/euaiact/actions/workflows/ci.yml/badge.svg)](https://github.com/azizamari/euaiact/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](pyproject.toml)

A small, **zero-dependency** Python SDK for the **EU AI Act**
(Regulation (EU) 2024/1689). It parses the official EUR-Lex HTML into a navigable
tree of provisions with stable, traceable ids, and lets you query the Act from
Python — articles, paragraphs, points, recitals, annexes, cross-references and
footnotes.

The consolidated, free-to-reuse text is **bundled with the package**, so it works
fully offline.

```python
from euaiact import AIAct

act = AIAct.load()                       # parse the bundled EU AI Act
act.article(9).heading                   # 'Risk management system'
act.article(5).paragraph(1).point("a")   # <Provision point Article 5(1), point (a)>
act.annex("III").heading                 # 'High-risk AI systems referred to in Article 6(2)'
print(act.article(9).paragraph(2).full_text())
```

## Features

- 🪶 **Zero runtime dependencies** — standard library only; trivial to vendor.
- 🌳 **Whole-Act tree** — chapters → sections → articles → paragraphs → points,
  plus recitals, citations, annexes and footnotes.
- 🔖 **Three stable handles per provision** — a canonical `id`, the raw EUR-Lex
  `eli_id`, and a human legal `citation`.
- 🔗 **Cross-reference extraction & resolution** — internal references are plain
  prose in the source; this turns them into explicit id-to-id edges.
- 🔎 **Search** — substring or regex, over a provision's own text or its subtree.
- 📦 **Serialization & CLI** — `to_json()`, `reference_graph()`, and a
  `euaiact` command-line tool.
- 📴 **Offline** — the consolidated Act text ships with the package.

## Installation

Install directly from GitHub:

```bash
pip install git+https://github.com/azizamari/euaiact
```

Or from a local clone:

```bash
git clone https://github.com/azizamari/euaiact
cd euaiact
pip install -e .
```

Requires Python ≥ 3.9. No third-party dependencies.

## Concepts

The whole Act is a tree of **`Provision`** nodes, discriminated by
**`ProvisionType`**: `DOCUMENT → CHAPTER → SECTION → ARTICLE → PARAGRAPH →
POINT`, plus `RECITAL`, `CITATION`, `ANNEX`, `TITLE`, `PREAMBLE`, `SIGNATURE`.

Every provision carries three handles:

| field      | example                       | purpose                                  |
|------------|-------------------------------|------------------------------------------|
| `id`       | `art_9.par_2.pt_a`            | stable machine id (canonical path)       |
| `eli_id`   | `005.001`, `art_5`, `rct_12`  | raw EUR-Lex id (provenance / round-trip) |
| `citation` | `Article 9(2), point (a)`     | human, legal-style label                 |

### Id scheme

```
art_5                     Article 5
art_5.par_1               Article 5(1)
art_5.par_1.pt_a          Article 5(1), point (a)
art_5.par_1.pt_h.pt_i     Article 5(1), point (h)(i)
rct_12                    Recital 12
cit_3                     Citation 3
cpt_III                   Chapter III
cpt_III.sct_2             Chapter III, Section 2
anx_III                   Annex III
anx_III.pt_1.pt_a         Annex III, point 1(a)
fn_5                      Footnote 5
```

## API reference

### Loading

```python
AIAct.load()                       # parse the bundled consolidated text
AIAct.from_file(path)              # parse an EU AI Act HTML file
AIAct.from_html(html_string)       # parse an HTML string
```

### Collections

```python
act.title                          # the regulation's descriptive title
act.chapters                       # list[Provision]  (13)
act.articles                       # list[Provision]  (113)
act.recitals                       # list[Provision]  (180)
act.citations                      # list[Provision]  (7)
act.sections                       # list[Provision]  (16)
act.annexes                        # list[Provision]  (13)
```

### Single-item accessors (accept int or Roman where relevant)

```python
act.article(9)                     act.recital(12)        act.citation(3)
act.chapter("III")                 act.annex(3)           act.annex("III")
```

### Lookup by id or citation

```python
act.get("art_9.par_2")             # by canonical id; None if absent
act.get("005.001")                 # by raw EUR-Lex id
act.get("Article 9(2)")            # by human legal citation
act["005.001"]                     # __getitem__ (raises KeyError if absent)
"anx_III" in act                   # membership
```

### Navigating within a provision

```python
art = act.article(5)
art.paragraph(1)                   # child paragraph by number
art.paragraph(1).point("a")        # child point by marker
art.parent, art.children
art.siblings()                     # list[Provision]
p.ancestors()                      # generator, innermost-first
p.ancestor_of_type(ProvisionType.ARTICLE)
p.descendants()                    # generator, depth-first
p.walk()                           # self + descendants, depth-first
p.of_type(ProvisionType.POINT)     # matching nodes in the subtree
```

### Text

```python
prov.text                          # own lead/chapeau text (excludes children)
prov.full_text()                   # rendered subtree, with numbering/headings
prov.plain_text                    # flattened subtree text (no numbering)
```

### Search

```python
act.search("human oversight")                              # own-text substring
act.search("human oversight", whole_subtree=True)          # match subtree text
act.search(r"high[- ]risk", regex=True)                    # regex
act.search("provider", types=[ProvisionType.PARAGRAPH])    # filter by type
```

### Cross-references

```python
for ref in act.references(act.article(6).paragraph(1)):
    print(ref.raw, ref.kind, ref.target_ids, ref.external)
# e.g.  'Annex III'   annex   ['anx_III']   False
#       'paragraph 1' paragraph ['art_6.par_1'] False

act.reference_graph()              # [{"source", "target", "kind", "raw"}, ...]
```

### Footnotes

```python
act.footnote(5).text               # footnote by number / "fn_5"
act.footnotes_for(act.citation(4)) # footnotes referenced by a provision
```

### Serialization & stats

```python
act.to_dict()                      # nested dict (whole tree + footnotes)
act.to_json("aiact.json")          # write JSON; also returns the string
act.stats()                        # {'article': 113, 'recital': 180, ...}
```

## Command line

```bash
python -m euaiact stats                 # provision counts
python -m euaiact show art_9            # print a provision's text
python -m euaiact search "human oversight"
python -m euaiact export aiact.json     # whole Act → JSON
python -m euaiact graph edges.json      # internal cross-reference graph → JSON
```

## Data-model fidelity

Validated against the consolidated 2024/1689 text (asserted by the test suite):

| unit                  | count |
|-----------------------|-------|
| articles              | 113   |
| recitals              | 180   |
| citations             | 7     |
| chapters              | 13    |
| sections              | 16    |
| annexes               | 13    |
| footnotes             | 58    |
| definitions (Art 3)   | 68    |
| high-risk areas (Annex III) | 8 |

## Roadmap

Planned next steps (contributions welcome):

- **Multilingual support** — the Act is published in all 24 official EU
  languages. Load any language version (e.g. `AIAct.load(lang="fr")`) by
  bundling/fetching the corresponding EUR-Lex HTML. The structural parser is
  language-agnostic (it keys on EUR-Lex ids/classes), so the provision tree comes
  for free; reference-phrase extraction would gain per-language patterns.
- **Previous revisions** — support consolidated versions and amendments over
  time: point-in-time loading and diffs between versions, addressed by EUR-Lex
  CELEX / consolidation identifiers.
- **Richer annex structure** — annexes are already parsed to point level; model
  their internal sub-sections / group headings (e.g. the lettered sections of
  Annex VII) as first-class nodes.

Ideas and contributions welcome — open an
[issue](https://github.com/azizamari/euaiact/issues).

## Development

```bash
pip install -e . pytest
pytest -q
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for architecture notes and the
HTML-to-model mapping.

## Licence & data provenance

SDK code: **MIT** (see [LICENSE](LICENSE)). Bundled text: Regulation (EU)
2024/1689, Official Journal of the EU — free EU law, reuse authorised under
Commission Decision 2011/833/EU with source acknowledgement. Not affiliated with
or endorsed by the European Union. Canonical source:
<https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng>.

## Citation

```bibtex
@software{euaiact,
  title  = {euaiact: a zero-dependency Python SDK for the EU AI Act},
  author = {Amari, Aziz},
  year   = {2026},
  url    = {https://github.com/azizamari/euaiact}
}
```
