#!/usr/bin/env python3
"""Upload a local file or directory backup to Baidu Cloud BOS."""

from __future__ import annotations

import argparse
import getpass
import importlib
import shutil
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path


DEFAULT_BUCKET = "baic-sil-data"
DEFAULT_ENDPOINT = "https://bj.bcebos.com"
SINGLE_UPLOAD_LIMIT = 5 * 1024 * 1024 * 1024
MULTIPART_CHUNK_SIZE = 64 * 1024 * 1024
PROGRESS_BAR_WIDTH = 30


@dataclass
class UploadTarget:
    path: Path
    object_key: str
    temp_dir: Path | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Back up data to a Baidu Cloud BOS bucket.")
    parser.add_argument("-s", "--source", required=True, help="Local file or directory to upload")
    parser.add_argument("-b", "--bucket", default=DEFAULT_BUCKET, help="BOS bucket name")
    parser.add_argument(
        "-e",
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help="BOS endpoint, for example https://bj.bcebos.com",
    )
    parser.add_argument(
        "-p",
        "--prefix",
        required=True,
        help="Object key prefix in BOS",
    )
    parser.add_argument(
        "--object-key",
        help="Exact BOS object key. If omitted, prefix plus the original file name is used.",
    )
    return parser.parse_args()


def prompt_credentials() -> tuple[str, str]:
    access_key_id = input("Baidu Cloud AK: ").strip()
    secret_access_key = getpass.getpass("Baidu Cloud SK: ").strip()
    if not access_key_id or not secret_access_key:
        raise ValueError("AK and SK cannot be empty")
    return access_key_id, secret_access_key


def build_bos_client(endpoint: str, access_key_id: str, secret_access_key: str):
    try:
        credentials_module = importlib.import_module("baidubce.auth.bce_credentials")
        config_module = importlib.import_module("baidubce.bce_client_configuration")
        client_module = importlib.import_module("baidubce.services.bos.bos_client")
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency. Install it with: python3 -m pip install bce-python-sdk"
        ) from exc

    config = config_module.BceClientConfiguration(
        credentials=credentials_module.BceCredentials(access_key_id, secret_access_key),
        endpoint=endpoint,
    )
    return client_module.BosClient(config)


def make_object_key(prefix: str, object_name: str) -> str:
    clean_prefix = prefix.strip("/")
    return f"{clean_prefix}/{object_name}" if clean_prefix else object_name


def prepare_upload(source: Path, prefix: str, object_key: str | None) -> UploadTarget:
    if not source.exists():
        raise FileNotFoundError(f"Source does not exist: {source}")

    if source.is_file():
        return UploadTarget(
            path=source,
            object_key=object_key or make_object_key(prefix, source.name),
        )

    if source.is_dir():
        temp_dir = Path(tempfile.mkdtemp(prefix="bos-backup-"))
        archive_path = temp_dir / f"{source.name}.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(source, arcname=source.name)

        return UploadTarget(
            path=archive_path,
            object_key=object_key or make_object_key(prefix, archive_path.name),
            temp_dir=temp_dir,
        )

    raise ValueError(f"Source must be a regular file or directory: {source}")


def format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{value:.2f} TiB"


class ProgressBar:
    def __init__(self, total_bytes: int) -> None:
        self.total_bytes = max(total_bytes, 1)
        self.last_percent = -1

    def update(self, consumed_bytes: int, total_bytes: int | None = None) -> None:
        uploaded = min(consumed_bytes, self.total_bytes)
        percent = int(uploaded * 100 / self.total_bytes)
        if percent == self.last_percent and uploaded < self.total_bytes:
            return

        self.last_percent = percent
        filled = int(PROGRESS_BAR_WIDTH * uploaded / self.total_bytes)
        bar = "#" * filled + "-" * (PROGRESS_BAR_WIDTH - filled)
        print(
            f"\rUploading: [{bar}] {percent:3d}% "
            f"{format_bytes(uploaded)}/{format_bytes(self.total_bytes)}",
            end="",
            flush=True,
        )

    def finish(self) -> None:
        self.update(self.total_bytes)
        print()


def upload_multipart(client, bucket: str, object_key: str, local_path: Path, progress: ProgressBar) -> None:
    upload_id = client.initiate_multipart_upload(bucket, object_key).upload_id
    part_list = []
    file_size = local_path.stat().st_size
    offset = 0
    part_number = 1

    try:
        while offset < file_size:
            part_size = min(MULTIPART_CHUNK_SIZE, file_size - offset)

            def update_part(consumed_bytes: int, total_bytes: int, part_offset: int = offset) -> None:
                progress.update(part_offset + consumed_bytes)

            response = client.upload_part_from_file(
                bucket,
                object_key,
                upload_id,
                part_number,
                part_size,
                str(local_path),
                offset,
                progress_callback=update_part,
            )
            part_list.append({"partNumber": part_number, "eTag": response.metadata.etag})
            offset += part_size
            part_number += 1

        client.complete_multipart_upload(bucket, object_key, upload_id, part_list)
    except Exception:
        client.abort_multipart_upload(bucket, object_key, upload_id)
        raise


def upload_file(client, bucket: str, object_key: str, local_path: Path) -> str:
    progress = ProgressBar(local_path.stat().st_size)
    if local_path.stat().st_size >= SINGLE_UPLOAD_LIMIT:
        upload_multipart(client, bucket, object_key, local_path, progress)
        progress.finish()
        return "multipart"

    client.put_object_from_file(
        bucket,
        object_key,
        str(local_path),
        progress_callback=progress.update,
    )
    progress.finish()
    return "single"


def main() -> int:
    args = parse_args()
    source = Path(args.source).expanduser().resolve()
    upload_target: UploadTarget | None = None

    try:
        upload_target = prepare_upload(source, args.prefix, args.object_key)
        access_key_id, secret_access_key = prompt_credentials()
        client = build_bos_client(args.endpoint, access_key_id, secret_access_key)

        size_mb = upload_target.path.stat().st_size / 1024 / 1024
        print("==========================================")
        print(f"Source:     {source}")
        print(f"Upload:     {upload_target.path} ({size_mb:.2f} MiB)")
        print(f"Bucket:     {args.bucket}")
        print(f"Endpoint:   {args.endpoint}")
        print(f"Object key: {upload_target.object_key}")
        print("==========================================")

        method = upload_file(client, args.bucket, upload_target.object_key, upload_target.path)
        print(f"Backup uploaded successfully ({method} upload).")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        if upload_target and upload_target.temp_dir:
            shutil.rmtree(upload_target.temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())