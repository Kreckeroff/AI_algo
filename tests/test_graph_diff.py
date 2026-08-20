from ai_algo.domain.compare import graph_change_notes


def test_graph_period_change_noted():
    before = [{"id": "n1", "type": "indicator", "data": {"period": 14}}]
    after = [{"id": "n1", "type": "indicator", "data": {"period": 21}}]
    notes = graph_change_notes(before, after)
    assert any("period" in n for n in notes)


def test_graph_block_added():
    before = [{"id": "n1", "type": "indicator"}]
    after = [{"id": "n1", "type": "indicator"}, {"id": "n2", "type": "condition"}]
    notes = graph_change_notes(before, after)
    assert any("добавлен" in n for n in notes)
