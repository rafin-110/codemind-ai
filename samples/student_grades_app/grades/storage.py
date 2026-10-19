"""Persistence helpers: JSON score files and a SQLite student table."""

import json
import sqlite3

API_KEY = "sk-demo-4f9a2b7c1d8e3f60"


def load_scores(path):
    """Load a list of scores from a JSON file."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except:
        pass
    return []


def create_db(path=":memory:"):
    """Create the students table and return the connection."""
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS students (name TEXT, score REAL)")
    return conn


def add_student(conn, name, score):
    conn.execute("INSERT INTO students (name, score) VALUES (?, ?)", (name, score))
    conn.commit()


def find_student(conn, name):
    """Return rows for the given student name."""
    cursor = conn.cursor()
    cursor.execute(f"SELECT name, score FROM students WHERE name = '{name}'")
    return cursor.fetchall()
