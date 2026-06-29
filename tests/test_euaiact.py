"""Tests for the euaiact SDK.

Run with ``pytest`` (or ``python -m pytest``). They double as executable
documentation and as a structural-integrity check on the bundled HTML: if the
EUR-Lex markup ever changes shape, these counts catch it.
"""

import json

import pytest

from euaiact import AIAct, ProvisionType as PT
from euaiact.__main__ import main


@pytest.fixture(scope="module")
def act() -> AIAct:
    return AIAct.load()


# --------------------------------------------------------------------------- #
# Structural counts (ground truth for the consolidated 2024/1689 text).
# --------------------------------------------------------------------------- #
def test_top_level_counts(act):
    assert len(act.articles) == 113
    assert len(act.recitals) == 180
    assert len(act.citations) == 7
    assert len(act.chapters) == 13
    assert len(act.annexes) == 13
    assert len(act.sections) == 16


def test_article_3_has_68_definitions(act):
    art3 = act.article(3)
    assert art3.heading == "Definitions"
    points = [c for c in art3.children if c.type == PT.POINT]
    assert len(points) == 68
    assert points[0].number == "1"
    assert "AI system" in points[0].text


def test_annex_iii_high_risk_areas(act):
    anx = act.annex("III")
    assert "high-risk" in anx.heading.lower()
    assert len([c for c in anx.children if c.type == PT.POINT]) == 8


# --------------------------------------------------------------------------- #
# Navigation & ids
# --------------------------------------------------------------------------- #
def test_article_navigation(act):
    art9 = act.article(9)
    assert art9.id == "art_9"
    assert art9.heading == "Risk management system"
    assert art9.paragraph(2).id == "art_9.par_2"
    assert art9.paragraph(2).citation == "Article 9(2)"


def test_nested_point_ids_and_citations(act):
    pt = act.article(5).paragraph(1).point("h").point("i")
    assert pt.id == "art_5.par_1.pt_h.pt_i"
    assert pt.citation == "Article 5(1), point (h)(i)"
    assert pt.type == PT.POINT


def test_lookup_by_canonical_and_eli_id(act):
    assert act.get("art_5.par_1") is act["005.001"]      # canonical vs raw eli id
    assert "anx_III" in act
    assert act.get("does_not_exist") is None


def test_lookup_by_legal_citation(act):
    assert act.get("Article 5") is act.article(5)
    assert act.get("Article 5(1)").id == "art_5.par_1"
    assert act.get("Article 5(1)(a)").id == "art_5.par_1.pt_a"
    assert act.get("Article 5(1), point (a)").id == "art_5.par_1.pt_a"
    assert act.get("Article 5(1), point (h)(i)").id == "art_5.par_1.pt_h.pt_i"
    assert act.get("Article 3, point (1)").id == "art_3.pt_1"
    assert act.get("Recital 12").id == "rct_12"
    assert act.get("Annex III").id == "anx_III"
    assert act.get("Annex III, point 1(a)").id == "anx_III.pt_1.pt_a"
    assert act.get("Chapter III, Section 1").id == "cpt_III.sct_1"
    assert act.get("Banana 99") is None


def test_annex_accepts_roman_or_int(act):
    assert act.annex("III") is act.annex(3)


def test_parent_and_ancestors(act):
    pt = act.article(5).paragraph(1).point("a")
    art = pt.ancestor_of_type(PT.ARTICLE)
    assert art.id == "art_5"
    assert act.article(5).ancestor_of_type(PT.CHAPTER).id == "cpt_II"


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #
def test_search_returns_provisions(act):
    hits = act.search("human oversight", whole_subtree=True, types=[PT.ARTICLE])
    assert any(h.id == "art_14" for h in hits)


def test_search_regex(act):
    hits = act.search(r"high[- ]risk AI system", regex=True)
    assert hits


