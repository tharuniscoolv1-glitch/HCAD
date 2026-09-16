"""
HCAD Binary Codec: optimized batch row serialization and deserialization.
"""
from typing import Any, List, Optional, Sequence, Tuple
from ..core.column import Column
from ..core.exceptions import CorruptedFileError, SchemaMismatchError


class RowCodec:
    """
    Handles fast binary packing and unpacking of tabular rows.
    """

    def __init__(self, columns: Sequence[Column]):
        self.columns = list(columns)
        self.row_byte_size = sum(col.byte_size for col in self.columns)
        
        # Precompute column slice offsets: [(start, end, column_obj), ...]
        self._col_slices: List[Tuple[int, int, Column]] = []
        curr = 0
        for col in self.columns:
            next_offset = curr + col.byte_size
            self._col_slices.append((curr, next_offset, col))
            curr = next_offset

    def encode_rows(self, rows: Sequence[Sequence[Any]]) -> bytes:
        """
        Encodes a list of rows into contiguous binary bytes.
        """
        if not rows:
            return b''

        buf = bytearray()
        for row_idx, row in enumerate(rows):
            if len(row) != len(self.columns):
                raise SchemaMismatchError(
                    f"Row {row_idx} length mismatch: expected {len(self.columns)} values, got {len(row)}."
                )
            for col_idx, (_, _, col) in enumerate(self._col_slices):
                buf.extend(col.pack(row[col_idx]))

        return bytes(buf)

    def decode_rows(
        self, raw_bytes: bytes, expected_row_count: Optional[int] = None
    ) -> List[List[Any]]:
        """
        Decodes contiguous binary bytes into a list of row values.
        """
        if not raw_bytes:
            if expected_row_count is not None and expected_row_count > 0:
                raise CorruptedFileError(
                    f"Corrupted HCAD data: expected {expected_row_count} rows, but got 0 bytes."
                )
            return []

        if self.row_byte_size <= 0:
            return []

        total_bytes = len(raw_bytes)
        if total_bytes % self.row_byte_size != 0:
            raise CorruptedFileError(
                f"Corrupted HCAD data: payload size ({total_bytes} bytes) is not a multiple "
                f"of row size ({self.row_byte_size} bytes)."
            )

        actual_row_count = total_bytes // self.row_byte_size
        if expected_row_count is not None and actual_row_count != expected_row_count:
            raise CorruptedFileError(
                f"Corrupted HCAD data: expected {expected_row_count} rows, but payload contains {actual_row_count} rows."
            )

        rows: List[List[Any]] = []
        slices = self._col_slices
        for row_idx in range(actual_row_count):
            row_start = row_idx * self.row_byte_size
            row_bytes = raw_bytes[row_start : row_start + self.row_byte_size]
            row_vals = []
            for start, end, col in slices:
                row_vals.append(col.unpack(row_bytes[start:end]))
            rows.append(row_vals)

        return rows
