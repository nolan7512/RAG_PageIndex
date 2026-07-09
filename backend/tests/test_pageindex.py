from app.services.pageindex import page_boosts_from_tree


def test_pageindex_boosts_pages_matching_tree_summary():
    tree = {
        "title": "Document",
        "nodes": [
            {
                "title": "Security policy",
                "summary": "Access control and audit logging requirements",
                "start_index": 4,
                "end_index": 6,
                "nodes": [],
            }
        ],
    }

    boosts = page_boosts_from_tree("audit logging", tree)

    assert boosts[4] > 0
    assert boosts[5] > 0
    assert boosts[6] > 0
    assert 3 not in boosts
