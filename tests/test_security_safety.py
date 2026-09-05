import asyncio
import zipfile

import pytest
from fastapi import HTTPException

from api.main import _validated_job_id
from api.repository_api import get_artifact_details, get_summary
from src.agents.repository_discovery import RepositoryDiscoveryAgent
from src.security.safety import SecurityValidationError, safe_extract_zip, safe_join, validate_artifact_id


def _zip(path, members):
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)


def test_zip_path_traversal_and_absolute_entries_are_rejected(tmp_path):
    for name in ("../../outside.txt", "/absolute.txt", r"C:\absolute.txt"):
        archive = tmp_path / f"bad-{len(name)}.zip"
        _zip(archive, {name: "unsafe"})
        with pytest.raises(SecurityValidationError):
            safe_extract_zip(archive, tmp_path / "extract")
    assert not (tmp_path / "outside.txt").exists()


def test_normal_zip_extracts_inside_destination_and_malformed_zip_is_safe(tmp_path):
    archive = tmp_path / "normal.zip"
    _zip(archive, {"repo/PROGRAM.cbl": "IDENTIFICATION DIVISION."})
    extracted = safe_extract_zip(archive, tmp_path / "extract")
    assert extracted[0].read_text(encoding="utf-8") == "IDENTIFICATION DIVISION."
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    with pytest.raises(SecurityValidationError):
        safe_extract_zip(bad, tmp_path / "bad-extract")


def test_safe_path_and_ids_cannot_escape_their_roots(tmp_path):
    assert safe_join(tmp_path, "nested/source.cpy").parent == (tmp_path / "nested").resolve()
    for unsafe in ("../secret", r"..\secret", "/secret", r"C:\secret"):
        with pytest.raises(SecurityValidationError):
            safe_join(tmp_path, unsafe)
    with pytest.raises(HTTPException):
        _validated_job_id("../../outputs")
    with pytest.raises(SecurityValidationError):
        validate_artifact_id("../../.env")


def test_repository_api_rejects_path_identifiers():
    with pytest.raises(HTTPException) as repo_error:
        asyncio.run(get_summary("../../outputs"))
    assert repo_error.value.status_code == 400
    with pytest.raises(HTTPException) as artifact_error:
        asyncio.run(get_artifact_details("valid-repository", "../../.env"))
    assert artifact_error.value.status_code == 400


def test_discovery_handles_binary_source_as_data_without_execution(tmp_path):
    (tmp_path / "program.cbl").write_bytes(b"\x00\xffIDENTIFICATION DIVISION")
    discovered = RepositoryDiscoveryAgent().discover(str(tmp_path))
    assert "program.cbl" in discovered
    # The discovery agent only returns decoded text; it never dispatches a
    # shell command or executes the uploaded member.
    assert "IDENTIFICATION" in discovered["program.cbl"]
