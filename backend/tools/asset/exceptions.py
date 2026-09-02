"""
Exceptions for asset downloading, archive validation, and asset operations.
"""

from __future__ import annotations


class AssetError(Exception):
    """Base exception for asset operations."""


class DownloadError(AssetError):
    """Exception raised when asset download fails."""


class ZipSlipSecurityError(AssetError):
    """Exception raised when archive extraction detects path traversal attempt."""
