# HCAD (Highly Compressed Activity Data)

HCAD is an ultra-fast, lightweight binary tabular file format and Python package designed for high-density activity and time-series records.

It uses Python's `struct` module for zero-overhead binary serialization and `zlib` for data compression, minimizing file size and eliminating redundant metadata overhead.

---

## Features

* **Compact Binary Header (20 Bytes):** Magic identifier (`3A 3B 4C 1E FF B4 E9 FF`), version, compression flag, column count, max descriptor size, and a 4-byte `row_count` enabling $O(1)$ length calculation.
* **Flexible Column Schemas:** Supports single values (`'i'`, `'f'`, `'d'`) and compound struct formats (e.g. `'H h H'`, `'c i'`, `'cccc II'`).
* **$O(1)$ In-Place Appends:** Directly appends uncompressed rows to disk without rewriting the file.
* **$O(1)$ In-Place Cell Updates:** Modify specific cells in uncompressed files using binary seeks without touching other rows.
* **In-Place Row Deletions:** Delete rows with automatic file truncation for terminal rows.
* **Lossless Compression:** Toggle between uncompressed (`0`) and zlib compressed (`1`) states seamlessly.
* **Dual API Support:**
  * **Modern Object-Oriented API:** `HCADFile`, `Table`, and `Column`.
  * **Procedural Backward-Compatible API:** `functions.py` (`createNewFile`, `validateFile`, `writeDataToFile`, etc.).
* **Robust File Integrity:** Zero temporary file leakage on error; comprehensive corruption and truncation detection.

---

## Quick Start

### 1. Modern Object-Oriented API (`hcad`)

```python
from src.hcad import HCADFile, Table, Column, COMPRESSION_NONE, COMPRESSION_ZLIB

# Define schema
columns = [
    Column(col_id=0, descriptor='i'),        # Integer
    Column(col_id=1, descriptor='f'),        # Float
    Column(col_id=2, descriptor='H h H'),    # Compound format (3 shorts)
]

# Create a new HCAD file
hf = HCADFile.create("activity.hcad", columns, compression=COMPRESSION_NONE)

# Write initial rows
table = Table(columns)
table.add_row([1, 24.5, (10, -5, 20)])
table.add_row([2, 25.1, (12, -4, 22)])
hf.write(table)

# O(1) in-place append
hf.append_row([3, 26.0, (15, -2, 25)])

# O(1) in-place cell update (Row index 0, Column 1 -> 24.8)
hf.update_cell(row_idx=0, col_id_or_idx=1, value=24.8)

# Delete a row
hf.delete_row(row_idx=1)

# Compress file in-place
hf.compress()

# Read table
read_table = hf.read()
for row in read_table:
    print(row)
```

---

### 2. Procedural API (`src/functions.py`)

For compatibility with existing scripts:

```python
from src.functions import (
    createNewFile,
    validateFile,
    writeDataToFile,
    readDataFromFile,
    compressDataInFile,
    decompressDataInFile,
)

# 1. Create file with column descriptors
createNewFile("data.hcad", ".", ["i", "f", "c i"])

# 2. Write data
data = {
    'numberOfColumns': 3,
    'descriptions': ["i", "f", "c i"],
    'payload': {
        0: [100, 200],
        1: [3.14, 2.71],
        2: [(b'A', 1), (b'B', 2)],
    }
}
writeDataToFile("data.hcad", data)

# 3. Read data back (returns columnar dictionary)
result = readDataFromFile("data.hcad")
print(result)

# 4. Toggle compression
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

Run the test suite using Python's built-in `unittest` module:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```
