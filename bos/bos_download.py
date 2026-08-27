#!/usr/bin/env python3
"""Download a file or directory prefix from Baidu Cloud BOS."""

from __future__ import annotations

import argparse
import concurrent.futures
import getpass
import importlib
import shutil
import sys
import time
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path


DEFAULT_BUCKET = "baic-sil-data"
DEFAULT_ENDPOINT = "https://bj.bcebos.com"
DEFAULT_THREADS = 4
RANGED_DOWNLOAD_CHUNK_SIZE = 64 * 1024 * 1024
PROGRESS_BAR_WIDTH = 30


@dataclass
class DownloadItem:
    object_key: str
    local_path: Path
    size: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download data from a Baidu Cloud BOS bucket.")
    parser.add_argument(
        "-s",
        "--source",
        required=True,
        help="BOS object key or directory prefix to download",
    )
    parser.add_argument(
        "-d",
        "--dest",
        required=True,
        help="Local directory to save downloaded files",
    )
    parser.add_argument("-b", "--bucket", default=DEFAULT_BUCKET, help="BOS bucket name")
    parser.add_argument(
        "-e",
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help="BOS endpoint, for example https://bj.bcebos.com",
    )
    parser.add_argument(
        "-t",
        "--threads",
        type=int,
        default=DEFAULT_THREADS,
        help=f"Concurrent download threads (default: {DEFAULT_THREADS})",
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
        self.last_downloaded = 0
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
        downloaded = min(consumed_bytes, self.total_bytes)
        percent = int(downloaded * 100 / self.total_bytes)

        elapsed = now - self.last_time
        if elapsed > 0:
            self.last_speed = max(downloaded - self.last_downloaded, 0) / elapsed

        if percent == self.last_percent and downloaded < self.total_bytes and elapsed < 0.5:
            return

        self.last_percent = percent
        self.last_downloaded = downloaded
        self.last_time = now
        filled = int(PROGRESS_BAR_WIDTH * downloaded / self.total_bytes)
        bar = "#" * filled + "-" * (PROGRESS_BAR_WIDTH - filled)
        print(
            f"\rDownloading: [{bar}] {percent:3d}% "
            f"{format_bytes(downloaded)}/{format_bytes(self.total_bytes)} "
            f"{format_bytes(int(self.last_speed))}/s",
            end="",
            flush=True,
        )

    def finish(self) -> None:
        with self.lock:
            self.downloaded = self.total_bytes
            self._render(self.total_bytes)
        print()


def object_key_to_str(object_key: object) -> str:
    if isinstance(object_key, bytes):
        return object_key.decode("utf-8")
    return str(object_key)


def normalize_prefix(prefix: str) -> str:
    return prefix.strip("/")


def safe_local_path(base_dir: Path, relative_key: str) -> Path:
    parts = [part for part in relative_key.split("/") if part and part not in (".", "..")]
    if not parts:
        raise ValueError(f"Invalid object key for local path: {relative_key}")
    return base_dir.joinpath(*parts)


def get_object_size(client, bucket: str, object_key: str) -> int:
    response = client.get_object_meta_data(bucket, object_key)
    return int(response.metadata.content_length)


def build_file_item(client, bucket: str, object_key: str, dest_dir: Path) -> DownloadItem:
    return DownloadItem(
        object_key=object_key,
        local_path=safe_local_path(dest_dir, Path(object_key).name),
        size=get_object_size(client, bucket, object_key),
    )


def build_directory_items(client, bucket: str, source: str, dest_dir: Path) -> list[DownloadItem]:
    clean_source = normalize_prefix(source)
    prefix = f"{clean_source}/" if clean_source else ""
    root_dir = dest_dir if source.endswith("/") else dest_dir / Path(clean_source).name
    items: list[DownloadItem] = []

    for item in client.list_all_objects(bucket, prefix=prefix):
        object_key = object_key_to_str(item.key)
        if object_key.endswith("/"):
            continue
        relative_key = object_key[len(prefix) :]
        items.append(
            DownloadItem(
                object_key=object_key,
                local_path=safe_local_path(root_dir, relative_key),
                size=int(getattr(item, "size", 0)),
            )
        )

    if not items:
        raise FileNotFoundError(f"No BOS objects found for source: {source}")
    return items


def build_download_items(client, bucket: str, source: str, dest_dir: Path) -> list[DownloadItem]:
    clean_source = source.strip("/")
    if not clean_source:
        return build_directory_items(client, bucket, source, dest_dir)

    try:
        return [build_file_item(client, bucket, clean_source, dest_dir)]
    except Exception:
        return build_directory_items(client, bucket, source, dest_dir)


def download_object(client, bucket: str, item: DownloadItem, progress: ProgressBar) -> None:
    item.local_path.parent.mkdir(parents=True, exist_ok=True)
    downloaded = 0

    def update_item(consumed_bytes: int, total_bytes: int) -> None:
        nonlocal downloaded
        delta = max(consumed_bytes - downloaded, 0)
        downloaded = consumed_bytes
        progress.add(delta)

    client.get_object_to_file(
        bucket,
        item.object_key,
        str(item.local_path),
        progress_callback=update_item,
    )
    progress.add(item.size - downloaded)


def download_object_range(
    client,
    bucket: str,
    item: DownloadItem,
    part_path: Path,
    byte_range: tuple[int, int],
    progress: ProgressBar,
) -> None:
    downloaded = 0

    def update_part(consumed_bytes: int, total_bytes: int) -> None:
        nonlocal downloaded
        delta = max(consumed_bytes - downloaded, 0)
        downloaded = consumed_bytes
        progress.add(delta)

    client.get_object_to_file(
        bucket,
        item.object_key,
        str(part_path),
        range=byte_range,
        progress_callback=update_part,
    )
    progress.add(byte_range[1] - byte_range[0] + 1 - downloaded)


def download_large_object(client, bucket: str, item: DownloadItem, progress: ProgressBar, threads: int) -> None:
    item.local_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix="bos-download-"))

    try:
        ranges: list[tuple[int, int, Path]] = []
        for start in range(0, item.size, RANGED_DOWNLOAD_CHUNK_SIZE):
            end = min(start + RANGED_DOWNLOAD_CHUNK_SIZE - 1, item.size - 1)
            part_path = temp_dir / f"part-{len(ranges):06d}"
            ranges.append((start, end, part_path))

        with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
            futures = [
                executor.submit(
                    download_object_range,
                    client,
                    bucket,
                    item,
                    part_path,
                    (start, end),
                    progress,
                )
                for start, end, part_path in ranges
            ]
            for future in concurrent.futures.as_completed(futures):
                future.result()

        with item.local_path.open("wb") as output:
            for _, _, part_path in ranges:
                with part_path.open("rb") as part_file:
                    shutil.copyfileobj(part_file, output)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def download_items(client, bucket: str, items: list[DownloadItem], threads: int) -> str:
    total_size = sum(item.size for item in items)
    progress = ProgressBar(total_size)
    worker_count = max(1, threads)

    if len(items) == 1 and items[0].size > RANGED_DOWNLOAD_CHUNK_SIZE and worker_count > 1:
        download_large_object(client, bucket, items[0], progress, worker_count)
        progress.finish()
        return "ranged"

    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(download_object, client, bucket, item, progress) for item in items]
        for future in concurrent.futures.as_completed(futures):
            future.result()

    progress.finish()
    return "parallel" if worker_count > 1 and len(items) > 1 else "single"


def main() -> int:
    args = parse_args()
    dest_dir = Path(args.dest).expanduser().resolve()

    try:
        sdk_modules = load_bos_sdk()
        access_key_id, secret_access_key = prompt_credentials()
        client = build_bos_client(args.endpoint, access_key_id, secret_access_key, sdk_modules)
        items = build_download_items(client, args.bucket, args.source, dest_dir)
        total_size = sum(item.size for item in items)

        print("==========================================")
        print(f"Source:   {args.source}")
        print(f"Dest:     {dest_dir}")
        print(f"Bucket:   {args.bucket}")
        print(f"Endpoint: {args.endpoint}")
        print(f"Objects:  {len(items)}")
        print(f"Size:     {format_bytes(total_size)}")
        print(f"Threads:  {max(1, args.threads)}")
        print("==========================================")

        method = download_items(client, args.bucket, items, args.threads)
        print(f"Download completed successfully ({method} download).")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())