#!/usr/bin/env python3
"""Upload a local file or directory backup to Baidu Cloud BOS."""

from __future__ import annotations

import argparse
import concurrent.futures
import getpass
import importlib
import sys
import time
import threading
from dataclasses import dataclass
from pathlib import Path


DEFAULT_BUCKET = "baic-sil-data"
DEFAULT_ENDPOINT = "https://bj.bcebos.com"
SINGLE_UPLOAD_LIMIT = 5 * 1024 * 1024 * 1024
MULTIPART_CHUNK_SIZE = 64 * 1024 * 1024
PROGRESS_BAR_WIDTH = 30
DEFAULT_THREADS = 16


@dataclass
class UploadTarget:
    path: Path
    object_key: str


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
    parser.add_argument(
        "-t",
        "--threads",
        type=int,
        default=DEFAULT_THREADS,
        help=f"Concurrent upload threads (default: {DEFAULT_THREADS})",
    )
    return parser.parse_args()


def prompt_credentials() -> tuple[str, str]:
    access_key_id = input("Baidu Cloud AK: ").strip()
    secret_access_key = getpass.getpass("Baidu Cloud SK: ").strip()
    if not access_key_id or not secret_access_key:
        raise ValueError("AK and SK cannot be empty")
    return access_key_id, secret_access_key


def load_bos_sdk():
    try:
        credentials_module = importlib.import_module("baidubce.auth.bce_credentials")
        config_module = importlib.import_module("baidubce.bce_client_configuration")
        client_module = importlib.import_module("baidubce.services.bos.bos_client")
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency. Install it with: python3 -m pip install bce-python-sdk"
        ) from exc

    return credentials_module, config_module, client_module


def build_bos_client(endpoint: str, access_key_id: str, secret_access_key: str, sdk_modules):
    credentials_module, config_module, client_module = sdk_modules

    config = config_module.BceClientConfiguration(
        credentials=credentials_module.BceCredentials(access_key_id, secret_access_key),
        endpoint=endpoint,
    )
    return client_module.BosClient(config)


def make_object_key(prefix: str, object_name: str) -> str:
    clean_prefix = prefix.strip("/")
    return f"{clean_prefix}/{object_name}" if clean_prefix else object_name


def prepare_upload(source: Path, prefix: str, object_key: str | None) -> list[UploadTarget]:
    if not source.exists():
        raise FileNotFoundError(f"Source does not exist: {source}")

    if source.is_file():
        return [UploadTarget(path=source, object_key=object_key or make_object_key(prefix, source.name))]

    if source.is_dir():
        if object_key:
            raise ValueError("--object-key can only be used when --source is a file")

        return [
            UploadTarget(
                path=file_path,
                object_key=make_object_key(
                    prefix,
                    str(file_path.relative_to(source.parent)).replace("\\", "/"),
                ),
            )
            for file_path in sorted(source.rglob("*"))
            if file_path.is_file()
        ]

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
        self.downloaded = 0
        self.last_percent = -1
        self.last_uploaded = 0
        self.last_time = time.monotonic()
        self.last_speed = 0.0
        self.lock = threading.Lock()

    def update(self, consumed_bytes: int, total_bytes: int | None = None) -> None:
        with self.lock:
            self._render(consumed_bytes)

    def add(self, consumed_bytes: int) -> None:
        with self.lock:
            self.downloaded = min(self.downloaded + max(consumed_bytes, 0), self.total_bytes)
            self._render(self.downloaded)

    def _render(self, consumed_bytes: int) -> None:
        now = time.monotonic()
        uploaded = min(consumed_bytes, self.total_bytes)
        percent = int(uploaded * 100 / self.total_bytes)

        elapsed = now - self.last_time
        if elapsed > 0:
            self.last_speed = max(uploaded - self.last_uploaded, 0) / elapsed

        if percent == self.last_percent and uploaded < self.total_bytes and elapsed < 0.5:
            return

        self.last_percent = percent
        self.last_uploaded = uploaded
        self.last_time = now
        filled = int(PROGRESS_BAR_WIDTH * uploaded / self.total_bytes)
        bar = "#" * filled + "-" * (PROGRESS_BAR_WIDTH - filled)
        print(
            f"\rUploading: [{bar}] {percent:3d}% "
            f"{format_bytes(uploaded)}/{format_bytes(self.total_bytes)} "
            f"{format_bytes(int(self.last_speed))}/s",
            end="",
            flush=True,
        )

    def finish(self) -> None:
        with self.lock:
            self.downloaded = self.total_bytes
            self._render(self.total_bytes)
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
            part_uploaded = 0

            def update_part(consumed_bytes: int, total_bytes: int) -> None:
                nonlocal part_uploaded
                progress.add(max(consumed_bytes - part_uploaded, 0))
                part_uploaded = consumed_bytes

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
            progress.add(part_size - part_uploaded)
            offset += part_size
            part_number += 1

        client.complete_multipart_upload(bucket, object_key, upload_id, part_list)
    except Exception:
        client.abort_multipart_upload(bucket, object_key, upload_id)
        raise


def upload_file(client, bucket: str, object_key: str, local_path: Path, progress: ProgressBar) -> str:
    if local_path.stat().st_size >= SINGLE_UPLOAD_LIMIT:
        upload_multipart(client, bucket, object_key, local_path, progress)
        return "multipart"

    uploaded = 0

    def update_file(consumed_bytes: int, total_bytes: int) -> None:
        nonlocal uploaded
        progress.add(max(consumed_bytes - uploaded, 0))
        uploaded = consumed_bytes

    client.put_object_from_file(
        bucket,
        object_key,
        str(local_path),
        progress_callback=update_file,
    )
    progress.add(local_path.stat().st_size - uploaded)
    return "single"


def main() -> int:
    args = parse_args()
    source = Path(args.source).expanduser().resolve()
    upload_targets: list[UploadTarget] = []

    try:
        sdk_modules = load_bos_sdk()
        upload_targets = prepare_upload(source, args.prefix, args.object_key)
        if not upload_targets:
            raise ValueError(f"Source directory contains no regular files: {source}")
        access_key_id, secret_access_key = prompt_credentials()
        client = build_bos_client(args.endpoint, access_key_id, secret_access_key, sdk_modules)

        print("==========================================")
        print(f"Source:     {source}")
        print(f"Bucket:     {args.bucket}")
        print(f"Endpoint:   {args.endpoint}")
        print(f"Files:      {len(upload_targets)}")
        print("==========================================")

        methods = set()
        progress = ProgressBar(sum(target.path.stat().st_size for target in upload_targets))
        worker_count = max(1, args.threads)

        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(
                    upload_file,
                    client,
                    args.bucket,
                    upload_target.object_key,
                    upload_target.path,
                    progress,
                ): upload_target
                for upload_target in upload_targets
            }
            for future in concurrent.futures.as_completed(futures):
                upload_target = futures[future]
                method = future.result()
                methods.add(method)
                print(f"\nUploaded: {upload_target.object_key}")

        progress.finish()

        print(
            f"Backup uploaded successfully ({len(upload_targets)} file(s), "
            f"{', '.join(sorted(methods))} upload, {worker_count} thread(s))."
        )
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())