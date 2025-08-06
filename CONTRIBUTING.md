# contributing

Contributions are welcome: new specs, new conversion backends, better error
messages, docs, or engine work. Teaching tolk a new file format needs no
Python at all.

## Adding or improving a spec

This is the most useful contribution and works without touching code.

1. Copy an existing spec from `src/tolk/specs/` to `<name>.toml` in your own
   spec directory (`~/.config/tolk/specs/`, which overrides shipped specs of
   the same name).
2. Give each quantity an anchor, the literal string the file prints next to
   the value, and say how to read what follows.
3. Check it against a real file:

   ```
   tolk explain job.out energy
   ```

   That prints the byte offset and line the anchor matched, the text it
   matched, and the value parsed out of it. If any of those look wrong, the
   spec is wrong, not the engine.
4. When it works, copy the file into `src/tolk/specs/` in this repo, add a
   fixture and a golden case, and open a pull request.

## Adding a conversion backend

Backends are TOML too. Declare how to detect the tool, which format pairs it
handles, and the command to run. tolk ships only the Open Babel backend, so
anything else belongs either in your own `~/.config/tolk/backends/` or in a
pull request if it is widely useful.

## Changing the engine

Ground rules, in order of importance:

- No format knowledge in code. If a change only matters for one file format,
  it belongs in a spec, not in the engine. This rule is the whole reason the
  project exists.
- The backend boundary is `_engine.py`. Every function there takes a haystack
  and byte offsets and returns byte offsets, never parsed values. The C
  engine implements the same signatures, so anything added on one side has to
  work on the other.
- Never read what nobody asked for. Laziness is the product. A change that
  makes tolk touch pages it did not need is a regression even when it is
  faster on a benchmark.
- No global mutable state in the engine. Batch work runs threaded.
- The record model never discards data it did not understand. Unrecognised
  fields pass through verbatim.
- Fail with a reason, not an exception. A missing quantity yields None and
  says why, because scanning five hundred files where twelve crashed must not
  abort on the first one.

Workflow:

1. Clone, branch, edit.
2. Run the tests:

   ```
   make test
   ```

3. Run the linters and type checker (needs black, ruff, mypy, e.g. via
   `uvx`):

   ```
   make check
   ```

4. Add or update a test. New engine behaviour gets a case in
   `tests/test_engine.py`, new spec behaviour gets a fixture and a golden.
5. Update README.md and CHANGELOG.md if behaviour changed.
6. Open a pull request.

Code style follows the repository conventions: Black formatting, strict
typing, comments explain why rather than what, no emojis, no decorative
lines.

## Commits

One change per commit. Message is a single short lowercase imperative
sentence, no prefix, no trailing period:

```
add block extraction from an anchor
fix phantom final line when the file ends with a newline
```

## Releases

Bump `__version__` in `src/tolk/_version.py` and describe the change in
CHANGELOG.md.
