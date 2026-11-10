# How to add a source

A new source system delivers files into `sources/<source>/<delivery date>/`. To bring it onto the platform:

1. Ask the vendor for a test delivery and the document that describes its columns; keep the document as
   `sources/<source>/README-vendor.md`.
2. Profile the test delivery: delimiter, types, keys, nulls and personal data.
3. Create the bronze tables, one file per table: `pipeline/bronze/<source>_<file>.sql`, every column as text.
4. Write the loader `pipeline/loaders/<source>.py`; it maps each file to its bronze table and calls `load_bronze`.
5. Add the job `jobs/ingest_<source>.yaml` with its schedule and one step per file.
6. Run it once by hand: `make run JOB=ingest_<source>`, and check the rows in `ops/runs.jsonl`.
