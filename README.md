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

Early. Specs and extraction work, the CLI and the C engine do not exist yet.
See CHANGELOG.md.

## Reading a file

```python
import tolk

tolk.get("job.out", "energy")                    # one Value
tolk.get("job.out", ["energy", "geometry"])      # dict keyed by name
tolk.sniff("job.out")                            # -> "orca"
tolk.formats()                                   # what specs exist
```

Values carry their origin, so a number can always be traced back to the line
that produced it:

```python
value = tolk.get("job.out", "energy", with_lines=True)
value.value        # -270.965189516826
value.unit         # "hartree"
value.where        # job.out:13383
```

Nothing raises when a quantity is absent. A miss is a value of None with a
reason, so a sweep over hundreds of files survives the broken ones:

```python
value = tolk.get("job.out", "excitations")
if not value:
    print(value.reason)     # anchor '...' not found
```

## Specs

A spec says where a quantity lives and how to read it. Shipped specs live in
`src/tolk/specs/`, and anything in `~/.config/tolk/specs/` overrides them by
name.

```toml
format = "orca"

[signature]
contains = ["* O   R   C   A *"]
priority = 50

[quantity.energy]
anchor = "FINAL SINGLE POINT ENERGY"
occurrence = "last"
parse = { field = -1, type = "float", unit = "hartree" }

[quantity.geometry]
anchor = "CARTESIAN COORDINATES (ANGSTROEM)"
occurrence = "last"
block = { skip = 2, until = "blank" }
parse.columns = { symbol = 0, x = 1, y = 2, z = 3 }
parse.types = { symbol = "str" }
```

`occurrence` is `first`, `last`, `all`, or an index. Negative indices count
from the end. `all` is for quantities a program prints once per item rather
than as a table, one line per excited state.

`block` walks from the anchor to the data. `skip` steps over the header,
`until` ends the run at `blank` or at a literal that begins a line.

`parse` turns text into values. `field` takes one whitespace separated field,
negative counting from the right. `columns` names several. `types` overrides
the type per column, so a label can sit beside its numbers. `strip` removes
punctuation programs glue on, the comma after a revision or the `f=` in front
of an oscillator strength. `whole_line` keeps text with spaces in it.

A quantity with no `anchor` is read from the start of the file, which is how
positional formats like xyz work.

Detection is content first, extension second. Specs with a banner should not
claim an extension, since ORCA and Gaussian both write `.out` and only the
banner separates them.

Shipped: `orca`, `gaussian`, `xyz`.

## Debugging a spec

`explain` shows what the spec actually did, which is the difference between a
declarative system and a guessing game:

```
$ python -c "import tolk; print(tolk.explain('job.out', 'geometry'))"
quantity geometry (orca, /.../specs/chem/orca.toml)
anchor   'CARTESIAN COORDINATES (ANGSTROEM)' occurrence last
found    byte 4033, line 66
line     CARTESIAN COORDINATES (ANGSTROEM)
block    15 lines
         C      0.035760   -1.136467    0.299262
         C     -0.011666    1.094815    0.358093
         ... 13 more
rule     columns symbol=0, x=1, y=2, z=3
value    15 rows of symbol, x, y, z
```

## Layer zero

The lowest layer needs no spec. It finds bytes and hands back offsets.

```python
with tolk.open("job.out") as src:
    hit = src.rfind(b"FINAL ENERGY")   # last occurrence, or -1
    src.line(hit)                      # the line it sits on
    src.line_number(hit)               # counts newlines, so opt in

    src.findall(b"CYCLE")              # every offset
    src.find_nth(b"CYCLE", -2)         # second from the end
    src.count(b"CYCLE")

    src.line_span(hit)                 # (start, end), no terminator
    src.lines(start, end)              # spans overlapping a region
    src.advance_lines(hit, 3)          # clamped at both ends

    src.block_lines(hit, skip=4, until=tolk.BLANK)
    src.tail(8192)                     # snapped to a line boundary
    src.head(4096, whole_lines=True)
```

## Development

```
make test
make goldens
make check
```

The goldens under `tests/expected/` pin the explain output for every fixture.
They are the specification for what a spec is supposed to match, so
regenerating them is a reviewed diff.

See CONTRIBUTING.md.

## License

MIT, see LICENSE.
