import json

from grades.storage import add_student, create_db, find_student, load_scores


def test_load_scores_valid_file(tmp_path):
    path = tmp_path / "scores.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert load_scores(path) == [1, 2, 3]


def test_load_scores_missing_file_returns_empty(tmp_path):
    assert load_scores(tmp_path / "missing.json") == []


def test_find_student():
    conn = create_db()
    add_student(conn, "Asha", 88.0)
    add_student(conn, "Ben", 71.5)
    assert find_student(conn, "Asha") == [("Asha", 88.0)]
    assert find_student(conn, "Nobody") == []
