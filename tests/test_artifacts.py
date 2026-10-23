import io
import zipfile

import pytest

from app.db.enums import ArtifactStatus
from app.db.models import Artifact
from tests.conftest import as_user, file_part, submit


def make_zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for n, c in files.items():
            zf.writestr(n, c)
    return buf.getvalue()


def test_clean_upload_goes_to_review_and_is_private_until_approved(client, employee, reviewer):
    r = submit(client, employee, file_part())
    assert r.status_code == 202
    a = r.json()
    assert a["status"] == "pending_review" and a["scan_result"]["antivirus"]["status"] == "not_configured"
    assert a["scan_result"]["blocked"] is False and len(a["sha256"]) == 64
    other = as_user("other@neuleap.ai")
    assert client.get(f"/api/v1/artifacts/{a['id']}", headers=other).status_code == 404
    assert client.get(f"/api/v1/artifacts/{a['id']}/download", headers=other).status_code == 404
    assert client.get("/api/v1/library", headers=other).json()["total"] == 0
    assert client.get(f"/api/v1/artifacts/{a['id']}/download", headers=employee).content == b"# My findings\nAll good.\n"
    assert client.post(f"/api/v1/artifacts/{a['id']}/approve", json={}, headers=reviewer).status_code == 200
    lib = client.get("/api/v1/library", headers=other).json()
    assert lib["total"] == 1 and "scan_result" not in lib["items"][0]
    assert client.get(f"/api/v1/artifacts/{a['id']}/download", headers=other).status_code == 200
    assert "scan_result" not in client.get(f"/api/v1/artifacts/{a['id']}", headers=other).json()


def test_secret_is_quarantined_cannot_be_approved_and_can_be_replaced(client, employee, reviewer, admin, db):
    bad = make_zip({"app.py": "aws_key = 'AKIAABCDEFGHIJKLMNOP'\n"})
    r = submit(client, employee, {"file": ("poc.zip", bad, "application/zip")})
    a = r.json()
    assert a["status"] == "quarantined"
    assert "AKIAABCDEFGHIJKLMNOP" not in r.text
    assert client.post(f"/api/v1/artifacts/{a['id']}/approve", json={}, headers=admin).status_code == 409
    q = client.get("/api/v1/moderation/artifacts?status=quarantined", headers=reviewer).json()
    assert q["total"] == 1
    assert client.put(f"/api/v1/artifacts/{a['id']}/file", files=file_part("poc.md", b"# clean"), headers=as_user("other@neuleap.ai")).status_code == 404
    rep = client.put(f"/api/v1/artifacts/{a['id']}/file", files=file_part("poc.md", b"# clean"), headers=employee)
    assert rep.status_code == 202 and rep.json()["status"] == "pending_review" and rep.json()["version"] == 2
    assert client.post(f"/api/v1/artifacts/{a['id']}/approve", json={}, headers=admin).status_code == 200
    assert client.put(f"/api/v1/artifacts/{a['id']}/file", files=file_part(), headers=employee).status_code == 409


def test_client_name_is_blocked(client, employee):
    r = submit(client, employee, file_part("n.md", b"Built for AcmeCorp last quarter"))
    assert r.json()["status"] == "quarantined"
    assert any(f["kind"] == "client_name" for f in r.json()["scan_result"]["findings"])


@pytest.mark.parametrize("name,content", [("run.exe", b"MZ\x90\x00"), ("x.pdf", b"MZ\x90\x00"), ("x.sh", b"#!/bin/sh\nrm -rf /"),
                                          ("x.zip", b"%PDF-1.4"), ("empty.md", b"")])
def test_dangerous_uploads_rejected_at_the_door(client, employee, db, name, content):
    r = submit(client, employee, {"file": (name, content, "application/octet-stream")})
    assert r.status_code == 422, r.text
    assert db.query(Artifact).count() == 0


