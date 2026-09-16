"""
HCAD Header parsing, packing, and validation.
"""
import struct
from dataclasses import dataclass
from typing import Tuple

from .constants import (
    IDENTIFIER,
    CURRENT_VERSION,
    VERSION_1,
    COMPRESSION_NONE,
    COMPRESSION_ZLIB,
    SUPPORTED_COMPRESSIONS,
    HEADER_FORMAT_V2,
    HEADER_SIZE_V2,
    HEADER_FORMAT_V1,
    HEADER_SIZE_V1,
    DEFAULT_MAX_DESCRIPTOR_SIZE,
)
from .exceptions import (
    InvalidHeaderError,
    UnsupportedVersionError,
    UnsupportedCompressionError,
)


@dataclass
class Header:
    column_count: int
    max_descriptor_size: int = DEFAULT_MAX_DESCRIPTOR_SIZE
    version: int = CURRENT_VERSION
    compression: int = COMPRESSION_NONE
    row_count: int = 0
    identifier: bytes = IDENTIFIER

    def __post_init__(self):
        self.validate()

    def validate(self) -> None:
        if self.identifier != IDENTIFIER:
            raise InvalidHeaderError(f"Invalid HCAD identifier signature: {self.identifier!r}")

        if self.version != CURRENT_VERSION:
            raise UnsupportedVersionError(f"Unsupported HCAD version: {self.version}")

        if self.compression not in SUPPORTED_COMPRESSIONS:
            raise UnsupportedCompressionError(f"Unsupported compression flag: {self.compression}")

        if not (0 <= self.column_count <= 65535):
            raise InvalidHeaderError(f"Column count must be between 0 and 65535, got {self.column_count}")

        if not (1 <= self.max_descriptor_size <= 65535):
            raise InvalidHeaderError(
                f"Max column descriptor size must be between 1 and 65535, got {self.max_descriptor_size}"
            )

        if not (0 <= self.row_count <= 4294967295):
            raise InvalidHeaderError(f"Row count must be between 0 and 4294967295, got {self.row_count}")

    def pack(self) -> bytes:
        """
        Packs the header into 20 bytes:
        <8s (identifier) H (column_count) H (max_descriptor_size) H (version) H (compression) I (row_count)
        """
        self.validate()
        return struct.pack(
            HEADER_FORMAT_V2,
            self.identifier,
            self.column_count,
            self.max_descriptor_size,
            self.version,
            self.compression,
            self.row_count,
        )

    @classmethod
    def from_stream(cls, stream) -> Tuple['Header', int]:
        """
        Reads and parses the header from an open binary stream.
        Returns:
            (Header, header_size_in_bytes)
        """
        raw = stream.read(HEADER_SIZE_V2)
        if len(raw) < HEADER_SIZE_V1:
            raise InvalidHeaderError("File size is smaller than the minimum HCAD header size.")

        # Check signature first 8 bytes
        ident = raw[:8]
        if ident != IDENTIFIER:
            raise InvalidHeaderError(f"Invalid HCAD file: identifier mismatch ({ident!r}).")

        if len(raw) >= HEADER_SIZE_V2:
            # Try V2 unpack
            ident, col_count, max_desc, ver, comp, row_cnt = struct.unpack(HEADER_FORMAT_V2, raw[:HEADER_SIZE_V2])
            # If version is valid V2
            if ver == CURRENT_VERSION and comp in SUPPORTED_COMPRESSIONS:
                header = cls(
                    identifier=ident,
                    column_count=col_count,
                    max_descriptor_size=max_desc,
                    version=ver,
                    compression=comp,
                    row_count=row_cnt,
                )
                return header, HEADER_SIZE_V2

        # Fallback to V1 format (16 bytes) if header is 16 bytes or doesn't match V2
        stream.seek(0)
        v1_raw = stream.read(HEADER_SIZE_V1)
        ident, col_count, ver, comp, max_desc = struct.unpack(HEADER_FORMAT_V1, v1_raw)
        header = cls(
            identifier=ident,
            column_count=col_count,
            max_descriptor_size=max_desc,
            version=ver,
            compression=comp,
            row_count=0,  # V1 did not store row count
        )
        return header, HEADER_SIZE_V1
