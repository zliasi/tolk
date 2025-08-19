.PHONY: test goldens check

test:
	python3 -m unittest discover -s tests

goldens:
	python3 tests/update-goldens.py

PY_FILES = src/tolk tests

check:
	black --check $(PY_FILES)
	ruff check --select E4,E7,E9,F $(PY_FILES)
	mypy --strict src/tolk
