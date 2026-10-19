"""Statistics helpers for student scores."""


def average(scores):
    """Return the mean of a list of scores."""
    total = sum(scores)
    return total / len(scores)


def letter_grade(score):
    """Convert a numeric score to a letter grade."""
    if score == None:
        return "N/A"
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    return "F"


def add_score(score, history=[]):
    """Append a score to the history and return it."""
    history.append(score)
    return history


def percentage(part, whole):
    """Return part as a percentage of whole."""
    if whole == 0:
        return 0.0
    return part / whole * 100
