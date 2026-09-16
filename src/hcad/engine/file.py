"""
HCAD File Engine: High-level I/O, transactional modifications, and compression.
"""
import os
import struct
import tempfile
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from ..core.constants import (
    COMPRESSION_NONE,
    COMPRESSION_ZLIB,
    CURRENT_VERSION,
    DEFAULT_MAX_DESCRIPTOR_SIZE,
    HEADER_SIZE_V2,
    IDENTIFIER,
)
from ..core.column import Column
from ..core.header import Header
from ..core.table import Table
from ..core.exceptions import (
    CorruptedFileError,
    HCADError,
    InvalidHeaderError,
    SchemaMismatchError,
    UnsupportedCompressionError,
)
from .codec import RowCodec


class HCADFile:
    """
    Manages an HCAD binary file on disk.
    """

    def __init__(self, file_path: Union[str, Path]):
        self.file_path = Path(file_path).resolve()
        self.header: Optional[Header] = None
        self.columns: List[Column] = []
        self.data_offset: int = 0
        self._codec: Optional[RowCodec] = None

    @classmethod
    def create(
        cls,
        file_path: Union[str, Path],
        columns: Sequence[Column],
        max_descriptor_size: int = DEFAULT_MAX_DESCRIPTOR_SIZE,
        compression: int = COMPRESSION_NONE,
        overwrite: bool = True,
    ) -> 'HCADFile':
        """
        Creates a new HCAD file on disk with the specified schema.
        """
        target = Path(file_path).resolve()
        if not overwrite and target.exists():
            raise FileExistsError(f"HCAD file '{target}' already exists.")

        target.parent.mkdir(parents=True, exist_ok=True)

        header = Header(
            column_count=len(columns),
            max_descriptor_size=max_descriptor_size,
            version=CURRENT_VERSION,
            compression=compression,
            row_count=0,
        )

        # Pre-validate columns against max_descriptor_size
        col_bytes = bytearray()
        for col in columns:
            col_bytes.extend(col.to_bytes())

        # Atomic create via tempfile
        dir_name = target.parent
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='wb', dir=dir_name, delete=False) as tmp_file:
                tmp_path = Path(tmp_file.name)
                tmp_file.write(header.pack())
                tmp_file.write(col_bytes)
            os.replace(tmp_path, target)
            tmp_path = None
        finally:
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

        instance = cls(target)
        instance.load_metadata()
        return instance

    @classmethod
    def open(cls, file_path: Union[str, Path]) -> 'HCADFile':
        """
        Opens an existing HCAD file and loads its schema metadata.
        """
        instance = cls(file_path)
        instance.load_metadata()
        return instance

    def load_metadata(self) -> None:
        """
        Reads and validates the header and column definitions from the file.
        """
        if not self.file_path.exists():
            raise FileNotFoundError(f"HCAD file not found: {self.file_path}")

        try:
            with open(self.file_path, 'rb') as f:
                self.header, header_size = Header.from_stream(f)
                self.columns = []
                for _ in range(self.header.column_count):
                    col = Column.from_stream(f, self.header.max_descriptor_size)
                    self.columns.append(col)
                self.data_offset = f.tell()
        except (OSError, ValueError) as e:
            if not isinstance(e, HCADError):
                raise InvalidHeaderError(f"Failed to read HCAD metadata from '{self.file_path}': {e}") from e
            raise

        self._codec = RowCodec(self.columns)

    @property
    def is_compressed(self) -> bool:
        if self.header is None:
            self.load_metadata()
        return self.header.compression == COMPRESSION_ZLIB

    @property
    def row_count(self) -> int:
        if self.header is None:
            self.load_metadata()
        return self.header.row_count

    @property
    def row_byte_size(self) -> int:
        if self._codec is None:
            self.load_metadata()
        return self._codec.row_byte_size

    def read(self) -> Table:
        """
        Reads all row data from the HCAD file and returns a Table object.
        """
        if self.header is None or self._codec is None:
            self.load_metadata()

        with open(self.file_path, 'rb') as f:
            f.seek(self.data_offset)
            raw_payload = f.read()

        if self.header.compression == COMPRESSION_NONE:
            rows = self._codec.decode_rows(raw_payload, self.header.row_count)
        elif self.header.compression == COMPRESSION_ZLIB:
            if not raw_payload:
                decompressed = b''
            else:
                try:
                    decompressed = zlib.decompress(raw_payload)
                except zlib.error as e:
                    raise CorruptedFileError(f"Decompression failed for '{self.file_path}': {e}") from e
            rows = self._codec.decode_rows(decompressed, self.header.row_count)
        else:
            raise UnsupportedCompressionError(f"Unsupported compression: {self.header.compression}")

        return Table(self.columns, rows)

    def write(self, table: Table) -> None:
        """
        Overwrites all table data in the HCAD file.
        """
        if self.header is None or self._codec is None:
            self.load_metadata()

        if len(table.columns) != len(self.columns):
            raise SchemaMismatchError("Table schema column count does not match file schema.")

        for c_file, c_tbl in zip(self.columns, table.columns):
            if c_file.id != c_tbl.id or c_file.descriptor != c_tbl.descriptor:
                raise SchemaMismatchError(f"Schema mismatch: {c_file} vs {c_tbl}")

        raw_rows = self._codec.encode_rows(table.rows)
        new_row_count = len(table.rows)

        if self.header.compression == COMPRESSION_ZLIB:
            payload = zlib.compress(raw_rows) if raw_rows else b''
        else:
            payload = raw_rows

        self.header.row_count = new_row_count
        self._atomic_rewrite(payload)

    def append_row(self, row: Union[Sequence[Any], Dict[int, Any]]) -> None:
        self.append_rows([row])

    def append_rows(self, rows: Sequence[Union[Sequence[Any], Dict[int, Any]]]) -> None:
        """
        Appends new rows to the file.
        In uncompressed mode, this performs an O(1) in-place file append.
        """
        if not rows:
            return

        if self.header is None or self._codec is None:
            self.load_metadata()

        # Format rows into standard list of values
        table = Table(self.columns)
        table.add_rows(rows)
        new_bytes = self._codec.encode_rows(table.rows)
        added_count = len(table.rows)

        if self.header.compression == COMPRESSION_NONE:
            # Direct in-place append
            with open(self.file_path, 'r+b') as f:
                f.seek(0, os.SEEK_END)
                f.write(new_bytes)
                # Update row count in header
                self.header.row_count += added_count
                f.seek(0)
                f.write(self.header.pack())
        elif self.header.compression == COMPRESSION_ZLIB:
            # Decompress, merge, recompress
            with open(self.file_path, 'rb') as f:
                f.seek(self.data_offset)
                compressed = f.read()

            if compressed:
                try:
                    existing_raw = zlib.decompress(compressed)
                except zlib.error as e:
                    raise CorruptedFileError(f"Decompression error during append: {e}") from e
            else:
                existing_raw = b''

            combined = existing_raw + new_bytes
            new_payload = zlib.compress(combined) if combined else b''
            self.header.row_count += added_count
            self._atomic_rewrite(new_payload)

    def update_cell(self, row_idx: int, col_id_or_idx: int, value: Any) -> None:
        """
        Updates a specific cell in the table.
        In uncompressed mode, this modifies the exact bytes in-place without rewriting the file.
        """
        if self.header is None or self._codec is None:
            self.load_metadata()

        if not (0 <= row_idx < self.header.row_count):
            raise IndexError(f"Row index {row_idx} out of range (0..{self.header.row_count - 1}).")

        col_idx = None
        for idx, col in enumerate(self.columns):
            if col.id == col_id_or_idx or idx == col_id_or_idx:
                col_idx = idx
                target_col = col
                break

        if col_idx is None:
            raise SchemaMismatchError(f"Column {col_id_or_idx} not found in file schema.")

        col_offset_in_row = sum(self.columns[i].byte_size for i in range(col_idx))
        val_bytes = target_col.pack(value)

        if self.header.compression == COMPRESSION_NONE:
            # O(1) in-place seek & write
            target_pos = self.data_offset + (row_idx * self.row_byte_size) + col_offset_in_row
            with open(self.file_path, 'r+b') as f:
                f.seek(target_pos)
                f.write(val_bytes)
        else:
            # Compressed: read table, update, rewrite
            table = self.read()
            table.update_cell(row_idx, col_idx, value)
            self.write(table)

    def delete_row(self, row_idx: int) -> None:
        """
        Deletes a specific row by index.
        """
        if self.header is None or self._codec is None:
            self.load_metadata()

        if not (0 <= row_idx < self.header.row_count):
            raise IndexError(f"Row index {row_idx} out of range (0..{self.header.row_count - 1}).")

        if self.header.compression == COMPRESSION_NONE:
            # If deleting the last row, truncate file directly
            if row_idx == self.header.row_count - 1:
                new_file_size = self.data_offset + ((self.header.row_count - 1) * self.row_byte_size)
                with open(self.file_path, 'r+b') as f:
                    f.truncate(new_file_size)
                    self.header.row_count -= 1
                    f.seek(0)
                    f.write(self.header.pack())
                return

        # For intermediate rows or compressed files, rewrite payload
        table = self.read()
        table.delete_row(row_idx)
        self.write(table)

    def compress(self) -> None:
        """
        Compresses an uncompressed HCAD file in place.
        """
        if self.header is None or self._codec is None:
            self.load_metadata()

        if self.header.compression == COMPRESSION_ZLIB:
            raise ValueError("File is already compressed.")

        with open(self.file_path, 'rb') as f:
            f.seek(self.data_offset)
            raw_data = f.read()

        # Validate raw data integrity before compressing
        expected_bytes = self.header.row_count * self.row_byte_size
        if len(raw_data) != expected_bytes:
            raise CorruptedFileError(
                f"Cannot compress corrupted file: expected {expected_bytes} bytes, got {len(raw_data)} bytes."
            )

        compressed_data = zlib.compress(raw_data) if raw_data else b''
        self.header.compression = COMPRESSION_ZLIB
        self._atomic_rewrite(compressed_data)

    def decompress(self) -> None:
        """
        Decompresses a compressed HCAD file in place.
        """
        if self.header is None or self._codec is None:
            self.load_metadata()

        if self.header.compression == COMPRESSION_NONE:
            raise ValueError("File is not compressed.")

        with open(self.file_path, 'rb') as f:
            f.seek(self.data_offset)
            compressed_data = f.read()

        if compressed_data:
            try:
                raw_data = zlib.decompress(compressed_data)
            except zlib.error as e:
                raise CorruptedFileError(f"Corrupted compressed payload: {e}") from e
        else:
            raw_data = b''

        expected_bytes = self.header.row_count * self.row_byte_size
        if len(raw_data) != expected_bytes:
            raise CorruptedFileError(
                f"Decompressed data size ({len(raw_data)}) does not match expected size ({expected_bytes})."
            )

        self.header.compression = COMPRESSION_NONE
        self._atomic_rewrite(raw_data)

    def _atomic_rewrite(self, new_payload: bytes) -> None:
        """
        Atomically updates the header and data payload using a temporary file.
        Guarantees zero temporary file leakage on disk upon any exception.
        """
        dir_name = self.file_path.parent
        tmp_path = None
        try:
            with open(self.file_path, 'rb') as orig:
                orig.seek(0)
                # Read original column definitions between header and data_offset
                # Note: header size can be 20 (v2) or 16 (v1)
                orig.seek(0)
                _, h_size = Header.from_stream(orig)
                col_def_bytes = orig.read(self.data_offset - h_size)

            with tempfile.NamedTemporaryFile(mode='wb', dir=dir_name, delete=False) as tmp_file:
                tmp_path = Path(tmp_file.name)
                tmp_file.write(self.header.pack())
                tmp_file.write(col_def_bytes)
                tmp_file.write(new_payload)

            os.replace(tmp_path, self.file_path)
            tmp_path = None
            self.load_metadata()
        finally:
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def __enter__(self) -> 'HCADFile':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
