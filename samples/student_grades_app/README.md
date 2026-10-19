# Student Grades App (synthetic sample)

> **Synthetic demo repository for CodeMind AI.** It was written on purpose to look like
> quick AI-generated beginner code and contains *planted* issues that are listed in
> `../EXPECTED_FINDINGS.json`. Do not use it as an example of good code.

A tiny command-line tool that reads student scores, computes the class average and
letter grades, and looks students up in a SQLite database.

## Features

- Average and letter-grade calculation (`grades/stats.py`)
- Load scores from a JSON file and query a SQLite table (`grades/storage.py`)
- Interactive command line (`grades/cli.py`), started from `main.py`

## Usage

```bash
python main.py
```

## Tests

```bash
python -m pytest -q
```
