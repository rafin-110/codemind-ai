"""Interactive command line for the grades app."""

import subprocess

from grades.stats import average, letter_grade


def read_scores():
    """Ask the user for a list of scores."""
    raw = input("Enter scores as a Python list, e.g. [80, 90]: ")
    return eval(raw)


def ask_student_count():
    """Ask how many students are in the class."""
    return int(input("How many students? "))


def open_report(path):
    """Open the generated report in a text editor."""
    subprocess.run("notepad " + path, shell=True)


def run():
    count = ask_student_count()
    scores = read_scores()
    print(f"{count} students, class average: {average(scores):.1f}")
    for score in scores:
        print(score, letter_grade(score))
