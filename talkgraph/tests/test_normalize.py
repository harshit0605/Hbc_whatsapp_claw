from talkgraph.graph.store import normalize_name


def test_normalize_collapses_and_lowercases():
    assert normalize_name("  Alice   Smith ") == "alice smith"
    assert normalize_name("BOB") == "bob"
    assert normalize_name("Alice") == normalize_name("alice")
