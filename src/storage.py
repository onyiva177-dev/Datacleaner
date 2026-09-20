"""
Supabase Storage access for the pipeline running inside Airflow.

Why this exists: in the local docker-compose setup, the uploaded CSV and the
Airflow container happen to share a filesystem volume, so the pipeline could
just read/write local paths. That stops being true once Airflow runs on a
separate host (Render, Railway, etc.) from wherever the file was uploaded.
The pipeline must explicitly pull the raw file down and push results back up
through Supabase Storage's REST API - there is no shared disk to rely on.

Uses plain `requests` against the Storage REST API rather than the supabase-py
package, to keep the Airflow image's dependency footprint small.
"""
from __future__ import annotations

import os

import requests

BUCKET = "datasets"


def _base_url() -> str:
    url = os.getenv("SUPABASE_URL")
    if not url:
        raise RuntimeError(
            "SUPABASE_URL is not set. The pipeline needs this to reach Storage "
            "for both downloading the raw upload and uploading cleaned results."
        )
    return url.rstrip("/")


def _headers() -> dict:
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY is not set. Required to read/write Storage "
            "from the Airflow container (the anon key is not sufficient here)."
        )
    return {"Authorization": f"Bearer {key}"}


def download(storage_path: str, local_path: str, timeout: int = 60) -> str:
    """Download a file from Supabase Storage to a local path. Creates parent dirs."""
    url = f"{_base_url()}/storage/v1/object/{BUCKET}/{storage_path}"
    resp = requests.get(url, headers=_headers(), timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(
            f"Could not download '{storage_path}' from Supabase Storage "
            f"(status {resp.status_code}): {resp.text[:300]}"
        )
    os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
    with open(local_path, "wb") as fh:
        fh.write(resp.content)
    return local_path


def upload(local_path: str, storage_path: str, content_type: str = "text/csv",
          timeout: int = 60) -> str:
    """Upload a local file to Supabase Storage, overwriting if it already exists."""
    url = f"{_base_url()}/storage/v1/object/{BUCKET}/{storage_path}"
    headers = {**_headers(), "Content-Type": content_type, "x-upsert": "true"}
    with open(local_path, "rb") as fh:
        resp = requests.put(url, headers=headers, data=fh.read(), timeout=timeout)
    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Could not upload '{local_path}' to '{storage_path}' "
            f"(status {resp.status_code}): {resp.text[:300]}"
        )
    return storage_path


CONTENT_TYPES = {
    ".csv": "text/csv",
    ".parquet": "application/octet-stream",
    ".md": "text/markdown",
    ".json": "application/json",
}


def upload_export_bundle(dataset_id: int, local_dir: str) -> list[str]:
    """
    Uploads every file in local_dir to cleaned/<dataset_id>/<filename>, matching
    the fixed paths the frontend's /api/export route reads from. Returns the
    list of storage paths written.
    """
    written = []
    for filename in sorted(os.listdir(local_dir)):
        local_path = os.path.join(local_dir, filename)
        if not os.path.isfile(local_path):
            continue
        ext = os.path.splitext(filename)[1]
        content_type = CONTENT_TYPES.get(ext, "application/octet-stream")
        storage_path = f"cleaned/{dataset_id}/{filename}"
        upload(local_path, storage_path, content_type)
        written.append(storage_path)
    return written
