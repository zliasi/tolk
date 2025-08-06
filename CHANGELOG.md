# changelog

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
