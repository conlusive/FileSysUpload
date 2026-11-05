"""Інтеграційні тести ендпоінтів /files: завантаження, обробка, безпека, пагінація, видалення."""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app
from tests.conftest import (
    image_bytes, login_headers, make_settings, pdf_bytes, register, storage_files, tmp_files, upload,
)


# ---------- успішні сценарії ----------

def test_upload_jpeg_creates_variants_and_metadata(client, auth, settings):
    data = image_bytes("JPEG", (3000, 2000))
    response = upload(client, auth, "holiday photo.jpg", data, "image/jpeg")
    assert response.status_code == 201, response.text
    meta = response.json()
    assert meta["original_name"] == "holiday photo.jpg"
    assert meta["kind"] == "image" and meta["content_type"] == "image/jpeg"
    assert (meta["width"], meta["height"]) == (3000, 2000)
    assert meta["size_bytes"] == len(data)
    assert meta["sha256"] == hashlib.sha256(data).hexdigest()
    assert meta["thumbnail_url"] and meta["download_url"].endswith("/download")
    assert len(storage_files(settings)) == 3           # оригінал + оптимізована копія + мініатюра
    assert tmp_files(settings) == []


def test_download_original_is_byte_identical(client, auth):
    data = image_bytes("PNG", (500, 400))
    meta = upload(client, auth, "pic.png", data).json()
    response = client.get(f"/files/{meta['id']}/download", headers=auth)
    assert response.status_code == 200
    assert response.content == data
    assert response.headers["content-type"] == "image/png"
    assert response.headers["content-disposition"].startswith("attachment")
    assert response.headers["x-content-type-options"] == "nosniff"


def test_variants_are_resized_and_smaller(client, auth):
    data = image_bytes("JPEG", (3200, 1800), color=(10, 200, 90))
    meta = upload(client, auth, "big.jpg", data).json()
    optimized = Image.open(io.BytesIO(client.get(f"/files/{meta['id']}/download?variant=optimized", headers=auth).content))
    thumb_resp = client.get(f"/files/{meta['id']}/download?variant=thumbnail", headers=auth)
    thumb = Image.open(io.BytesIO(thumb_resp.content))
    assert max(optimized.size) == 1600 and optimized.size == (1600, 900)
    assert max(thumb.size) == 256 and thumb.size == (256, 144)
    assert thumb_resp.headers["content-type"] == "image/jpeg"
    assert meta["thumbnail_size"] < meta["optimized_size"] < meta["size_bytes"]


def test_small_images_are_not_upscaled(client, auth):
    meta = upload(client, auth, "tiny.png", image_bytes("PNG", (100, 50))).json()
    thumb = Image.open(io.BytesIO(client.get(f"/files/{meta['id']}/download?variant=thumbnail", headers=auth).content))
    assert thumb.size == (100, 50)


def test_png_with_transparency_keeps_alpha(client, auth):
    data = image_bytes("PNG", (600, 600), mode="RGBA", color=(255, 0, 0, 90))
    meta = upload(client, auth, "logo.png", data).json()
    response = client.get(f"/files/{meta['id']}/download?variant=thumbnail", headers=auth)
    assert response.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(response.content)).mode == "RGBA"


def test_webp_and_gif_are_processed(client, auth):
    for fmt, name in (("WEBP", "a.webp"), ("GIF", "a.gif")):
        response = upload(client, auth, name, image_bytes(fmt, (700, 300)))
        assert response.status_code == 201, (fmt, response.text)
        assert response.json()["thumbnail_size"]


def test_exif_orientation_is_applied(client, auth):
    image = Image.new("RGB", (400, 200), (50, 60, 70))
    exif = Image.Exif()
    exif[0x0112] = 6                                   # потрібен поворот на 90°
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", exif=exif.tobytes())
    meta = upload(client, auth, "rot.jpg", buffer.getvalue()).json()
    assert (meta["width"], meta["height"]) == (200, 400)


def test_exif_metadata_is_stripped_from_variants(client, auth):
    exif = Image.Exif()
    exif[0x010F] = "SecretCameraMaker"
    buffer = io.BytesIO()
    Image.new("RGB", (300, 300), (1, 2, 3)).save(buffer, "JPEG", exif=exif.tobytes())
    meta = upload(client, auth, "gps.jpg", buffer.getvalue()).json()
    content = client.get(f"/files/{meta['id']}/download?variant=optimized", headers=auth).content
    assert b"SecretCameraMaker" not in content


def test_pdf_is_stored_without_variants(client, auth, settings):
    data = pdf_bytes(4096)
    response = upload(client, auth, "report.pdf", data, "application/pdf")
    assert response.status_code == 201
    meta = response.json()
    assert meta["kind"] == "document" and meta["thumbnail_url"] is None and meta["width"] is None
    assert len(storage_files(settings)) == 1
    assert client.get(f"/files/{meta['id']}/download?variant=thumbnail", headers=auth).status_code == 404
    assert client.get(f"/files/{meta['id']}/download", headers=auth).content == data


