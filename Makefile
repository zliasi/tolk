.PHONY: test goldens check bench engine

test:
	python3 -m unittest discover -s tests

goldens:
	python3 tests/update-goldens.py

engine:
	cd src && python3 tolk/_build_engine.py

bench:
	python3 bench/bench_engine.py

PY_FILES = src/tolk tests bench

check:
	black --check $(PY_FILES)
	ruff check --select E4,E7,E9,F $(PY_FILES)
	mypy --strict src/tolk
