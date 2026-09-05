"""Request schemas and public limits for the UI bridge."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_FILES = 40
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_BATCH_BYTES = 100 * 1024 * 1024
MAX_PATH_DEPTH = 12
MAX_EVENTS = 100

PDF_CONTENT_TYPE = "application/pdf"
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ManifestFile(BaseModel):
    """One browser-selected file, paired positionally with one multipart file."""

    model_config = ConfigDict(extra="forbid", strict=True)

    client_file_id: str = Field(min_length=1, max_length=128)
    relative_path: str = Field(min_length=1, max_length=1024)
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int
    content_type: str = Field(min_length=1, max_length=200)
    selection_status: Literal["SELECTED"]
    purpose: Literal["SOURCE", "REFERENCE"]

    @field_validator("client_file_id", "relative_path", "filename", "content_type")
    @classmethod
    def no_surrounding_whitespace(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("must not have leading or trailing whitespace")
        return value


class JobManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    profile_id: str = Field(min_length=1, max_length=128)
    case_name: str = Field(min_length=1, max_length=200)
    files: list[ManifestFile]

    @field_validator("profile_id", "case_name")
    @classmethod
    def no_surrounding_whitespace(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("must not have leading or trailing whitespace")
        return value


class ReviewPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    review_status: Literal["UNREVIEWED", "REVIEWED", "NEEDS_FOLLOW_UP"]
