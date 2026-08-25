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

        client.put_object_from_file(args.bucket, upload_target.object_key, str(upload_target.path))
        print("Backup uploaded successfully.")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        if upload_target and upload_target.temp_dir:
            shutil.rmtree(upload_target.temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())