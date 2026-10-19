import pytest

from grades.stats import add_score, average, letter_grade, percentage


def test_average_normal():
    assert average([80, 90, 100]) == 90


def test_average_single_value():
    assert average([42]) == 42


def test_average_empty_raises():
    # Required behaviour: an empty class has no average; callers must be told.
    with pytest.raises(ValueError):
        average([])


def test_letter_grade_boundaries():
    assert letter_grade(90) == "A"
    assert letter_grade(75) == "B"
    assert letter_grade(60) == "C"
    assert letter_grade(59.9) == "F"
    assert letter_grade(None) == "N/A"


def test_add_score_returns_history():
    assert add_score(70, []) == [70]


def test_percentage_zero_whole():
    assert percentage(5, 0) == 0.0
    assert percentage(1, 4) == 25.0
