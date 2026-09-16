"""
HCAD Column Definition and Struct Handling.
"""
import struct
from typing import Any, Tuple, Union
from .exceptions import SchemaMismatchError


class Column:
    """
    Represents a column in an HCAD table.
    
    Attributes:
        id: Integer column identifier (0 to 65535).
        descriptor: Python struct format string (e.g., 'H', 'H h H', 'c i', '10s').
        byte_size: Size in bytes required by this column per row.
        struct_obj: Pre-compiled struct.Struct object for fast packing/unpacking.
        field_count: Number of unpacked values expected by this descriptor.
    """

    def __init__(self, col_id: int, descriptor: str, max_descriptor_size: int = 65535):
        if not isinstance(col_id, int) or col_id < 0 or col_id > 65535:
            raise SchemaMismatchError(f"Column ID must be an integer between 0 and 65535, got {col_id!r}")

        if not isinstance(descriptor, str):
            raise SchemaMismatchError(f"Column descriptor must be a string, got {type(descriptor).__name__}")

        # Normalize descriptor: strip outer whitespace, check for disallowed endian prefixes
        norm_desc = descriptor.strip()
        if not norm_desc:
            raise SchemaMismatchError(f"Column {col_id} descriptor cannot be empty.")

        # Disallow explicit endianness characters that conflict with standard little-endian '<'
        if norm_desc[0] in ('@', '=', '<', '>', '!'):
            # Strip if leading '<' was passed, otherwise reject ambiguous endianness
            if norm_desc.startswith('<'):
                norm_desc = norm_desc[1:].strip()
            else:
                raise SchemaMismatchError(
                    f"Column {col_id} descriptor '{descriptor}' specifies byte order '{norm_desc[0]}'. "
                    f"HCAD enforces standard little-endian '<' format."
                )

        encoded_desc = norm_desc.encode('utf-8')
        if len(encoded_desc) > max_descriptor_size:
            raise SchemaMismatchError(
                f"Column {col_id} descriptor '{norm_desc}' exceeds maximum allowed size "
                f"of {max_descriptor_size} bytes (got {len(encoded_desc)} bytes)."
            )

        # Validate that format is recognized by struct
        fmt = '<' + norm_desc
        try:
            compiled = struct.Struct(fmt)
            size = compiled.size
        except struct.error as e:
            raise SchemaMismatchError(f"Column {col_id} descriptor '{norm_desc}' is not a valid struct format: {e}")

        if size <= 0:
            raise SchemaMismatchError(f"Column {col_id} descriptor '{norm_desc}' evaluates to 0 bytes.")

        # Test dummy unpack to determine how many fields are packed/unpacked
        dummy_bytes = b'\x00' * size
        unpacked_dummy = compiled.unpack(dummy_bytes)

        self.id = col_id
        self.descriptor = norm_desc
        self.byte_size = size
        self.struct_obj = compiled
        self.field_count = len(unpacked_dummy)

    def pack(self, value: Any) -> bytes:
        """
        Packs a Python value or tuple/list of values into binary bytes.
        """
        try:
            if self.field_count == 1:
                # If a single field expects bytes/chars (e.g. 's' or 'c') and user passed str, encode it
                if isinstance(value, str):
                    value = value.encode('utf-8')
                return self.struct_obj.pack(value)
            else:
                if isinstance(value, (list, tuple)):
                    if len(value) != self.field_count:
                        raise SchemaMismatchError(
                            f"Column {self.id} ('{self.descriptor}') expects {self.field_count} values, got {len(value)}."
                        )
                    # Convert any nested str to bytes if necessary
                    processed = []
                    for v in value:
                        if isinstance(v, str):
                            v = v.encode('utf-8')
                        processed.append(v)
                    return self.struct_obj.pack(*processed)
                else:
                    raise SchemaMismatchError(
                        f"Column {self.id} ('{self.descriptor}') expects a sequence of {self.field_count} values."
                    )
        except (struct.error, TypeError) as e:
            raise SchemaMismatchError(
                f"Failed to pack value {value!r} for column {self.id} ('{self.descriptor}'): {e}"
            ) from e

    def unpack(self, raw_bytes: bytes) -> Any:
        """
        Unpacks binary bytes into a single value or tuple of values.
        """
        try:
            unpacked = self.struct_obj.unpack(raw_bytes)
            return unpacked[0] if self.field_count == 1 else unpacked
        except struct.error as e:
            raise SchemaMismatchError(
                f"Failed to unpack bytes for column {self.id} ('{self.descriptor}'): {e}"
            ) from e

    def to_bytes(self) -> bytes:
        """
        Encodes this column's metadata into bytes:
        uint16 column_id + uint16 descriptor_length + UTF-8 descriptor
        """
        encoded = self.descriptor.encode('utf-8')
        return struct.pack('<H H', self.id, len(encoded)) + encoded

    @classmethod
    def from_stream(cls, stream, max_descriptor_size: int = 65535) -> 'Column':
        """
        Reads a column definition from an open binary stream.
        """
        prefix = stream.read(4)
        if len(prefix) < 4:
            raise CorruptedFileError("Unexpected EOF while reading column definition header.")
        col_id, desc_len = struct.unpack('<H H', prefix)

        if desc_len > max_descriptor_size:
            raise CorruptedFileError(
                f"Column {col_id} descriptor length ({desc_len}) exceeds max allowed size ({max_descriptor_size})."
            )

        desc_bytes = stream.read(desc_len)
        if len(desc_bytes) < desc_len:
            raise CorruptedFileError(f"Unexpected EOF while reading descriptor bytes for column {col_id}.")

        try:
            desc_str = desc_bytes.decode('utf-8')
        except UnicodeDecodeError as e:
            raise CorruptedFileError(f"Invalid UTF-8 descriptor string for column {col_id}: {e}")

        return cls(col_id, desc_str, max_descriptor_size)

    def __repr__(self) -> str:
        return f"Column(id={self.id}, descriptor='{self.descriptor}', byte_size={self.byte_size})"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Column):
            return False
        return self.id == other.id and self.descriptor == other.descriptor
