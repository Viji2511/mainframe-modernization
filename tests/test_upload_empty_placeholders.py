import asyncio
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile

import api.main as api_main


def _upload(name: str, content: bytes) -> UploadFile:
    return UploadFile(filename=name, file=BytesIO(content))


def test_upload_ignores_empty_repository_placeholders_but_keeps_real_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(api_main, "UPLOAD_BASE_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(api_main, "OUTPUT_BASE_DIR", str(tmp_path / "outputs"))

    result = asyncio.run(api_main.upload_files(
        files=[_upload(".gitkeep", b""), _upload("PROGRAM.cbl", b"       IDENTIFICATION DIVISION.\n")],
        paths=["app/cpy-bms/.gitkeep", "app/cbl/PROGRAM.cbl"],
    ))

    assert result["file_count"] == 1
    assert result["skipped_empty_files"] == 1
    stored = tmp_path / "uploads" / result["job_id"] / "app" / "cbl" / "PROGRAM.cbl"
    assert stored.read_text(encoding="utf-8").startswith("       IDENTIFICATION")


def test_upload_rejects_an_all_empty_selection(tmp_path, monkeypatch):
    monkeypatch.setattr(api_main, "UPLOAD_BASE_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(api_main, "OUTPUT_BASE_DIR", str(tmp_path / "outputs"))

    with pytest.raises(HTTPException) as rejected:
        asyncio.run(api_main.upload_files(files=[_upload(".gitkeep", b"")], paths=["repo/.gitkeep"]))

    assert rejected.value.status_code == 400
    assert rejected.value.detail == "Upload rejected."