def test_get_metadata(client, auth):
    meta = upload(client, auth, "doc.pdf", pdf_bytes()).json()
    response = client.get(f"/files/{meta['id']}", headers=auth)
    assert response.status_code == 200 and response.json() == meta


# ---------- відхилення некоректних файлів ----------

def test_text_disguised_as_png_is_rejected(client, auth, settings):
    response = upload(client, auth, "fake.png", b"just plain text, not an image", "image/png")
    assert response.status_code == 415
    assert storage_files(settings) == [] and tmp_files(settings) == []


def test_executable_with_image_extension_is_rejected(client, auth):
    assert upload(client, auth, "evil.png", b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 100).status_code == 415


def test_real_image_with_wrong_extension_is_rejected(client, auth):
    assert upload(client, auth, "photo.exe", image_bytes("PNG", (10, 10))).status_code == 415
    assert upload(client, auth, "photo", image_bytes("PNG", (10, 10))).status_code == 415


def test_content_type_mismatch_is_rejected(client, auth):
    assert upload(client, auth, "photo.png", image_bytes("PNG", (10, 10)), "application/pdf").status_code == 415


def test_empty_file_is_rejected(client, auth):
    assert upload(client, auth, "empty.png", b"").status_code == 400


def test_corrupted_image_is_rejected_and_cleaned(client, auth, settings):
    broken = image_bytes("JPEG", (200, 200))[:60] + b"\x00" * 200      # валідна сигнатура, зіпсований вміст
    response = upload(client, auth, "broken.jpg", broken)
    assert response.status_code == 422
    assert storage_files(settings) == [] and tmp_files(settings) == []


def test_truncated_png_is_rejected(client, auth):
    data = image_bytes("PNG", (400, 400), color=(9, 9, 9))
    assert upload(client, auth, "cut.png", data[: len(data) // 2]).status_code == 422


def test_missing_file_field_is_422(client, auth):
    assert client.post("/files", headers=auth, data={"x": "y"}).status_code == 422


def test_pixel_bomb_is_rejected(tmp_path):
    app = create_app(make_settings(tmp_path, max_image_pixels=1_000_000))
    with TestClient(app) as client:
        register(client)
        headers = login_headers(client)
        bomb = image_bytes("PNG", (3000, 3000))                       # 9 Мпікс, але файл дуже малий
        assert len(bomb) < 100_000
        assert upload(client, headers, "bomb.png", bomb).status_code == 422


# ---------- обмеження розміру ----------

def test_oversized_upload_rejected_while_streaming(tmp_path):
    settings = make_settings(tmp_path, max_upload_bytes=10_000, chunk_size=4096)
    app = create_app(settings)
    with TestClient(app) as client:
        register(client)
        headers = login_headers(client)
        response = upload(client, headers, "big.pdf", pdf_bytes(20_000))          # менше за ліміт + запас -> потокова перевірка
        assert response.status_code == 413
        assert storage_files(settings) == [] and tmp_files(settings) == []


def test_oversized_upload_rejected_early_by_content_length(tmp_path):
    settings = make_settings(tmp_path, max_upload_bytes=10_000)
    app = create_app(settings)
    with TestClient(app) as client:
        register(client)
        headers = login_headers(client)
        response = upload(client, headers, "huge.pdf", pdf_bytes(300_000))        # перевищує ліміт + запас -> рання відмова
        assert response.status_code == 413
        assert storage_files(settings) == []


def test_file_exactly_at_limit_is_accepted(tmp_path):
    settings = make_settings(tmp_path, max_upload_bytes=10_000)
    app = create_app(settings)
    with TestClient(app) as client:
        register(client)
        headers = login_headers(client)
        assert upload(client, headers, "ok.pdf", pdf_bytes(10_000)).status_code == 201
        assert upload(client, headers, "over.pdf", pdf_bytes(10_001)).status_code == 413


# ---------- безпека та розмежування доступу ----------

def test_path_traversal_in_filename_is_neutralised(client, auth, settings):
    response = upload(client, auth, "../../../etc/passwd.png", image_bytes("PNG", (20, 20)))
    assert response.status_code == 201
    assert response.json()["original_name"] == "passwd.png"
    root = Path(settings.storage_dir).resolve()
    assert all(root in p.resolve().parents for p in storage_files(settings))
    assert not (root.parent / "etc").exists()


def test_stored_names_are_server_generated(client, auth, settings):
    upload(client, auth, "my secret name.png", image_bytes("PNG", (20, 20)))
    for path in storage_files(settings):
        assert "secret" not in path.name
        assert path.suffix in {".png", ".jpg"}


def test_user_cannot_access_foreign_files(client, auth, auth_bob):
    meta = upload(client, auth, "private.pdf", pdf_bytes()).json()
    fid = meta["id"]
    assert client.get(f"/files/{fid}", headers=auth_bob).status_code == 404
    assert client.get(f"/files/{fid}/download", headers=auth_bob).status_code == 404
    assert client.delete(f"/files/{fid}", headers=auth_bob).status_code == 404
    assert client.get("/files", headers=auth_bob).json()["total"] == 0
    assert client.get(f"/files/{fid}", headers=auth).status_code == 200   # власник і далі має доступ


@pytest.mark.parametrize("bad_id", ["../../etc/passwd", "g" * 32, "A" * 32, "abc", "0" * 31])
def test_invalid_file_ids_are_rejected(client, auth, bad_id):
    assert client.get(f"/files/{bad_id}", headers=auth).status_code in (404, 422)
    assert client.get(f"/files/{bad_id}/download", headers=auth).status_code in (404, 422)


def test_unknown_file_id_is_404(client, auth):
    assert client.get("/files/" + "0" * 32, headers=auth).status_code == 404


def test_invalid_variant_is_422(client, auth):
    meta = upload(client, auth, "a.png", image_bytes("PNG", (50, 50))).json()
    assert client.get(f"/files/{meta['id']}/download?variant=../../x", headers=auth).status_code == 422


# ---------- список, пошук, пагінація ----------

def _seed(client, auth, count: int = 5) -> list[dict]:
    items = []
    for i in range(count):
        items.append(upload(client, auth, f"file_{i}.pdf", pdf_bytes(1024 + i)).json())
    return items


def test_list_pagination_and_order(client, auth):
    items = _seed(client, auth, 5)
    page1 = client.get("/files?limit=2&offset=0", headers=auth).json()
    page2 = client.get("/files?limit=2&offset=2", headers=auth).json()
    page3 = client.get("/files?limit=2&offset=4", headers=auth).json()
    assert page1["total"] == 5 and (page1["limit"], page1["offset"]) == (2, 0)
    assert len(page1["items"]) == len(page2["items"]) == 2 and len(page3["items"]) == 1
    listed = [f["id"] for p in (page1, page2, page3) for f in p["items"]]
    assert len(set(listed)) == 5
    assert listed[0] == items[-1]["id"]                       # нові першими


def test_list_filters(client, auth):
    upload(client, auth, "cat.png", image_bytes("PNG", (30, 30)))
    upload(client, auth, "report_2026.pdf", pdf_bytes())
    upload(client, auth, "100%_done.pdf", pdf_bytes())
    assert client.get("/files?kind=image", headers=auth).json()["total"] == 1
    assert client.get("/files?kind=document", headers=auth).json()["total"] == 2
    assert client.get("/files?q=REPORT", headers=auth).json()["total"] == 1
    assert client.get("/files?q=%25", headers=auth).json()["total"] == 1     # '%' шукається буквально
    assert client.get("/files?q=r_p", headers=auth).json()["total"] == 0     # '_' не є шаблоном ("rep" не збігається)
    assert client.get("/files?q=t_2", headers=auth).json()["total"] == 1     # а літерально збігається


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "kind=video", "q="])
def test_list_validation(client, auth, query):
    assert client.get(f"/files?{query}", headers=auth).status_code == 422