def test_zip_with_executable_or_traversal_is_quarantined(client, employee):
    for files in ({"run.exe": "MZ"}, {"../../evil.txt": "x"}):
        r = submit(client, employee, {"file": ("a.zip", make_zip(files), "application/zip")})
        assert r.json()["status"] == "quarantined", files


def test_oversized_upload_rejected(client, employee, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 100)
    r = submit(client, employee, file_part("big.md", b"x" * 500))
    assert r.status_code == 413


def test_link_only_submission_is_marked_not_scanned(client, employee):
    r = submit(client, employee, None, repo_url="https://github.com/org/repo")
    assert r.status_code == 202 and r.json()["status"] == "pending_review"
    assert "not fetched" in r.json()["scan_result"]["note"]
    assert submit(client, employee, None, repo_url="http://10.0.0.1/repo").status_code == 422
    assert submit(client, employee, None).status_code == 422


def test_cannot_submit_to_topic_you_are_not_on_or_someone_elses_assignment(client, employee, make_topic):
    t = make_topic()
    assert submit(client, employee, file_part(), topic_id=str(t.id)).status_code == 403
    other = as_user("other@neuleap.ai")
    client.post(f"/api/v1/topics/{t.id}/volunteer", headers=other)
    aid = client.get("/api/v1/me/assignments", headers=other).json()[0]["id"]
    assert submit(client, employee, file_part(), assignment_id=aid).status_code == 404
    assert submit(client, other, file_part(), assignment_id=aid).status_code == 202


def test_moderator_cannot_review_own_artifact_and_reject_flow(client, reviewer, employee):
    own = submit(client, reviewer, file_part()).json()
    assert client.post(f"/api/v1/artifacts/{own['id']}/approve", json={}, headers=reviewer).status_code == 403
    a = submit(client, employee, file_part()).json()
    assert client.post(f"/api/v1/artifacts/{a['id']}/reject", json={"reason": "x"}, headers=reviewer).status_code == 422
    r = client.post(f"/api/v1/artifacts/{a['id']}/reject", json={"reason": "Missing README"}, headers=reviewer)
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    mine = client.get("/api/v1/artifacts/mine", headers=employee).json()
    assert mine["items"][0]["rejection_reason"] == "Missing README"
    assert client.post(f"/api/v1/artifacts/{a['id']}/approve", json={}, headers=reviewer).status_code == 409
    rep = client.put(f"/api/v1/artifacts/{a['id']}/file", files=file_part("v2.md", b"# readme"), headers=employee)
    assert rep.json()["status"] == "pending_review"


def test_moderation_endpoints_forbidden_for_employees(client, employee):
    a = submit(client, employee, file_part()).json()
    assert client.get("/api/v1/moderation/artifacts", headers=employee).status_code == 403
    assert client.post(f"/api/v1/artifacts/{a['id']}/quarantine", json={"reason": "abc"}, headers=employee).status_code == 403


def test_scan_is_idempotent(db, client, employee):
    from app.services.artifacts import process_scan
    a = submit(client, employee, file_part()).json()
    import uuid
    assert process_scan(db, uuid.UUID(a["id"])) is None  # already scanned: second delivery does nothing
    assert db.get(Artifact, uuid.UUID(a["id"])).status == ArtifactStatus.PENDING_REVIEW


def test_path_traversal_in_filename_is_neutralised(client, employee, db):
    r = submit(client, employee, {"file": ("../../../etc/passwd.md", b"# hi", "text/plain")})
    assert r.status_code == 202 and r.json()["filename"] == "passwd.md"
    from app.storage.local import LocalStorage
    import pytest as _p
    with _p.raises(ValueError):
        LocalStorage().path_for("../outside.txt")
    with _p.raises(ValueError):
        LocalStorage().path_for("/etc/passwd")


def test_declared_oversized_request_is_refused_before_parsing(client, employee):
    import httpx
    r = client.post("/api/v1/artifacts", headers={**employee, "Content-Length": "999999999999", "Content-Type": "multipart/form-data; boundary=x"},
                    content=b"--x--")
    assert r.status_code == 413
