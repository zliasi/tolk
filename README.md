# tolk

Fast parser and IO framework.

A C engine locates bytes, Python decides what they mean. Files are opened
lazily and only the regions you ask for are ever read or parsed, so pulling
three numbers out of a gigabyte log costs kilobytes of work. Format knowledge
lives in declarative TOML specs rather than code, so teaching tolk a new file
type means writing a spec, not patching the engine.

Requires Python 3.11 or newer. The C engine is optional, a pure-Python
backend with the same interface takes over when it is not built.

## Installation

```
git clone https://github.com/zliasi/tolk
pip install ./tolk
```

## Status

Early. The byte layer works, specs and the CLI do not exist yet. See
CHANGELOG.md.

## Layer zero

The lowest layer needs no spec and no configuration. It finds bytes and hands
back offsets.

```python
import tolk

with tolk.open("job.out") as src:
    hit = src.rfind(b"FINAL ENERGY")        # last occurrence
    print(src.line(hit))                    # the line it sits on
    print(src.line_number(hit))             # for provenance
```

Anchors, occurrences, and counts:

```python
src.find(b"CYCLE")                  # first, or -1
src.rfind(b"CYCLE")                 # last, or -1
src.findall(b"CYCLE")               # every offset, non-overlapping
src.find_nth(b"CYCLE", -2)          # second from the end
src.count(b"CYCLE")                 # how many
```

Lines are located as they are needed, never indexed up front:

```python
src.line_span(offset)               # (start, end) of the line, no terminator
src.lines(start, end)               # spans overlapping a region
src.advance_lines(offset, 3)        # three lines further on, clamped at EOF
```

Blocks address tabular output. An anchor names the header, `skip` steps over
it, and `until` says what ends the run:

```python
src.block_lines(hit, skip=4, until=tolk.BLANK)   # to the first blank line
src.block_lines(hit, skip=2, until=b"---")       # to a separator
src.block_lines(hit, skip=2, max_lines=10)       # a fixed count
```

Status checks read the end only, which is why checking hundreds of files is
cheap:

```python
src.tail(8192)                      # snapped to a line boundary
src.head(4096, whole_lines=True)
```

Detection is content first, extension second:

```python
tolk.sniff("mol.xyz")               # -> "xyz"
```

Register your own signature, highest priority wins:

```python
tolk.Signature("orca", contains=(b"* O   R   C   A *",), priority=50)
```

## Development

```
make test
make check
```

See CONTRIBUTING.md.

## License

MIT, see LICENSE.
