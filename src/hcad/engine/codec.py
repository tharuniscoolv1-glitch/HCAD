"""
HCAD Binary Codec: optimized batch row serialization and deserialization.
Uses a unified pre-compiled struct.Struct with C-level iter_unpack for maximum throughput.
"""
import struct
from typing import Any, List, Optional, Sequence, Tuple
from ..core.column import Column
from ..core.exceptions import CorruptedFileError, SchemaMismatchError


class RowCodec:
    """
    Handles fast binary packing and unpacking of tabular rows using a unified compiled struct.
    """

    def __init__(self, columns: Sequence[Column]):
        self.columns = list(columns)
        
        # Build unified row format string
        if self.columns:
            row_fmt = '<' + ' '.join(col.descriptor for col in self.columns)
            self.row_struct = struct.Struct(row_fmt)
            self.row_byte_size = self.row_struct.size
        else:
            self.row_struct = struct.Struct('<')
            self.row_byte_size = 0

        # Precompute flat tuple slicing mapping: [(start, stop_or_none), ...]
        self._field_slices: List[Tuple[int, Optional[int]]] = []
        curr = 0
        for col in self.columns:
            if col.field_count == 1:
                self._field_slices.append((curr, None))
                curr += 1
            else:
                self._field_slices.append((curr, curr + col.field_count))
                curr += col.field_count

    def encode_rows(self, rows: Sequence[Sequence[Any]]) -> bytes:
        """
        Encodes a list of rows into contiguous binary bytes using preallocated memory and pack_into.
        """
        if not rows or self.row_byte_size <= 0:
            return b''

        total_bytes = len(rows) * self.row_byte_size
        buf = bytearray(total_bytes)
        offset = 0
        pack_into = self.row_struct.pack_into
        row_size = self.row_byte_size
        num_cols = len(self.columns)
        columns = self.columns

        for row_idx, row in enumerate(rows):
            if len(row) != num_cols:
                raise SchemaMismatchError(
                    f"Row {row_idx} length mismatch: expected {num_cols} values, got {len(row)}."
                )

            flat_vals = []
            for col_idx in range(num_cols):
                col = columns[col_idx]
                val = row[col_idx]
                if col.field_count == 1:
                    if isinstance(val, str):
                        val = val.encode('utf-8')
                    flat_vals.append(val)
                else:
                    if not isinstance(val, (list, tuple)) or len(val) != col.field_count:
                        raise SchemaMismatchError(
                            f"Row {row_idx}, Column {col.id} ('{col.descriptor}') expects {col.field_count} values, got {val!r}."
                        )
                    for v in val:
                        flat_vals.append(v.encode('utf-8') if isinstance(v, str) else v)

            try:
                pack_into(buf, offset, *flat_vals)
            except (struct.error, TypeError) as e:
                raise SchemaMismatchError(f"Failed to pack row {row_idx}: {e}") from e

            offset += row_size

        return bytes(buf)

    def encode_single_row(self, row: Sequence[Any]) -> bytes:
        """
        Encodes a single row into packed bytes.
        """
        if len(row) != len(self.columns):
            raise SchemaMismatchError(
                f"Row length mismatch: expected {len(self.columns)} values, got {len(row)}."
            )

        flat_vals = []
        for col_idx, col in enumerate(self.columns):
            val = row[col_idx]
            if col.field_count == 1:
                if isinstance(val, str):
                    val = val.encode('utf-8')
                flat_vals.append(val)
            else:
                if not isinstance(val, (list, tuple)) or len(val) != col.field_count:
                    raise SchemaMismatchError(
                        f"Column {col.id} ('{col.descriptor}') expects {col.field_count} values, got {val!r}."
                    )
                for v in val:
                    flat_vals.append(v.encode('utf-8') if isinstance(v, str) else v)

        try:
            return self.row_struct.pack(*flat_vals)
        except (struct.error, TypeError) as e:
            raise SchemaMismatchError(f"Failed to pack row: {e}") from e

    def decode_single_row(self, row_bytes: bytes) -> List[Any]:
        """
        Decodes a single packed row of bytes into a list of column values.
        """
        if len(row_bytes) != self.row_byte_size:
            raise CorruptedFileError(
                f"Corrupted row: expected {self.row_byte_size} bytes, got {len(row_bytes)} bytes."
            )

        try:
            flat_tuple = self.row_struct.unpack(row_bytes)
        except struct.error as e:
            raise CorruptedFileError(f"Failed to unpack row bytes: {e}") from e

        row_vals = []
        for start, stop in self._field_slices:
            if stop is None:
                row_vals.append(flat_tuple[start])
            else:
                row_vals.append(flat_tuple[start:stop])
        return row_vals

    def decode_rows(
        self, raw_bytes: bytes, expected_row_count: Optional[int] = None
    ) -> List[List[Any]]:
        """
        Decodes contiguous binary bytes into a list of row values using C-level iter_unpack.
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
        field_slices = self._field_slices
        iter_unpack = self.row_struct.iter_unpack

        try:
            for flat_tuple in iter_unpack(raw_bytes):
                row_vals = []
                for start, stop in field_slices:
                    if stop is None:
                        row_vals.append(flat_tuple[start])
                    else:
                        row_vals.append(flat_tuple[start:stop])
                rows.append(row_vals)
        except struct.error as e:
            raise CorruptedFileError(f"Failed to unpack rows via iter_unpack: {e}") from e

        return rows
