"""
HCAD Table: in-memory representation of tabular activity data.
Provides fast manipulation, validation, and zero-dependency CSV/JSON export/import,
as well as optional pandas and NumPy interoperability bridges.
"""
import ast
import csv
import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from .column import Column
from .exceptions import SchemaMismatchError


def _format_cell_for_csv(val: Any) -> str:
    """Formats a Python cell value into a string suitable for CSV."""
    if isinstance(val, bytes):
        try:
            return val.decode('utf-8').rstrip('\x00')
        except UnicodeDecodeError:
            return val.hex()
    elif isinstance(val, (list, tuple)):
        cleaned = [
            (v.decode('utf-8').rstrip('\x00') if isinstance(v, bytes) else v)
            for v in val
        ]
        return json.dumps(cleaned)
    return str(val)


def _format_cell_for_json(val: Any) -> Any:
    """Formats a Python cell value into a JSON-serializable object."""
    if isinstance(val, bytes):
        try:
            return val.decode('utf-8').rstrip('\x00')
        except UnicodeDecodeError:
            return val.hex()
    elif isinstance(val, (list, tuple)):
        return [
            (v.decode('utf-8').rstrip('\x00') if isinstance(v, bytes) else v)
            for v in val
        ]
    return val


def _parse_csv_cell(raw: str, col: Column) -> Any:
    """Parses a CSV string token according to the column's struct descriptor."""
    raw = raw.strip()
    if col.field_count == 1:
        desc = col.descriptor
        if desc.endswith(('s', 'p', 'c')):
            return raw.encode('utf-8')
        if desc.endswith('?'):
            return raw.lower() in ('true', '1', 't', 'yes')
        if any(desc.endswith(ch) for ch in ('e', 'f', 'd')):
            return float(raw)
        if any(desc.endswith(ch) for ch in ('b', 'B', 'h', 'H', 'i', 'I', 'l', 'L', 'q', 'Q', 'n', 'N', 'P')):
            return int(raw)
        try:
            return int(raw)
        except ValueError:
            try:
                return float(raw)
            except ValueError:
                return raw
    else:
        # Compound column
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, (list, tuple)) and len(parsed) == col.field_count:
                return tuple(parsed)
        except Exception:
            pass
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, (list, tuple)) and len(parsed) == col.field_count:
                return tuple(parsed)
        except Exception:
            pass
        parts = [p.strip() for p in (raw.split(',') if ',' in raw else raw.split()) if p.strip()]
        if len(parts) == col.field_count:
            converted = []
            for p in parts:
                try:
                    converted.append(int(p))
                except ValueError:
                    try:
                        converted.append(float(p))
                    except ValueError:
                        converted.append(p)
            return tuple(converted)
        raise SchemaMismatchError(
            f"Cannot parse '{raw}' as compound column with {col.field_count} values for {col}."
        )


