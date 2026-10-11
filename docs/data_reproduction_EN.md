# Reproducing the Amazon Review Dataset

This repository does not redistribute the Amazon Reviews 2023 source files or
derived Parquet files. It provides the filtering notebook and a command-line
script that rebuild the documented analysis set: 547 products and 105,060
reviews.

## Source files

Download the following `Beauty_and_Personal_Care` files from the official
[Amazon Reviews 2023](https://amazon-reviews-2023.github.io/) page.

- `meta_Beauty_and_Personal_Care.jsonl.gz`
- `Beauty_and_Personal_Care.jsonl.gz`

Place them under `data/raw/`. The source and generated files remain ignored by
Git and are subject to the terms published by the dataset provider.

## Selection rules

The pipeline selects shampoo titles, removes known unrelated title patterns,
requires at least 300 Amazon ratings and product text, then keeps products with
at least 50 reviews and 10 reviews rated three or lower. It also removes review
duplicates and retains only products whose observed reviews refer to one child
ASIN, preventing variant attributes from being mixed.

`analyzed_asin` records that selected child ASIN in the derived files. The
application database still uses `parent_asin` as the product key and preserves
the original review `asin`.

## Run the pipeline

```powershell
python -m pip install -r requirements-data.txt
python scripts/prepare_amazon_data.py `
  --metadata data/raw/meta_Beauty_and_Personal_Care.jsonl.gz `
  --reviews data/raw/Beauty_and_Personal_Care.jsonl.gz `
  --output-dir data
```

The command creates `products_rds.parquet`, `reviews_rds.parquet`, and a
`dataset_manifest.json` containing the filters, row counts, columns, and output
SHA-256 hashes. `--skip-count-check` is intended only for investigating source
or environment differences; relational and aggregate validation still runs.

After the local database migrations have run and the target tables are empty,
load the files with:

```powershell
python scripts/load_data.py
```

For a cell-by-cell view, see
[`notebooks/01_data_filtering.ipynb`](../notebooks/01_data_filtering.ipynb).
