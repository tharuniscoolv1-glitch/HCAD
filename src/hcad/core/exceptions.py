"""
HCAD Exception hierarchy.
"""

class HCADError(Exception):
    """Base exception for all HCAD-related errors."""
    pass


class InvalidHeaderError(HCADError, ValueError):
    """Raised when file header fails validation or has an invalid signature."""
    pass


class CorruptedFileError(HCADError, ValueError):
    """Raised when file payload or descriptors are corrupted or truncated."""
    pass


class SchemaMismatchError(HCADError, ValueError):
    """Raised when data columns/types do not match the expected HCAD schema."""
    pass


class UnsupportedVersionError(HCADError, ValueError):
    """Raised when the HCAD file version is not supported."""
    pass


class UnsupportedCompressionError(HCADError, ValueError):
    """Raised when the compression format is unknown or unsupported."""
    pass
