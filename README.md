# parquet_to_ndjson.py

Convert a local arXiv metadata `.parquet` file into normalized `.ndjson`, with one JSON document per line.

The script cleans text fields, normalizes dates to UTC where possible, formats authors, splits categories, builds arXiv abstract/PDF links, preserves version metadata, and skips rows without an arXiv `id`.

## Data Formats

Parquet is a compressed columnar binary format. It is best for large datasets, analytics, and efficient storage.

NDJSON is newline-delimited JSON: one JSON object per line. It is best for imports, streaming, logs, search indexing, and tools that process records one at a time.

This converter reads arXiv metadata Parquet rows shaped like this:

```ts
interface ParquetInputRow {
  id: string;
  submitter: string;
  authors: string;
  title: string;
  comments: string;
  "journal-ref": string;
  doi: string;
  "report-no": string;
  categories: string;
  license: string;
  abstract: string;
  versions: Array<{
    version: string;
    created: string;
  }>;
  update_date: Date;
  authors_parsed: string[][];
}
```

It writes one NDJSON line per valid row. Each line is a JSON object shaped like this:

```ts
interface NdjsonOutputDocument {
  id: string;
  extractedID: string;
  updated: string;
  published: string;
  title: string;
  summary: string;
  authors: string[];
  doi: string;
  journalRef: string;
  primaryCategory: string;
  category: string[];
  comment: string;
  pdfLink: string;
  absLink: string;
  baseArxivID: string;
  latestVersion: string;
  submitter: string;
  authorsRaw: string;
  authorsParsed: string[][];
  reportNo: string;
  license: string;
  versions: Array<{
    version: string;
    created: string;
  }>;
  updateDate: string;
  metadataSource: "local-parquet";
  rawMetadata?: ParquetInputRow;
}
```

## Get Started

Install the dependency:

```powershell
pip install pyarrow
```

Run the converter:

```powershell
python .\parquet_to_ndjson.py E:\ArxivMeta\train-00009-of-00010.parquet
```

By default, output is written beside the input file with the `.ndjson` extension.

## Usage

```powershell
python .\parquet_to_ndjson.py <parquet_file> [options]
```

## Options

- `<parquet_file>`: Required path to a local `.parquet` file.
- `--out <path>`: Write output to a specific `.ndjson` path.
- `--overwrite`: Replace the output file if it already exists.
- `--include-raw`: Include the original Parquet row under `rawMetadata`.
- `--max-rows <n>`: Stop after writing `n` rows. Must be `0` or greater.
- `--progress-every <n>`: Print progress every `n` written rows. Default: `50000`. Use `0` to disable progress messages.
- `-h`, `--help`: Show command help.

## Included Example

The `example` folder contains:

- `sample.parquet`: 1,000-row sample input.
- `sample.ndjson`: generated NDJSON output.

Show help:

```powershell
python .\parquet_to_ndjson.py --help
```

Generate `example\sample.ndjson` from the sample input:

```powershell
python .\parquet_to_ndjson.py .\example\sample.parquet
```

Regenerate it if the output already exists:

```powershell
python .\parquet_to_ndjson.py .\example\sample.parquet --overwrite
```

Write to a custom output path:

```powershell
python .\parquet_to_ndjson.py .\example\sample.parquet --out .\example\custom.ndjson
```

Include the original Parquet row in each output document:

```powershell
python .\parquet_to_ndjson.py .\example\sample.parquet --out .\example\sample.raw.ndjson --include-raw --overwrite
```

Write only the first 100 rows:

```powershell
python .\parquet_to_ndjson.py .\example\sample.parquet --out .\example\sample-100.ndjson --max-rows 100 --overwrite
```

Print progress every 100 written rows:

```powershell
python .\parquet_to_ndjson.py .\example\sample.parquet --out .\example\sample.progress.ndjson --progress-every 100 --overwrite
```

Run with all conversion options together:

```powershell
python .\parquet_to_ndjson.py .\example\sample.parquet --out .\example\sample.full.ndjson --overwrite --include-raw --max-rows 1000 --progress-every 100
```
