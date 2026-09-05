"""ATLAS contracts, synthetic fixtures, and source normalization."""

from .ingestion import IngestionError, detect_document_role, normalize_file
from .models import NormalizedDocument, ReviewSnapshot

__all__ = [
    "IngestionError",
    "NormalizedDocument",
    "ReviewSnapshot",
    "detect_document_role",
    "normalize_file",
]
