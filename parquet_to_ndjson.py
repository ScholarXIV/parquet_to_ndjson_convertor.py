#!/usr/bin/env python3
"""
Convert a local arXiv metadata Parquet shard into normalized NDJSON.

Example:
  python parquet_to_ndjson.py example/sample.parquet

Output:
  example/sample.ndjson
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

try:
    import pyarrow.parquet as pq
except ImportError as error:
    raise SystemExit("pyarrow is required. Install it with: pip install pyarrow") from error


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\n", " ").split()).strip()


def parse_categories(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [clean_text(item) for item in value if clean_text(item)]
    return [item for item in clean_text(value).split(" ") if item]


def format_author(author_parts: Any) -> str:
    if not isinstance(author_parts, list):
        return clean_text(author_parts)

    padded = [*author_parts, "", "", ""]
    last_name = clean_text(padded[0])
    first_name = clean_text(padded[1])
    suffix = clean_text(padded[2])

    return clean_text(" ".join(part for part in [first_name, last_name, suffix] if part))


def parse_authors(row: dict[str, Any]) -> list[str]:
    parsed = row.get("authors_parsed")
    if isinstance(parsed, list):
        authors = [format_author(author) for author in parsed]
        authors = [author for author in authors if author]
        if authors:
            return authors

    raw_authors = clean_text(row.get("authors"))
    return [raw_authors] if raw_authors else []


def get_version_date(versions: Any, index: int) -> str:
    if not isinstance(versions, list) or not versions:
        return ""

    try:
        version = versions[index]
    except IndexError:
        return ""

    if not isinstance(version, dict):
        return ""

    return to_iso_utc(version.get("created"))


def get_version_label(versions: Any, index: int = -1) -> str:
    if not isinstance(versions, list) or not versions:
        return ""

    try:
        version = versions[index]
    except IndexError:
        return ""

    if not isinstance(version, dict):
        return ""

    return clean_text(version.get("version"))


def append_version(arxiv_id: str, versions: Any) -> str:
    version = get_version_label(versions)
    if not version:
        return arxiv_id

    if re.search(r"v\d+$", arxiv_id):
        return arxiv_id

    return f"{arxiv_id}{version}"


def get_arxiv_id_path(paper_id: str) -> str:
    return re.sub(
        r"^https?://(?:export\.)?arxiv\.org/abs/",
        "",
        paper_id,
    )


def arxiv_abs_url(arxiv_id: str) -> str:
    return f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""


def arxiv_pdf_url(arxiv_id: str) -> str:
    return f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else ""


def datetime_to_iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)

    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def to_iso_utc(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, datetime):
        return datetime_to_iso_utc(value)

    if isinstance(value, date):
        return datetime_to_iso_utc(datetime(value.year, value.month, value.day, tzinfo=timezone.utc))

    text = clean_text(value)
    if not text:
        return ""

    try:
        return datetime_to_iso_utc(parsedate_to_datetime(text))
    except (TypeError, ValueError):
        pass

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return datetime_to_iso_utc(parsed)
    except ValueError:
        pass

    try:
        parsed_date = date.fromisoformat(text)
        return datetime_to_iso_utc(
            datetime(parsed_date.year, parsed_date.month, parsed_date.day, tzinfo=timezone.utc)
        )
    except ValueError:
        return text


def normalize_versions(versions: Any) -> list[dict[str, Any]]:
    if not isinstance(versions, list):
        return []

    normalized = []
    for version in versions:
        if not isinstance(version, dict):
            continue

        normalized.append(
            {
                **version,
                "created": to_iso_utc(version.get("created")),
            }
        )

    return normalized


def json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return to_iso_utc(value)
    return str(value)


def normalize_row(row: dict[str, Any], include_raw: bool) -> dict[str, Any] | None:
    arxiv_id = clean_text(row.get("id"))
    if not arxiv_id:
        return None

    categories = parse_categories(row.get("categories"))
    versions = row.get("versions") if isinstance(row.get("versions"), list) else []
    normalized_versions = normalize_versions(versions)
    update_date = to_iso_utc(row.get("update_date"))
    versioned_arxiv_id = append_version(arxiv_id, versions)
    abs_url = arxiv_abs_url(versioned_arxiv_id)
    extracted_id = get_arxiv_id_path(abs_url)

    doc: dict[str, Any] = {
        "id": abs_url,
        "extractedID": extracted_id,
        "updated": get_version_date(versions, -1) or update_date,
        "published": get_version_date(versions, 0) or update_date,
        "title": clean_text(row.get("title")),
        "summary": clean_text(row.get("abstract")),
        "authors": parse_authors(row),
        "doi": clean_text(row.get("doi")),
        "journalRef": clean_text(row.get("journal-ref")),
        "primaryCategory": categories[0] if categories else "",
        "category": categories,
        "comment": clean_text(row.get("comments")),
        "pdfLink": arxiv_pdf_url(extracted_id),
        "absLink": abs_url,
        "baseArxivID": arxiv_id,
        "latestVersion": get_version_label(versions),
        "submitter": clean_text(row.get("submitter")),
        "authorsRaw": clean_text(row.get("authors")),
        "authorsParsed": row.get("authors_parsed") or [],
        "reportNo": clean_text(row.get("report-no")),
        "license": clean_text(row.get("license")),
        "versions": normalized_versions,
        "updateDate": update_date,
        "metadataSource": "local-parquet",
    }

    if include_raw:
        doc["rawMetadata"] = row

    return doc


def output_path_for(parquet_path: Path, explicit_output: Path | None) -> Path:
    if explicit_output is not None:
        return explicit_output
    return parquet_path.with_suffix(".ndjson")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a local arXiv metadata Parquet file to NDJSON."
    )
    parser.add_argument("parquet_file", type=Path, help="Path to a local .parquet file.")
    parser.add_argument("--out", type=Path, default=None, help="Optional output .ndjson path.")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the output file if it already exists.",
    )
    parser.add_argument(
        "--include-raw",
        action="store_true",
        help="Also include the original Parquet row under rawMetadata.",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Stop after writing this many rows. Useful for sample outputs.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=50_000,
        help="Print progress every N rows.",
    )
    args = parser.parse_args()
    if args.max_rows is not None and args.max_rows < 0:
        raise SystemExit("--max-rows must be 0 or greater")
    return args


def main() -> int:
    args = parse_args()
    parquet_path = args.parquet_file

    if not parquet_path.exists():
        raise SystemExit(f"Parquet file not found: {parquet_path}")
    if parquet_path.suffix.lower() != ".parquet":
        raise SystemExit(f"Expected a .parquet file: {parquet_path}")

    output_path = output_path_for(parquet_path, args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists() and not args.overwrite:
        raise SystemExit(f"Output file already exists. Use --overwrite: {output_path}")

    parquet_file = pq.ParquetFile(parquet_path)
    total_rows = parquet_file.metadata.num_rows
    written = 0
    skipped = 0

    print(f"Input: {parquet_path}", flush=True)
    print(f"Rows: {total_rows}", flush=True)
    print(f"Output: {output_path}", flush=True)

    with output_path.open("w", encoding="utf-8") as output_file:
        for row_group_index in range(parquet_file.metadata.num_row_groups):
            table = parquet_file.read_row_group(row_group_index)

            for row in table.to_pylist():
                if args.max_rows is not None and written >= args.max_rows:
                    break

                doc = normalize_row(row, include_raw=args.include_raw)
                if doc is None:
                    skipped += 1
                    continue

                output_file.write(
                    json.dumps(doc, ensure_ascii=False, separators=(",", ":"), default=json_default)
                )
                output_file.write("\n")
                written += 1

                if args.progress_every > 0 and written % args.progress_every == 0:
                    print(f"written={written}/{total_rows} skipped={skipped}", flush=True)

            if args.max_rows is not None and written >= args.max_rows:
                break

    print(f"Done. written={written} skipped={skipped}", flush=True)
    print(f"Output: {output_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