# ---------- видалення та цілісність ----------

def test_delete_removes_db_record_and_all_files(client, auth, settings):
    meta = upload(client, auth, "x.jpg", image_bytes("JPEG", (900, 900))).json()
    assert len(storage_files(settings)) == 3
    assert client.delete(f"/files/{meta['id']}", headers=auth).status_code == 204
    assert storage_files(settings) == []
    assert client.get(f"/files/{meta['id']}", headers=auth).status_code == 404
    assert client.delete(f"/files/{meta['id']}", headers=auth).status_code == 404
    assert client.get("/files", headers=auth).json()["total"] == 0


def test_missing_content_on_disk_gives_404(client, auth, settings):
    meta = upload(client, auth, "d.pdf", pdf_bytes()).json()
    for path in storage_files(settings):
        path.unlink()
    assert client.get(f"/files/{meta['id']}/download", headers=auth).status_code == 404


def test_database_failure_leaves_no_orphan_files(tmp_path, monkeypatch):
    settings = make_settings(tmp_path)
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        register(client)
        headers = login_headers(client)

        def boom(self):
            raise RuntimeError("database is down")

        monkeypatch.setattr("sqlalchemy.orm.Session.commit", boom)
        response = upload(client, headers, "pic.jpg", image_bytes("JPEG", (800, 800)))
        assert response.status_code == 500
        assert storage_files(settings) == [] and tmp_files(settings) == []


def test_identical_files_get_distinct_ids_but_same_hash(client, auth):
    data = pdf_bytes(3000)
    first, second = upload(client, auth, "a.pdf", data).json(), upload(client, auth, "b.pdf", data).json()
    assert first["id"] != second["id"] and first["sha256"] == second["sha256"]


def test_filenames_with_unicode_roundtrip(client, auth):
    meta = upload(client, auth, "звіт №1.pdf", pdf_bytes()).json()
    assert meta["original_name"] == "звіт №1.pdf"
    response = client.get(f"/files/{meta['id']}/download", headers=auth)
    assert "filename*=utf-8''" in response.headers["content-disposition"]
