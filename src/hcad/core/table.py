"""
HCAD Table: in-memory representation of tabular activity data.
"""
from typing import Any, Dict, List, Sequence, Tuple, Union, Optional
from .column import Column
from .exceptions import SchemaMismatchError


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
        """Resolves column ID or direct column index to 0-based column index."""
        if col_id_or_idx in self._col_id_to_idx:
            return self._col_id_to_idx[col_id_or_idx]
        if 0 <= col_id_or_idx < len(self.columns):
            return col_id_or_idx
        raise SchemaMismatchError(
            f"Column identifier '{col_id_or_idx}' not found. Available column IDs: {list(self._col_id_to_idx.keys())}"
        )

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
        idx = self._resolve_col_idx(col_id_or_idx)
        return [r[idx] for r in self.rows]

    def update_cell(self, row_idx: int, col_id_or_idx: int, value: Any) -> None:
        if not (0 <= row_idx < len(self.rows)):
            raise IndexError(f"Row index {row_idx} out of range (0..{len(self.rows)-1}).")
        col_idx = self._resolve_col_idx(col_id_or_idx)
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

        # Check that all columns are present
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

    def __len__(self) -> int:
        return len(self.rows)

    def __iter__(self):
        return iter(self.rows)

    def __getitem__(self, item: int) -> List[Any]:
        return self.rows[item]

    def __repr__(self) -> str:
        return f"<HCAD Table: {len(self.columns)} columns, {len(self.rows)} rows>"