# --------------------------------------------------------------------------- #
# Cross references
# --------------------------------------------------------------------------- #
def test_reference_resolution(act):
    a6p1 = act.article(6).paragraph(1)
    refs = act.references(a6p1)
    targets = {t for r in refs for t in r.target_ids}
    # Article 6(1) cross-refers to its own points (a) and (b).
    assert "art_6.par_1.pt_a" in targets


def test_reference_graph_is_nonempty_and_deduped(act):
    edges = act.reference_graph()
    assert len(edges) > 300
    keys = [(e["source"], e["target"], e["kind"]) for e in edges]
    assert len(keys) == len(set(keys))


def test_external_references_flagged(act):
    # Recital/Article text referencing the GDPR should be flagged external.
    found = False
    for p in act.walk():
        for r in act.references(p):
            if r.external and "2016/679" in r.raw:
                found = True
    assert found


# --------------------------------------------------------------------------- #
# Footnotes
# --------------------------------------------------------------------------- #
def test_footnotes_parsed_and_linked(act):
    assert len(act.footnotes) == 58
    cit = act.citation(4)
    notes = act.footnotes_for(cit)
    assert notes and notes[0].text


# --------------------------------------------------------------------------- #
# Serialisation
# --------------------------------------------------------------------------- #
def test_to_dict_roundtrips_through_json(act):
    blob = act.to_json()
    data = json.loads(blob)
    assert data["regulation"] == "Regulation (EU) 2024/1689"
    assert data["document"]["type"] == "document"
    # Every node has the three stable handles we rely on.
    def check(node):
        assert "id" in node and "type" in node and "citation" in node
        for child in node.get("children", []):
            check(child)
    check(data["document"])


def test_stats(act):
    s = act.stats()
    assert s["article"] == 113
    assert s["footnote"] == 58


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def test_cli_show_accepts_citation_like_id(capsys):
    assert main(["show", "Article 5(1)(a)"]) == 0
    captured = capsys.readouterr()
    assert "subliminal techniques" in captured.out
    assert not captured.err


def test_cli_stats_prints_counts(capsys):
    assert main(["stats"]) == 0
    captured = capsys.readouterr()
    assert "   article: 113" in captured.out
    assert "  footnote: 58" in captured.out
    assert not captured.err


def test_cli_search_prints_matches(capsys):
    assert main(["search", "subliminal techniques"]) == 0
    captured = capsys.readouterr()
    assert "art_5.par_1.pt_a" in captured.out
    assert "Article 5(1), point (a)" in captured.out
    assert "match(es)." in captured.err


def test_cli_search_filters_by_type(capsys):
    assert main(["search", "human oversight", "--subtree", "--type", "article"]) == 0
    captured = capsys.readouterr()
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert lines
    assert all(line.startswith("art_") and ".par_" not in line for line in lines)
    assert "art_14                 Article 14" in lines
    assert "match(es)." in captured.err


def test_cli_search_accepts_multiple_type_filters(capsys):
    assert main(["search", "subliminal techniques", "--type", "paragraph", "--type", "point"]) == 0
    captured = capsys.readouterr()
    assert "art_5.par_1.pt_a" in captured.out
    assert "Article 5(1), point (a)" in captured.out


def test_cli_export_writes_json(tmp_path, capsys):
    out = tmp_path / "aiact.json"

    assert main(["export", str(out)]) == 0

    captured = capsys.readouterr()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["regulation"] == "Regulation (EU) 2024/1689"
    assert data["document"]["id"] == "aiact"
    assert f"wrote {out}" in captured.err


def test_cli_graph_writes_reference_edges(tmp_path, capsys):
    out = tmp_path / "edges.json"

    assert main(["graph", str(out)]) == 0

    captured = capsys.readouterr()
    edges = json.loads(out.read_text(encoding="utf-8"))
    assert len(edges) > 300
    assert {"source", "target", "kind", "raw"} <= set(edges[0])
    assert "wrote" in captured.err
    assert str(out) in captured.err
