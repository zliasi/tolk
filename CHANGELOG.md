# changelog

## 0.4.0 - 2025-10-24

The C engine, behind the same interface.

- csrc holds a small format agnostic engine: literal search forward and
  backward, count, all occurrences, nth with negative indexing, line
  boundaries, line advance, and line numbering
- forward search is memchr on the first byte then memcmp to confirm, so most
  of a buffer is rejected at memory bandwidth
- built with cffi via make engine. When it is not built the pure-Python
  backend keeps running at the same interface and nothing above the boundary
  changes. _engine.BACKEND says which is live
- parity tests run the same inputs through both backends, including every
  fixture, and skip the C half when it is not built
- bulk numeric column parsing: a whole block is split and converted in C and
  only finished numbers cross back, instead of one float() per cell. Used
  only when every requested column is numeric and nothing is being stripped,
  since a string column cannot travel as a double
- benchmarks for both the search primitives and the table path

Measured rather than assumed, and the results are mixed on purpose. Literal
search gains nothing, because bytes.find is already C and the cffi call costs
more than it saves. The wins are line numbering, 21x, and bulk table parsing,
1.7x. The planned Teddy style multi-literal scan was dropped: the benchmark
says separate prefiltered passes are already fast enough that it would not
pay for itself.

Two bugs the parity tests caught:

- the C backward iterator reversed a forward scan, which differs from a true
  backward walk for a needle that overlaps itself, and would also have made
  find_nth(-1) cost the length of the file rather than the distance from the
  end
- collecting all offsets counted the file first and then filled an exact
  array, reading it twice and coming out slower than the Python loop it
  replaced

## 0.3.0 - 2025-09-26

Status checking, the record model, and the CLI.

- check reads only the tail of a file and reports ok, error, running, or
  unknown. Error markers win over success markers, because a run can print
  something that looks like success and then die. No terminator plus a recent
  mtime reads as running
- record model: everything read becomes a Table and everything written comes
  from one, so conversion stays one reader plus one writer per format rather
  than a converter per pair
- a table carries units and keeps what it did not understand, including the
  reasons quantities went missing
- one list valued quantity expands to one row per element with the scalars
  repeated alongside. Two of them stay separate tables, since zipping would
  invent a relationship that is not in the file
- csv, tsv, and json output
- cli: get, check, scan, cat, sniff, and spec list/show/explain
- tolk get takes many files and emits one table. A quantity a format does not
  define is a miss for that file with exit status 1, not a fatal error, so a
  sweep over mixed programs completes
- the check module is private as _check, matching engine, sniff, and explain.
  Public names come from the package root, the modules behind them do not
  shadow those names

## 0.2.0 - 2025-09-05

Specs and extraction. Still no CLI and no C engine.

- specs are TOML and validated strictly at load time, so a typo names the
  file and the key instead of silently extracting nothing
- spec search path: shipped specs first, then ~/.config/tolk/specs, then
  TOLK_SPECS. A user spec replaces a shipped one of the same name, and
  Spec.source says which file won
- quantities address data by anchor, occurrence, block, and parse rule.
  occurrence is first, last, all, or an index, negative counting from the end
- occurrence = "all" reads quantities a program prints once per item rather
  than as a table, one line per excited state
- blocks skip a header and stop on a blank line, on a literal that begins a
  line, or after a line count
- parse rules: field, columns, per column types so a label can sit beside its
  numbers, strip for punctuation glued onto values, whole_line for text with
  spaces in it
- a quantity with no anchor is read from the start of the file, which is how
  positional formats work
- values carry provenance, the path and byte offset always, the line number
  only when asked since counting newlines is the one operation that has to
  read everything before the offset
- a missing quantity is a value of None with a reason, never an exception, so
  a sweep over many files survives the broken ones
- explain traces an extraction: anchor, byte, line, the matched text, the
  block it walked, and the value that came out
- describe lists what a spec can read
- package API: get, sniff, formats, spec, describe, explain
- shipped specs: orca, gaussian, xyz
- specs with a content banner no longer claim a file extension, since ORCA
  and Gaussian both write .out and only the banner separates them
- goldens under tests/expected pin the explain output for every fixture

## 0.1.0 - 2025-08-06

First cut of the byte layer. No specs, no CLI yet.

- Source opens a file lazily, mapping anything over 64 KB and reading
  smaller files outright, since a mapping costs more than the copy it saves
  below that. Slices are borrowed memoryviews, read() copies.
- literal search: find, rfind, forward and backward iteration, count, and
  nth with negative indexing so the last occurrence is a first class case
- line handling with no index structure. Boundaries are located as they are
  needed, so a lookup near the end of a large file touches two pages.
  Carriage returns are not content, and a trailing newline does not invent
  an empty final line.
- line_number is the one operation that reads everything before the offset,
  so it stays opt in for provenance and error messages
- block extraction: skip lines from an anchor, stop on the first blank line,
  on a literal that begins a line, or after a line count
- tail and head reads, by default snapped to whole lines
- format sniffing from the first 4 KB, content before extension, with
  signatures registered as data
- builtin signatures for xyz, csv, tsv, and text