class Table:
    """
    In-memory representation of an HCAD tabular dataset.
    """

    def __init__(self, columns: Sequence[Column], rows: Optional[List[List[Any]]] = None):
        self.columns = list(columns)
        self._col_id_to_idx: Dict[int, int] = {}
        for idx, col in enumerate(self.columns):
            if col.id in self._col_id_to_idx:
                raise SchemaMismatchError(f"Duplicate column ID {col.id} detected in schema.")
            self._col_id_to_idx[col.id] = idx

        self.row_byte_size = sum(col.byte_size for col in self.columns)
        self.rows: List[List[Any]] = []
        if rows:
            for row in rows:
                self.add_row(row)

    @property
    def column_count(self) -> int:
        return len(self.columns)

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def _resolve_col_idx(self, col_id_or_idx: int) -> int:
        """
        Resolves column identifier to 0-based positional index.
        Prefers exact column ID match first.
        If col_id_or_idx is not an existing column ID but falls within positional bounds,
        it resolves as a positional index.
        For explicit access without ambiguity, use get_column_by_id() or get_column_by_index().
        """
        if col_id_or_idx in self._col_id_to_idx:
            return self._col_id_to_idx[col_id_or_idx]
        if 0 <= col_id_or_idx < len(self.columns):
            return col_id_or_idx
        raise SchemaMismatchError(
            f"Column identifier '{col_id_or_idx}' not found. Available column IDs: {list(self._col_id_to_idx.keys())}"
        )

    def get_column_index(self, col_id: int) -> int:
        """Returns the 0-based positional index for a given column ID."""
        if col_id not in self._col_id_to_idx:
            raise SchemaMismatchError(f"Column ID {col_id} not found in table schema.")
        return self._col_id_to_idx[col_id]

    def add_row(self, row: Union[Sequence[Any], Dict[int, Any]]) -> None:
        """
        Validates and adds a single row to the table.
        """
        if isinstance(row, dict):
            row_vals = []
            for col in self.columns:
                if col.id not in row:
                    raise SchemaMismatchError(f"Missing value for column ID {col.id} in row dict.")
                row_vals.append(row[col.id])
        elif isinstance(row, (list, tuple)):
            if len(row) != len(self.columns):
                raise SchemaMismatchError(
                    f"Row length mismatch: expected {len(self.columns)} values, got {len(row)}."
                )
            row_vals = list(row)
        else:
            raise SchemaMismatchError(f"Row must be a sequence or dict, got {type(row).__name__}.")

        self.rows.append(row_vals)

    def add_rows(self, rows: Sequence[Union[Sequence[Any], Dict[int, Any]]]) -> None:
        for r in rows:
            self.add_row(r)

    def get_row(self, index: int) -> List[Any]:
        return self.rows[index]

    def get_column(self, col_id_or_idx: int) -> List[Any]:
        """
        Returns column values by column ID or index.
        Prefers column ID first; falls back to positional index.
        """
        idx = self._resolve_col_idx(col_id_or_idx)
        return [r[idx] for r in self.rows]

    def get_column_by_id(self, col_id: int) -> List[Any]:
        """Returns column values matching the exact column ID."""
        if col_id not in self._col_id_to_idx:
            raise SchemaMismatchError(
                f"Column ID {col_id} not found. Available column IDs: {list(self._col_id_to_idx.keys())}"
            )
        idx = self._col_id_to_idx[col_id]
        return [r[idx] for r in self.rows]

    def get_column_by_index(self, col_idx: int) -> List[Any]:
        """Returns column values at the exact 0-based positional index."""
        if not (0 <= col_idx < len(self.columns)):
            raise IndexError(
                f"Column index {col_idx} out of range (0..{len(self.columns)-1})."
            )
        return [r[col_idx] for r in self.rows]

    def update_cell(self, row_idx: int, col_id_or_idx: int, value: Any) -> None:
        if not (0 <= row_idx < len(self.rows)):
            raise IndexError(f"Row index {row_idx} out of range (0..{len(self.rows)-1}).")
        col_idx = self._resolve_col_idx(col_id_or_idx)
        self.rows[row_idx][col_idx] = value

    def update_cell_by_id(self, row_idx: int, col_id: int, value: Any) -> None:
        if not (0 <= row_idx < len(self.rows)):
            raise IndexError(f"Row index {row_idx} out of range (0..{len(self.rows)-1}).")
        if col_id not in self._col_id_to_idx:
            raise SchemaMismatchError(f"Column ID {col_id} not found.")
        self.rows[row_idx][self._col_id_to_idx[col_id]] = value

    def update_cell_by_index(self, row_idx: int, col_idx: int, value: Any) -> None:
        if not (0 <= row_idx < len(self.rows)):
            raise IndexError(f"Row index {row_idx} out of range (0..{len(self.rows)-1}).")
        if not (0 <= col_idx < len(self.columns)):
            raise IndexError(f"Column index {col_idx} out of range (0..{len(self.columns)-1}).")
        self.rows[row_idx][col_idx] = value

    def delete_row(self, row_idx: int) -> List[Any]:
        if not (0 <= row_idx < len(self.rows)):
            raise IndexError(f"Row index {row_idx} out of range (0..{len(self.rows)-1}).")
        return self.rows.pop(row_idx)

    def to_dict(self) -> Dict[int, List[Any]]:
        """
        Returns data formatted as a columnar dictionary:
        {column_id: [values_for_column]}
        """
        result: Dict[int, List[Any]] = {col.id: [] for col in self.columns}
        for row in self.rows:
            for idx, col in enumerate(self.columns):
                result[col.id].append(row[idx])
        return result

    @classmethod
    def from_dict(cls, columns: Sequence[Column], data: Dict[int, Sequence[Any]]) -> 'Table':
        """
        Creates a Table from a columnar dictionary: {column_id: [values]}
        """
        table = cls(columns)
        if not columns:
            return table

        if not isinstance(data, dict):
            raise SchemaMismatchError("Data payload must be a dictionary.")

        row_counts = []
        for col in columns:
            if col.id not in data:
                raise SchemaMismatchError(f"Missing column ID {col.id} in payload data.")
            col_data = data[col.id]
            if not isinstance(col_data, (list, tuple)):
                raise SchemaMismatchError(f"Column {col.id} data must be a sequence, got {type(col_data).__name__}.")
            row_counts.append(len(col_data))

        if len(set(row_counts)) > 1:
            raise SchemaMismatchError(
                f"Inconsistent column lengths: found lengths {row_counts}."
            )

        num_rows = row_counts[0] if row_counts else 0
        for i in range(num_rows):
            row_vals = [data[col.id][i] for col in columns]
            table.rows.append(row_vals)

        return table

    # --- CSV Interop ---

    def to_csv(
        self,
        file_path_or_buffer: Union[str, Path, Any],
        header: Optional[Sequence[str]] = None,
        write_header: bool = True,
        encoding: str = "utf-8",
    ) -> None:
        """
        Exports table rows to a CSV file or buffer. Zero external dependencies.
        """
        col_names = list(header) if header is not None else [f"col_{c.id}" for c in self.columns]
        if len(col_names) != len(self.columns):
            raise SchemaMismatchError(
                f"Header length ({len(col_names)}) does not match column count ({len(self.columns)})."
            )

        def write_content(writer):
            if write_header:
                writer.writerow(col_names)
            for row in self.rows:
                formatted_row = [_format_cell_for_csv(cell) for cell in row]
                writer.writerow(formatted_row)

        if hasattr(file_path_or_buffer, 'write'):
            writer = csv.writer(file_path_or_buffer)
            write_content(writer)
        else:
            with open(file_path_or_buffer, 'w', newline='', encoding=encoding) as f:
                writer = csv.writer(f)
                write_content(writer)

    @classmethod
    def from_csv(
        cls,
        file_path_or_buffer: Union[str, Path, Any],
        columns: Sequence[Column],
        has_header: bool = True,
        encoding: str = "utf-8",
    ) -> 'Table':
        """
        Imports table data from a CSV file or buffer with automatic type casting.
        """
        if not columns:
            raise SchemaMismatchError("Columns schema must be provided to import CSV data.")

        def parse_reader(reader) -> List[List[Any]]:
            rows = []
            it = iter(reader)
            if has_header:
                try:
                    next(it)
                except StopIteration:
                    return []

            for row_num, raw_row in enumerate(it, start=1):
                if not raw_row or (len(raw_row) == 1 and not raw_row[0].strip()):
                    continue
                if len(raw_row) != len(columns):
                    raise SchemaMismatchError(
                        f"CSV row {row_num} has {len(raw_row)} values, expected {len(columns)}."
                    )
                parsed_vals = [
                    _parse_csv_cell(raw_row[i], columns[i])
                    for i in range(len(columns))
                ]
                rows.append(parsed_vals)
            return rows

        if hasattr(file_path_or_buffer, 'read'):
            reader = csv.reader(file_path_or_buffer)
            rows = parse_reader(reader)
        else:
            with open(file_path_or_buffer, 'r', newline='', encoding=encoding) as f:
                reader = csv.reader(f)
                rows = parse_reader(reader)

        return cls(columns, rows)

    # --- JSON Interop ---

    def to_json(
        self,
        file_path: Optional[Union[str, Path]] = None,
        orient: str = "records",
        indent: Optional[int] = None,
    ) -> str:
        """
        Serializes table to JSON. Supports 'records', 'columns', and 'split' orientations.
        """
        if orient == "records":
            data = []
            for row in self.rows:
                rec = {str(col.id): _format_cell_for_json(row[i]) for i, col in enumerate(self.columns)}
                data.append(rec)
        elif orient == "columns":
            data = {
                str(col.id): [_format_cell_for_json(row[i]) for row in self.rows]
                for i, col in enumerate(self.columns)
            }
        elif orient == "split":
            data = {
                "columns": [col.id for col in self.columns],
                "descriptors": [col.descriptor for col in self.columns],
                "data": [[_format_cell_for_json(c) for c in row] for row in self.rows],
            }
        else:
            raise ValueError(f"Unsupported orient: '{orient}'. Choose 'records', 'columns', or 'split'.")

        json_str = json.dumps(data, indent=indent)
        if file_path is not None:
            Path(file_path).write_text(json_str, encoding="utf-8")
        return json_str

    @classmethod
    def from_json(
        cls,
        file_path_or_str: Union[str, Path],
        columns: Optional[Sequence[Column]] = None,
        orient: str = "auto",
    ) -> 'Table':
        """
        Parses table data from a JSON file or JSON string.
        """
        p = Path(file_path_or_str) if isinstance(file_path_or_str, (str, Path)) else None
        if p is not None and p.exists() and p.is_file():
            raw_text = p.read_text(encoding="utf-8")
        else:
            raw_text = str(file_path_or_str)

        data = json.loads(raw_text)

        # Detect orientation
        if isinstance(data, dict) and "columns" in data and "descriptors" in data and "data" in data:
            # 'split' orientation
            if columns is None:
                columns = [
                    Column(col_id=cid, descriptor=desc)
                    for cid, desc in zip(data["columns"], data["descriptors"])
                ]
            rows = data["data"]
            return cls(columns, rows)

        if columns is None:
            raise SchemaMismatchError(
                "Columns schema must be provided when importing non-split JSON formats."
            )

        if isinstance(data, list):
            # 'records' orientation or list of rows
            rows = []
            for item in data:
                if isinstance(item, dict):
                    row = []
                    for col in columns:
                        val = item.get(col.id, item.get(str(col.id), item.get(f"col_{col.id}")))
                        if val is None and str(col.id) not in item and col.id not in item:
                            raise SchemaMismatchError(f"Missing key for column {col.id} in JSON record.")
                        row.append(val)
                    rows.append(row)
                elif isinstance(item, (list, tuple)):
                    rows.append(list(item))
                else:
                    raise SchemaMismatchError(f"Unexpected JSON item type: {type(item).__name__}")
            return cls(columns, rows)

        elif isinstance(data, dict):
            # 'columns' orientation
            col_data = {}
            for col in columns:
                val = data.get(col.id, data.get(str(col.id)))
                if val is None:
                    raise SchemaMismatchError(f"Missing column {col.id} in JSON dict.")
                col_data[col.id] = val
            return cls.from_dict(columns, col_data)

        raise SchemaMismatchError(f"Unsupported JSON root type: {type(data).__name__}")

    # --- Pandas & NumPy Bridges (Optional) ---

    def to_pandas(self, column_names: Optional[Sequence[str]] = None) -> Any:
        """
        Converts the Table to a pandas.DataFrame.
        Requires pandas to be installed.
        """
        try:
            import pandas as pd
        except ImportError as e:
            raise ImportError(
                "pandas is required for to_pandas(). Install it via 'pip install pandas' or 'pip install hcad[dataframe]'."
            ) from e

        names = list(column_names) if column_names is not None else [f"col_{col.id}" for col in self.columns]
        if len(names) != len(self.columns):
            raise SchemaMismatchError(
                f"column_names length ({len(names)}) does not match column count ({len(self.columns)})."
            )

        data = {}
        for idx, col in enumerate(self.columns):
            col_vals = []
            for r in self.rows:
                v = r[idx]
                if isinstance(v, bytes):
                    try:
                        v = v.decode('utf-8').rstrip('\x00')
                    except UnicodeDecodeError:
                        pass
                col_vals.append(v)
            data[names[idx]] = col_vals

        return pd.DataFrame(data)

    @classmethod
    def from_pandas(cls, df: Any, columns: Optional[Sequence[Column]] = None) -> 'Table':
        """
        Creates an HCAD Table from a pandas.DataFrame.
        Requires pandas to be installed.
        """
        try:
            import pandas as pd
        except ImportError as e:
            raise ImportError(
                "pandas is required for from_pandas(). Install it via 'pip install pandas' or 'pip install hcad[dataframe]'."
            ) from e

        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"Expected pandas.DataFrame, got {type(df).__name__}")

        if columns is None:
            inferred = []
            for idx, col_name in enumerate(df.columns):
                dtype = df[col_name].dtype
                dtype_str = str(dtype)
                if 'int' in dtype_str:
                    desc = 'q' if '64' in dtype_str else 'i'
                elif 'float' in dtype_str:
                    desc = 'd'
                elif 'bool' in dtype_str:
                    desc = '?'
                else:
                    max_len = 64
                    for val in df[col_name].dropna():
                        s_len = len(str(val).encode('utf-8'))
                        if s_len > max_len:
                            max_len = s_len
                    desc = f"{max_len}s"
                inferred.append(Column(idx, desc))
            columns = inferred

        rows = []
        for row in df.itertuples(index=False):
            rows.append(list(row))
        return cls(columns, rows)

    def to_numpy(self, dtype: Any = None) -> Any:
        """
        Converts tabular data to a NumPy 2D ndarray.
        Requires numpy to be installed.
        """
        try:
            import numpy as np
        except ImportError as e:
            raise ImportError(
                "numpy is required for to_numpy(). Install it via 'pip install numpy' or 'pip install hcad[dataframe]'."
            ) from e

        return np.array(self.rows, dtype=dtype)

    @classmethod
    def from_numpy(cls, array: Any, columns: Sequence[Column]) -> 'Table':
        """
        Creates an HCAD Table from a NumPy 2D array or array-like.
        Requires numpy to be installed.
        """
        try:
            import numpy as np
        except ImportError as e:
            raise ImportError(
                "numpy is required for from_numpy(). Install it via 'pip install numpy' or 'pip install hcad[dataframe]'."
            ) from e

        arr = np.asarray(array)
        if arr.ndim != 2:
            raise ValueError(f"Expected 2D array, got shape {arr.shape}")
        if arr.shape[1] != len(columns):
            raise SchemaMismatchError(
                f"Array column count {arr.shape[1]} does not match provided columns count {len(columns)}."
            )

        return cls(columns, arr.tolist())

    def __len__(self) -> int:
        return len(self.rows)

    def __iter__(self):
        return iter(self.rows)

    def __getitem__(self, item: int) -> List[Any]:
        return self.rows[item]

    def __repr__(self) -> str:
        return f"<HCAD Table: {len(self.columns)} columns, {len(self.rows)} rows>"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Table):
            return False
        if len(self.columns) != len(other.columns):
            return False
        for c1, c2 in zip(self.columns, other.columns):
            if c1.id != c2.id or c1.descriptor != c2.descriptor:
                return False
        return self.rows == other.rows
