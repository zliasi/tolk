"""Command line interface.

The verbs are few on purpose. Everything that produces rows can emit csv,
tsv, or json, so shaping and joining belong to jq or mlr rather than to more
flags here.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from . import _check, _explain, _sniff, backends, batch, cache, convert, registry
from . import template
from ._version import __version__
from .record import Table
from .source import Source
from .spec import Spec, SpecError

FORMATS = ("csv", "tsv", "json")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    try:
        return int(args.run(args))
    except SpecError as exc:
        print(f"tolk: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"tolk: {exc}", file=sys.stderr)
        return 2
    except BrokenPipeError:
        return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tolk", description="fast parser and io")
    parser.add_argument("--version", action="version", version=__version__)
    subs = parser.add_subparsers(dest="command")

    get = subs.add_parser("get", help="extract quantities from files")
    get.add_argument("quantities", help="comma separated quantity names")
    get.add_argument("files", nargs="+")
    get.add_argument("-f", "--format", help="force a format instead of sniffing")
    get.add_argument("-t", "--to", choices=FORMATS, default="csv", help="output format")
    get.add_argument("-o", "--output", help="write here instead of stdout")
    get.add_argument(
        "--lines", action="store_true", help="include line numbers in provenance"
    )
    get.add_argument("-j", "--jobs", type=int, help="threads for many files")
    get.add_argument("--cache", action="store_true", help="remember anchor offsets")
    get.set_defaults(run=_run_get)

    check = subs.add_parser("check", help="report how runs ended")
    check.add_argument("files", nargs="+")
    check.add_argument("-f", "--format")
    check.add_argument("--failed", action="store_true", help="list only what is not ok")
    check.add_argument("-t", "--to", choices=FORMATS, help="machine readable output")
    check.add_argument("-j", "--jobs", type=int, help="threads for many files")
    check.set_defaults(run=_run_check)

    scan = subs.add_parser("scan", help="locate a literal and print offsets")
    scan.add_argument("file")
    scan.add_argument("pattern")
    scan.add_argument("--last", action="store_true", help="last occurrence only")
    scan.add_argument("--count", action="store_true", help="how many, and nothing else")
    scan.add_argument("--text", action="store_true", help="print the matching line")
    scan.set_defaults(run=_run_scan)

    cat = subs.add_parser("cat", help="print part of a file without reading it all")
    cat.add_argument("file")
    cat.add_argument("--head", type=int, metavar="BYTES")
    cat.add_argument("--tail", type=int, metavar="BYTES")
    cat.add_argument("--lines", metavar="A:B", help="line range, 1 based, inclusive")
    cat.set_defaults(run=_run_cat)

    conv = subs.add_parser("convert", help="convert a file to another format")
    conv.add_argument("source")
    conv.add_argument("target")
    conv.add_argument("-f", "--format", help="force the input format")
    conv.add_argument("-q", "--quantities", help="comma separated, default all")
    conv.add_argument("--explain", action="store_true", help="say how, and do nothing")
    conv.set_defaults(run=_run_convert)

    write = subs.add_parser("write", help="render an input template")
    write.add_argument("template", nargs="?")
    write.add_argument("output", nargs="?", help="default stdout")
    write.add_argument(
        "--set", dest="settings", action="append", default=[], metavar="K=V"
    )
    write.add_argument("--list", action="store_true", help="list templates")
    write.set_defaults(run=_run_write)

    backend = subs.add_parser("backends", help="list conversion backends")
    backend.set_defaults(run=_run_backends)

    sniff = subs.add_parser("sniff", help="name the format of files")
    sniff.add_argument("files", nargs="+")
    sniff.set_defaults(run=_run_sniff)

    spec = subs.add_parser("spec", help="inspect specs")
    spec_subs = spec.add_subparsers(dest="spec_command", required=True)
    spec_list = spec_subs.add_parser("list", help="known formats and their files")
    spec_list.set_defaults(run=_run_spec_list)
    spec_show = spec_subs.add_parser("show", help="quantities a format can read")
    spec_show.add_argument("format")
    spec_show.set_defaults(run=_run_spec_show)
    spec_explain = spec_subs.add_parser("explain", help="trace one extraction")
    spec_explain.add_argument("file")
    spec_explain.add_argument("quantity")
    spec_explain.add_argument("-f", "--format")
    spec_explain.set_defaults(run=_run_spec_explain)

    return parser


def _emit(table: Table, how: str, output: str | None) -> None:
    if how == "json":
        text = table.to_json()
        if not text.endswith("\n"):
            text += "\n"
    elif how == "tsv":
        text = table.to_tsv()
    else:
        text = table.to_csv()
    if output:
        with open(output, "w", encoding="utf-8") as handle:
            handle.write(text)
    else:
        sys.stdout.write(text)


def _run_get(args: argparse.Namespace) -> int:
    names = [name.strip() for name in args.quantities.split(",") if name.strip()]
    if not names:
        print("tolk: no quantities given", file=sys.stderr)
        return 2

    if args.cache:
        cache.enable()

    try:
        sweep = batch.get_many(
            list(args.files),
            names,
            format=args.format,
            with_lines=args.lines,
            workers=args.jobs,
        )
    finally:
        if args.cache:
            cache.disable()

    _emit(sweep.table, args.to, args.output)
    for where, reason in sorted(sweep.errors.items()):
        print(f"tolk: {where}: {reason}", file=sys.stderr)
    return 1 if sweep.errors else 0


def _run_check(args: argparse.Namespace) -> int:
    statuses = batch.check_many(list(args.files), format=args.format, workers=args.jobs)
    if args.failed:
        statuses = [status for status in statuses if not status.ok]

    if args.to:
        table = Table(
            rows=[
                {
                    "path": status.path,
                    "state": status.state,
                    "format": status.format,
                    "detail": status.detail,
                }
                for status in statuses
            ]
        )
        _emit(table, args.to, None)
    else:
        for status in statuses:
            print(status)

    return 1 if any(status.state != _check.OK for status in statuses) else 0


def _run_scan(args: argparse.Namespace) -> int:
    needle = args.pattern.encode()
    with Source(args.file) as src:
        if args.count:
            print(src.count(needle))
            return 0
        offsets = [src.rfind(needle)] if args.last else src.findall(needle)
        offsets = [off for off in offsets if off >= 0]
        if not offsets:
            return 1
        for offset in offsets:
            if args.text:
                line = src.line(offset).decode("utf-8", errors="replace")
                print(f"{offset}\t{src.line_number(offset)}\t{line}")
            else:
                print(offset)
    return 0


def _run_cat(args: argparse.Namespace) -> int:
    with Source(args.file) as src:
        if args.lines:
            first, _, last = args.lines.partition(":")
            start = int(first or 1)
            stop = int(last) if last else start
            printed = 0
            for number, (line_from, line_to) in enumerate(src.lines(), start=1):
                if number < start:
                    continue
                if number > stop:
                    break
                sys.stdout.write(
                    src.read(line_from, line_to).decode("utf-8", errors="replace")
                    + "\n"
                )
                printed += 1
            return 0 if printed else 1
        if args.tail:
            data = src.tail(args.tail)
        elif args.head:
            data = src.head(args.head, whole_lines=True)
        else:
            data = src.read()
        sys.stdout.write(data.decode("utf-8", errors="replace"))
    return 0


def _run_convert(args: argparse.Namespace) -> int:
    names = (
        [n.strip() for n in args.quantities.split(",") if n.strip()]
        if args.quantities
        else None
    )
    try:
        if args.explain:
            print(convert.plan(args.source, args.target, format=args.format))
            return 0
        done = convert.convert(
            args.source, args.target, format=args.format, quantities=names
        )
    except (convert.ConvertError, backends.BackendError) as exc:
        print(f"tolk: {exc}", file=sys.stderr)
        return 2
    print(f"{done.source} -> {done.target} via {done.how}", file=sys.stderr)
    return 0


def _run_write(args: argparse.Namespace) -> int:
    if args.list:
        for name in template.names():
            print(name)
        return 0
    if not args.template:
        print("tolk: give a template name, or --list", file=sys.stderr)
        return 2
    try:
        rendered = template.get(args.template).render(
            template.parse_settings(args.settings)
        )
    except template.TemplateError as exc:
        print(f"tolk: {exc}", file=sys.stderr)
        return 2
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(rendered)
    else:
        sys.stdout.write(rendered)
    return 0


def _run_backends(args: argparse.Namespace) -> int:
    found = backends.load_all()
    if not found:
        print("tolk: no backends found", file=sys.stderr)
        return 1
    width = max(len(name) for name in found)
    for name in sorted(found):
        entry = found[name]
        state = "installed" if entry.available() else "missing"
        print(f"{name:{width}}  {state:9s}  {entry.source}")
    print(f"native writers: {', '.join(convert.writers())}")
    return 0


def _run_sniff(args: argparse.Namespace) -> int:
    registry.load_all()
    status = 0
    for path in args.files:
        with Source(path) as src:
            detected = _sniff.sniff_source(src)
        print(f"{detected or 'unknown'}\t{path}")
        if detected is None:
            status = 1
    return status


def _run_spec_list(args: argparse.Namespace) -> int:
    specs = registry.load_all()
    if not specs:
        print("tolk: no specs found", file=sys.stderr)
        return 1
    width = max(len(name) for name in specs)
    for name in sorted(specs):
        print(f"{name:{width}}  {specs[name].source}")
    return 0


def _run_spec_show(args: argparse.Namespace) -> int:
    spec = registry.get(args.format)
    print(f"{spec.format} ({spec.source})")
    width = max((len(name) for name in spec.names()), default=0)
    for name in spec.names():
        quantity = spec.quantities[name]
        unit = f" [{quantity.parse.unit}]" if quantity.parse.unit else ""
        note = quantity.description or "no description"
        print(f"  {name:{width}}  {note}{unit}")
    return 0


def _run_spec_explain(args: argparse.Namespace) -> int:
    with Source(args.file) as src:
        spec = _resolve(src, args.format)
        print(_explain.explain_text(src, spec, args.quantity))
    return 0


def _resolve(src: Source, format: str | None) -> Spec:
    if format is not None:
        return registry.get(format)
    registry.load_all()
    detected = _sniff.sniff_source(src)
    if detected is None:
        raise SpecError(
            f"{src.path}: could not detect a format, pass -f. "
            f"known: {', '.join(registry.formats()) or 'none'}"
        )
    return registry.get(detected)


if __name__ == "__main__":
    raise SystemExit(main())
