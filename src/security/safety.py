"""Filesystem and archive safeguards for untrusted repository inputs."""

from __future__ import annotations

import ntpath
import os
import re
import shutil
import zipfile
from pathlib import Path, PurePosixPath


class SecurityValidationError(ValueError):
    pass


MAX_UPLOAD_SIZE = int(os.environ.get("MAX_UPLOAD_SIZE", str(50 * 1024 * 1024)))
MAX_ARCHIVE_FILES = int(os.environ.get("MAX_ARCHIVE_FILES", "5000"))
MAX_EXTRACTED_SIZE = int(os.environ.get("MAX_EXTRACTED_SIZE", str(500 * 1024 * 1024)))
MAX_UPLOAD_FILES = int(os.environ.get("MAX_UPLOAD_FILES", "10000"))
_SAFE_REPOSITORY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def validate_repository_id(value: str) -> str:
    if not isinstance(value, str) or not _SAFE_REPOSITORY_ID.fullmatch(value):
        raise SecurityValidationError("Invalid repository identifier.")
    return value


def validate_artifact_id(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 255 or "\x00" in value or "/" in value or "\\" in value:
        raise SecurityValidationError("Invalid artifact identifier.")
    return value


def safe_join(root: str | Path, relative_path: str | Path) -> Path:
    """Resolve a user-controlled relative path and keep it under ``root``."""
    if not isinstance(relative_path, (str, Path)) or not str(relative_path).strip():
        raise SecurityValidationError("A filename is required.")
    raw = str(relative_path).replace("\\", "/")
    pure = PurePosixPath(raw)
    if pure.is_absolute() or ntpath.isabs(raw) or any(part in {"", ".."} for part in pure.parts):
        raise SecurityValidationError("Unsafe filename or path.")
    if any(":" in part for part in pure.parts):
        raise SecurityValidationError("Unsafe filename or path.")
    base = Path(root).resolve()
    target = (base / Path(*pure.parts)).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise SecurityValidationError("Unsafe filename or path.") from exc
    return target


def safe_upload_path(root: str | Path, requested_path: str | None, filename: str | None) -> Path:
    candidate = requested_path or filename
    if not filename or not os.path.basename(filename):
        raise SecurityValidationError("Upload filename is missing.")
    return safe_join(root, candidate)


def _zip_member_path(destination: Path, member: zipfile.ZipInfo) -> Path:
    name = member.filename.replace("\\", "/")
    if not name or "\x00" in name:
        raise SecurityValidationError("Archive contains an invalid entry.")
    # ZIP symlinks are encoded in Unix external attributes. Reject them; a
    # source repository has no reason to contain an extracted symlink.
    mode = (member.external_attr >> 16) & 0o170000
    if mode == 0o120000:
        raise SecurityValidationError("Archive contains a symbolic-link entry.")
    return safe_join(destination, name)


def safe_extract_zip(archive_path: str | Path, destination: str | Path) -> list[Path]:
    """Validate all ZIP entries before extraction; never call ``extractall``."""
    destination_path = Path(destination).resolve()
    destination_path.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            members = archive.infolist()
            if not members:
                raise SecurityValidationError("Archive is empty.")
            if len(members) > MAX_ARCHIVE_FILES:
                raise SecurityValidationError("Archive contains too many files.")
            total_size = sum(member.file_size for member in members if not member.is_dir())
            if total_size > MAX_EXTRACTED_SIZE:
                raise SecurityValidationError("Archive expands beyond the allowed size.")
            targets = [(member, _zip_member_path(destination_path, member)) for member in members]
            extracted = []
            for member, target in targets:
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member, "r") as source, open(target, "wb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                extracted.append(target)
            return extracted
    except zipfile.BadZipFile as exc:
        raise SecurityValidationError("Uploaded archive is not a valid ZIP file.") from exc


def count_files(root: str | Path) -> int:
    return sum(1 for path in Path(root).rglob("*") if path.is_file())
