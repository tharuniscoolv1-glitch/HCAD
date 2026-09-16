"""
HCAD File Engine: High-level I/O, transactional modifications, streaming, and compression.
"""
import os
import struct
import tempfile
import zlib
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Union

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
    Supports O(1) in-place mutations, bounded-memory streaming, and random access.
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

        col_bytes = bytearray()
        for col in columns:
            col_bytes.extend(col.to_bytes())

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

    def read_row(self, row_idx: int) -> List[Any]:
        """
        Reads a single row by index.
        For uncompressed files, executes in O(1) time via direct binary seek.
        """
        if self.header is None or self._codec is None:
            self.load_metadata()

        if not (0 <= row_idx < self.header.row_count):
            raise IndexError(f"Row index {row_idx} out of range (0..{self.header.row_count - 1}).")

        if self.header.compression == COMPRESSION_NONE:
            target_pos = self.data_offset + (row_idx * self.row_byte_size)
            with open(self.file_path, 'rb') as f:
                f.seek(target_pos)
                raw_row = f.read(self.row_byte_size)
            if len(raw_row) < self.row_byte_size:
                raise CorruptedFileError(f"Unexpected EOF while reading row {row_idx}.")
            return self._codec.decode_single_row(raw_row)
        else:
            return self.read().get_row(row_idx)

    def read_range(self, start_idx: int, end_idx: int) -> Table:
        """
        Reads a slice of rows [start_idx:end_idx] from the file.
        For uncompressed files, reads only the requested byte slice from disk.
        """
        if self.header is None or self._codec is None:
            self.load_metadata()

        total_rows = self.header.row_count
        start = max(0, start_idx)
        end = min(total_rows, end_idx)
        if start >= end:
            return Table(self.columns, [])

        num_rows = end - start
        if self.header.compression == COMPRESSION_NONE:
            target_pos = self.data_offset + (start * self.row_byte_size)
            bytes_to_read = num_rows * self.row_byte_size
            with open(self.file_path, 'rb') as f:
                f.seek(target_pos)
                raw_slice = f.read(bytes_to_read)
            rows = self._codec.decode_rows(raw_slice, expected_row_count=num_rows)
            return Table(self.columns, rows)
        else:
            table = self.read()
            return Table(self.columns, table.rows[start:end])

    def iter_rows(self, batch_size: int = 1024) -> Iterator[List[Any]]:
        """
        Streams rows from the file with bounded memory usage.
        For uncompressed files, streams in batches from disk without loading the entire file into RAM.
        """
        if self.header is None or self._codec is None:
            self.load_metadata()

        if batch_size <= 0:
            raise ValueError(f"batch_size must be positive, got {batch_size}")

        if self.header.compression == COMPRESSION_NONE:
            if self.header.row_count == 0:
                return

            remaining_rows = self.header.row_count
            with open(self.file_path, 'rb') as f:
                f.seek(self.data_offset)
                while remaining_rows > 0:
                    rows_to_read = min(batch_size, remaining_rows)
                    raw_batch = f.read(rows_to_read * self.row_byte_size)
                    if len(raw_batch) < rows_to_read * self.row_byte_size:
                        raise CorruptedFileError("Unexpected EOF while streaming rows.")
                    decoded_rows = self._codec.decode_rows(raw_batch, expected_row_count=rows_to_read)
                    for row in decoded_rows:
                        yield row
                    remaining_rows -= rows_to_read
        else:
            table = self.read()
            for row in table.rows:
                yield row

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

    def append_row(self, row: Union[Sequence[Any], Dict[int, Any]], sync: bool = False) -> None:
        self.append_rows([row], sync=sync)

    def append_rows(
        self, rows: Sequence[Union[Sequence[Any], Dict[int, Any]]], sync: bool = False
    ) -> None:
        """
        Appends new rows to the file.
        In uncompressed mode, this performs an O(1) in-place file append.
        """
        if not rows:
            return

        if self.header is None or self._codec is None:
            self.load_metadata()

        table = Table(self.columns)
        table.add_rows(rows)
        new_bytes = self._codec.encode_rows(table.rows)
        added_count = len(table.rows)

        if self.header.compression == COMPRESSION_NONE:
            with open(self.file_path, 'r+b') as f:
                f.seek(0, os.SEEK_END)
                f.write(new_bytes)
                self.header.row_count += added_count
                f.seek(0)
                f.write(self.header.pack())
                if sync:
                    f.flush()
                    os.fsync(f.fileno())
        elif self.header.compression == COMPRESSION_ZLIB:
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

    def update_cell(
        self, row_idx: int, col_id_or_idx: int, value: Any, sync: bool = False
    ) -> None:
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
            target_pos = self.data_offset + (row_idx * self.row_byte_size) + col_offset_in_row
            with open(self.file_path, 'r+b') as f:
                f.seek(target_pos)
                f.write(val_bytes)
                if sync:
                    f.flush()
                    os.fsync(f.fileno())
        else:
            table = self.read()
            table.update_cell(row_idx, col_idx, value)
            self.write(table)

    def delete_row(self, row_idx: int, sync: bool = False) -> None:
        """
        Deletes a specific row by index.
        For uncompressed files, intermediate rows are shifted backward in 64 KB binary chunks
        and the file is truncated in-place, using strictly O(1) memory.
        """
        if self.header is None or self._codec is None:
            self.load_metadata()

        if not (0 <= row_idx < self.header.row_count):
            raise IndexError(f"Row index {row_idx} out of range (0..{self.header.row_count - 1}).")

        if self.header.compression == COMPRESSION_NONE:
            # If deleting the terminal row: instant truncation
            if row_idx == self.header.row_count - 1:
                new_file_size = self.data_offset + ((self.header.row_count - 1) * self.row_byte_size)
                with open(self.file_path, 'r+b') as f:
                    f.truncate(new_file_size)
                    self.header.row_count -= 1
                    f.seek(0)
                    f.write(self.header.pack())
                    if sync:
                        f.flush()
                        os.fsync(f.fileno())
                return

            # Intermediate row: shift subsequent bytes backward in 64 KB binary chunks
            chunk_size = 65536
            chunk_rows = max(1, chunk_size // self.row_byte_size)
            buffer_size = chunk_rows * self.row_byte_size

            dst_pos = self.data_offset + (row_idx * self.row_byte_size)
            src_pos = dst_pos + self.row_byte_size
            total_data_bytes = self.header.row_count * self.row_byte_size
            end_pos = self.data_offset + total_data_bytes

            with open(self.file_path, 'r+b') as f:
                while src_pos < end_pos:
                    bytes_to_read = min(buffer_size, end_pos - src_pos)
                    f.seek(src_pos)
                    chunk = f.read(bytes_to_read)
                    f.seek(dst_pos)
                    f.write(chunk)
                    src_pos += len(chunk)
                    dst_pos += len(chunk)

                new_size = self.data_offset + ((self.header.row_count - 1) * self.row_byte_size)
                f.truncate(new_size)
                self.header.row_count -= 1
                f.seek(0)
                f.write(self.header.pack())
                if sync:
                    f.flush()
                    os.fsync(f.fileno())
            return

        # For compressed files, rewrite payload atomically
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

    def to_csv(
        self,
        file_path: Union[str, Path],
        header: Optional[Sequence[str]] = None,
        write_header: bool = True,
        encoding: str = "utf-8",
    ) -> None:
        """
        Exports all rows to a CSV file.
        For uncompressed files, streams rows in bounded batches with constant memory usage.
        """
        import csv
        from ..core.table import _format_cell_for_csv

        if self.header is None or self._codec is None:
            self.load_metadata()

        col_names = list(header) if header is not None else [f"col_{c.id}" for c in self.columns]
        with open(file_path, 'w', newline='', encoding=encoding) as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(col_names)

            for row in self.iter_rows(batch_size=1024):
                formatted = [_format_cell_for_csv(v) for v in row]
                writer.writerow(formatted)

    def to_json(
        self,
        file_path: Optional[Union[str, Path]] = None,
        orient: str = "records",
        indent: Optional[int] = None,
    ) -> str:
        """
        Exports file contents to JSON.
        """
        table = self.read()
        return table.to_json(file_path=file_path, orient=orient, indent=indent)

    @classmethod
    def from_csv(
        cls,
        file_path: Union[str, Path],
        csv_path: Union[str, Path],
        columns: Sequence[Column],
        has_header: bool = True,
        compression: int = COMPRESSION_NONE,
        overwrite: bool = True,
    ) -> 'HCADFile':
        """
        Creates an HCAD file from a CSV file.
        """
        table = Table.from_csv(csv_path, columns, has_header=has_header)
        hfile = cls.create(file_path, columns, compression=compression, overwrite=overwrite)
        hfile.write(table)
        return hfile

    @classmethod
    def from_json(
        cls,
        file_path: Union[str, Path],
        json_path_or_str: Union[str, Path],
        columns: Optional[Sequence[Column]] = None,
        orient: str = "auto",
        compression: int = COMPRESSION_NONE,
        overwrite: bool = True,
    ) -> 'HCADFile':
        """
        Creates an HCAD file from a JSON file or JSON string.
        """
        table = Table.from_json(json_path_or_str, columns=columns, orient=orient)
        hfile = cls.create(file_path, table.columns, compression=compression, overwrite=overwrite)
        hfile.write(table)
        return hfile

    def __enter__(self) -> 'HCADFile':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

