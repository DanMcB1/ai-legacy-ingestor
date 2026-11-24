"""Command-line entry point: generate, ingest, search, report.

Examples::

    python -m ingestor generate
    python -m ingestor ingest
    python -m ingestor search "warranty claim for Anita Rosales"
    python -m ingestor report
"""

from __future__ import annotations

import argparse
import json
import sys

from .pipeline import ingest_paths, ingest_samples, load_store
from .samples import generate_all


def _cmd_generate(_args: argparse.Namespace) -> int:
    written = generate_all()
    print(f"Wrote {len(written)} sample files:")
    for name, path in written.items():
        print(f"  {name}: {path}")
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    if args.paths:
        result = ingest_paths(args.paths, copybook_path=args.copybook, persist=True)
    else:
        result = ingest_samples(persist=True)
    report = result.report
    print(
        f"Processed {report.files_processed} file(s): "
        f"{report.records_parsed} parsed, "
        f"{report.records_rejected} rejected, "
        f"{report.records_for_review} flagged for review, "
        f"{report.chunks_indexed} chunks indexed."
    )
    if report.by_source_type:
        parts = ", ".join(f"{k}={v}" for k, v in sorted(report.by_source_type.items()))
        print(f"By type: {parts}")
    for note in report.notes:
        print(f"Note: {note}")
    for item in report.rejects:
        print(f"Reject: {item['source_file']} record {item['record_number']}: {item['reason']}")
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    store = load_store()
    if not store.chunks:
        print("No index yet. Run `python -m ingestor ingest` first.", file=sys.stderr)
        return 1
    hits = store.search(args.query, k=args.k)
    if not hits:
        print("No matches.")
        return 0
    for i, hit in enumerate(hits, start=1):
        print(f"[{i}] score {hit.score:.3f}  {hit.chunk.citation()}")
        snippet = " ".join(hit.chunk.text.split())
        if len(snippet) > 280:
            snippet = snippet[:277] + "..."
        print(f"    {snippet}")
        print()
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    store = load_store()
    if store.report is None:
        print("No quality report in the index. Run `python -m ingestor ingest` first.", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(store.report.to_dict(), indent=2))
        return 0
    report = store.report
    print(f"Files processed:     {report.files_processed}")
    print(f"Records parsed:      {report.records_parsed}")
    print(f"Records rejected:    {report.records_rejected}")
    print(f"Flagged for review:  {report.records_for_review}")
    print(f"Chunks indexed:      {report.chunks_indexed}")
    if report.by_source_type:
        print("By type:             " + ", ".join(f"{k}={v}" for k, v in sorted(report.by_source_type.items())))
    if report.rejects:
        print("Rejects:")
        for item in report.rejects:
            print(f"  - {item['source_file']} record {item['record_number']}: {item['reason']}")
    if report.review_items:
        print("Review:")
        for item in report.review_items:
            conf = item.get("ocr_confidence")
            conf_s = f", OCR {conf:.0f}%" if isinstance(conf, (int, float)) and conf is not None else ""
            print(f"  - {item['source_file']} record {item['record_number']}{conf_s}: {', '.join(item.get('flags') or [])}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ingestor",
        description="Unstructured Legacy Ingestor — generate samples, ingest, and search.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Write the bundled sample files under data/samples/")
    gen.set_defaults(func=_cmd_generate)

    ing = sub.add_parser("ingest", help="Ingest sample files (or paths you pass) into the local index")
    ing.add_argument("paths", nargs="*", help="Optional files to ingest instead of the bundled samples")
    ing.add_argument("--copybook", help="Path to a .cpy copybook for a mainframe .DAT file")
    ing.set_defaults(func=_cmd_ingest)

    sch = sub.add_parser("search", help="Search the local index and print citations")
    sch.add_argument("query")
    sch.add_argument("-k", type=int, default=5, help="Maximum number of hits (default 5)")
    sch.set_defaults(func=_cmd_search)

    rep = sub.add_parser("report", help="Print the last data-quality report")
    rep.add_argument("--json", action="store_true", help="Print the report as JSON")
    rep.set_defaults(func=_cmd_report)

    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
