# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [0.1.0] — 2026-06

Initial public release.

### Added
- Zero-dependency parser for the EUR-Lex HTML of the EU AI Act
  (Regulation (EU) 2024/1689), built on the Python standard library only.
- `AIAct` facade: collections (`articles`, `recitals`, `citations`, `chapters`,
  `sections`, `annexes`), single-item accessors (`article`, `recital`, `annex`,
  `chapter`, `citation`), id lookup (`get` / `[]` / `in`), depth-first `walk`,
  full-text `search` (plain or regex; own-text or whole-subtree).
- `Provision` tree with three stable handles per node — canonical `id`
  (`art_9.par_2.pt_a`), raw EUR-Lex `eli_id`, and a human `citation`
  (`Article 9(2), point (a)`) — plus navigation (`parent`, `children`,
  `ancestors`, `siblings`, `walk`) and text views (`text`, `full_text`,
  `plain_text`).
- Cross-reference extraction and conservative resolution (the source does not
  hyperlink internal references): per-provision `references()` and a whole-Act
  `reference_graph()`.
- Footnote parsing and linkage (`footnote`, `footnotes_for`).
- Serialization: `to_dict()` / `to_json()` and `stats()`.
- Command-line interface: `euaiact stats | show | search | export | graph`.
- Bundled consolidated Act text (no network access required).
- Test suite asserting structural invariants (113 articles, 180 recitals,
  13 annexes, 68 definitions in Article 3, 8 high-risk areas in Annex III, …).

[0.1.0]: https://github.com/azizamari/euaiact/releases/tag/v0.1.0
