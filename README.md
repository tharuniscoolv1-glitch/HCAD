# HCAD (Highly Compressed Activity Data)

[![PyPI version](https://img.shields.io/pypi/v/hcad.svg)](https://pypi.org/project/hcad/)
[![Python versions](https://img.shields.io/pypi/pyversions/hcad.svg)](https://pypi.org/project/hcad/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

**HCAD** is an ultra-fast, lightweight binary tabular file format and Python engine designed for high-density activity and time-series records.

It uses Python's standard `struct` module for zero-overhead binary serialization and `zlib` for data compression, minimizing file size and eliminating redundant metadata overhead. Core HCAD has **zero external dependencies**.

---

## Key Features

* **Compact Binary Header (20 Bytes):** Magic identifier (`3A 3B 4C 1E FF B4 E9 FF`), version, compression flag, column count, max descriptor size, and a 4-byte `row_count` enabling $O(1)$ length calculation.
* **Flexible Column Schemas:** Supports single values (`'i'`, `'f'`, `'d'`) and compound struct formats (e.g. `'H h H'`, `'c i'`, `'cccc II'`).
* **High-Throughput Vectorized Codec:** Single unified `struct.Struct` with C-level `iter_unpack` decoding and preallocated `pack_into` encoding.
* **$O(1)$ Random Access & Slicing:** Seek and read any arbitrary row or range without loading the full file into memory (`read_row(index)`, `read_range(start, end)`).
* **Bounded-Memory Streaming:** Stream millions of rows in constant RAM with disk-backed batch generators (`iter_rows(batch_size)`).
* **In-Place Mutations & Shift Deletion:**
  * $O(1)$ in-place row appends without rewriting headers or table definitions.
  * $O(1)$ in-place cell updates directly to disk bytes.
  * $O(1)$-RAM intermediate row deletion using bounded 64 KB binary chunk shifting and terminal truncation.
* **Zero-Dependency CLI (`hcad`):** Inspect metadata (`info`), validate integrity (`validate`), print records (`dump`), toggle compression (`compress`/`decompress`), and import/export CSV & JSON directly from your shell.
* **Data Science Bridges:** Zero-dependency CSV & JSON import/export, plus optional pandas DataFrame and NumPy array bridges (`to_pandas`, `from_pandas`, `to_numpy`, `from_numpy`).
* **Dual API:** Both a modern, Pythonic object-oriented API (`HCADFile`, `Table`, `Column`) and a legacy procedural API (`createNewFile`, `validateFile`, `writeDataToFile`, etc.).

---

## Installation

```bash
# Standard zero-dependency installation
pip install hcad

# Optional: with pandas and numpy dataframe support
pip install hcad[dataframe]
```

---

## Command-Line Interface (CLI)

HCAD ships with a fast command-line utility for managing datasets:

```bash
# Inspect file metadata and column schema
hcad info activity.hcad

# Validate binary file integrity and decode health
hcad validate activity.hcad

# Dump table rows to terminal (supports --format table|csv|json)
hcad dump activity.hcad --limit 20 --format table

# Compress / decompress in place
hcad compress activity.hcad
hcad decompress activity.hcad

# Export HCAD to CSV or JSON
hcad export activity.hcad --format csv -o activity.csv
hcad export activity.hcad --format json -o activity.json

# Import CSV to HCAD
hcad import activity.csv -o activity.hcad --columns "0:i,1:d,2:4s" --compress
```

---

## Quick Start (Python API)

### 1. Modern Object-Oriented API (`hcad`)

```python
from hcad import HCADFile, Table, Column, COMPRESSION_NONE, COMPRESSION_ZLIB

# 1. Define schema
columns = [
    Column(0, 'i'),        # Integer (Column ID 0)
    Column(1, 'd'),        # Double Float (Column ID 1)
    Column(2, '4s'),       # 4-byte string (Column ID 2)
]

# 2. Create file
hf = HCADFile.create("activity.hcad", columns, compression=COMPRESSION_NONE)

# 3. Append rows
rows = [
    [1, 24.5, b"r001"],
    [2, 25.1, b"r002"],
    [3, 26.0, b"r003"],
]
hf.append_rows(rows)

# 4. O(1) Random Access and Streaming
print("Row 0:", hf.read_row(0))
for row in hf.iter_rows(batch_size=1024):
    print("Streamed row:", row)

# 5. O(1) In-Place Cell Update (Row 0, Column 1 -> 99.9)
hf.update_cell(row_idx=0, col_id_or_idx=1, value=99.9)

# 6. Bounded-Memory Row Deletion
hf.delete_row(row_idx=1)

# 7. CSV / JSON Bridges
hf.to_csv("activity.csv")
hf.to_json("activity.json", orient="split")

# 8. Pandas & NumPy Interoperability (requires hcad[dataframe])
table = hf.read()
df = table.to_pandas()
arr = table.to_numpy()
```

---

### 2. Procedural API (`hcad.functions`)

For legacy scripts:

```python
from hcad import (
    createNewFile,
    validateFile,
    writeDataToFile,
    readDataFromFile,
    compressDataInFile,
    decompressDataInFile,
)

# Create file
createNewFile("data.hcad", ".", ["i", "d"])

# Write data
data = {
    'numberOfColumns': 2,
    'descriptions': ["i", "d"],
    'payload': {
        0: [100, 200],
        1: [3.14, 2.71],
    }
}
writeDataToFile("data.hcad", data)

# Read data (columnar dict)
result = readDataFromFile("data.hcad")
print(result)

# Toggle compression
compressDataInFile("data.hcad")
decompressDataInFile("data.hcad")
```

---

## File Format Specification (v2)

### Header Layout (20 Bytes)

| Offset | Field | Type | Size | Description |
| :--- | :--- | :--- | :--- | :--- |
| `0x00` | `Identifier` | `bytes` | 8 B | Magic bytes: `3A 3B 4C 1E FF B4 E9 FF` |
| `0x08` | `ColumnCount` | `uint16` | 2 B | Number of columns ($N$) |
| `0x0A` | `MaxDescriptorSize` | `uint16` | 2 B | Max allowed bytes for column descriptor string |
| `0x0C` | `Version` | `uint16` | 2 B | Format version (currently `1`) |
| `0x0E` | `Compression` | `uint16` | 2 B | `0` = None, `1` = zlib |
| `0x10` | `RowCount` | `uint32` | 4 B | Number of rows stored in the file |

### Column Section

For each column ($i = 0 \dots N-1$):
* `ColumnID` (2 B, uint16)
* `DescriptorLength` (2 B, uint16)
* `DescriptorString` (UTF-8 bytes, length = `DescriptorLength`)

### Data Section

* **Uncompressed (`0`):** Contiguous packed rows (`RowCount * RowByteSize` bytes).
* **Compressed (`1`):** zlib compressed stream of the uncompressed row payload.

---

## Running Tests

Run the complete test suite using Python's built-in `unittest` runner:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

---

## License

Licensed under the [Apache License, Version 2.0](LICENSE).
