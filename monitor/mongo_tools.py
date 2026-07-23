#!/usr/bin/env python3
"""MongoDB 工具脚本：检查、备份、还原。

默认连接本套 monitor 平台的 MongoDB（宿主机端口 30253，库 server_monitor，无认证）。
备份和还原都使用单文件 archive 形式，不提供额外压缩/加密选项。

用法:
    python mongo_tools.py inspect
    python mongo_tools.py backup
    python mongo_tools.py restore /path/to/server_monitor_YYYYMMDD_HHMMSS.archive

依赖: mongodump / mongorestore 可执行文件（MongoDB Database Tools），
      需在 PATH 中可用，或者通过参数指定绝对路径。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from pymongo import MongoClient


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = int(os.getenv("MONGODB_PORT", "30253"))
DEFAULT_DB = os.getenv("MONGO_DB", "server_monitor")
DEFAULT_BACKUP_DIR = Path(__file__).resolve().parent / "mongo_backups"


def _human_bytes(value: int | float | None) -> str:
    if value is None:
        return "--"
    total = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if total < 1024 or unit == "TB":
            return f"{total:.1f}{unit}"
        total /= 1024
    return f"{total:.1f}TB"


def _format_dt(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else "--"


def _collect_date_ranges(db, collection_name: str) -> dict[str, tuple[datetime | None, datetime | None]]:
    date_fields = {
        "metrics": ["timestamp"],
        "servers": ["registered_at", "last_seen"],
        "server_mapping": [],
    }

    ranges: dict[str, tuple[datetime | None, datetime | None]] = {}
    for field in date_fields.get(collection_name, []):
        pipeline = [
            {"$match": {field: {"$type": "date"}}},
            {"$group": {"_id": None, "min": {"$min": f"${field}"}, "max": {"$max": f"${field}"}}},
        ]
        rows = list(db[collection_name].aggregate(pipeline))
        if rows:
            ranges[field] = (rows[0].get("min"), rows[0].get("max"))
    return ranges


def _mongo_client(host: str, port: int) -> MongoClient:
    return MongoClient(host, port, serverSelectionTimeoutMS=5000)


def inspect_db(args) -> None:
    client = _mongo_client(args.host, args.port)
    try:
        client.admin.command("ping")
        db = client[args.database]

        stats = db.command("dbstats")
        print(f"[数据库] {args.database}")
        print(f"  collections : {stats.get('collections', 0)}")
        print(f"  objects     : {stats.get('objects', 0)}")
        print(f"  dataSize    : {_human_bytes(stats.get('dataSize'))}")
        print(f"  storageSize : {_human_bytes(stats.get('storageSize'))}")
        print(f"  indexSize   : {_human_bytes(stats.get('indexSize'))}")
        print()

        for collection_name in sorted(db.list_collection_names()):
            coll_stats = db.command("collstats", collection_name)
            print(f"[集合] {collection_name}")
            print(f"  count       : {coll_stats.get('count', 0)}")
            print(f"  size        : {_human_bytes(coll_stats.get('size'))}")
            print(f"  storageSize  : {_human_bytes(coll_stats.get('storageSize'))}")
            print(f"  totalIndexSz : {_human_bytes(coll_stats.get('totalIndexSize'))}")

            date_ranges = _collect_date_ranges(db, collection_name)
            if date_ranges:
                for field, (min_dt, max_dt) in date_ranges.items():
                    print(f"  {field:<12}: {_format_dt(min_dt)}  ->  {_format_dt(max_dt)}")
            else:
                print("  date range   : --")
            print()
    finally:
        client.close()


def _build_archive_path(out_dir: Path, database: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return out_dir / f"{database}_{stamp}.archive"


def backup_db(args) -> Path:
    if not shutil.which(args.bin):
        sys.exit(f"[错误] 找不到 {args.bin}。请安装 MongoDB Database Tools，或通过 --bin 指定绝对路径。")

    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = _build_archive_path(out_dir, args.database)

    cmd = [
        args.bin,
        f"--host={args.host}",
        f"--port={args.port}",
        f"--db={args.database}",
        f"--archive={out_path}",
    ]
    print("[备份] 执行命令:", " ".join(cmd))

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        if out_path.exists():
            out_path.unlink(missing_ok=True)
        sys.exit(f"[错误] mongodump 失败，返回码 {exc.returncode}。")

    print(f"[完成] 备份成功: {out_path}")
    return out_path


def restore_db(args) -> None:
    archive_path = Path(args.archive).expanduser().resolve()
    if not archive_path.is_file():
        sys.exit(f"[错误] 备份文件不存在: {archive_path}")

    if not shutil.which(args.restore_bin):
        sys.exit(f"[错误] 找不到 {args.restore_bin}。请安装 MongoDB Database Tools，或通过 --restore-bin 指定绝对路径。")

    cmd = [
        args.restore_bin,
        f"--host={args.host}",
        f"--port={args.port}",
        f"--archive={archive_path}",
    ]
    if args.drop:
        cmd.append("--drop")

    print("[还原] 执行命令:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print("[完成] 还原成功")


def parse_args():
    parser = argparse.ArgumentParser(description="MongoDB 工具：检查、备份、还原。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--host", default=DEFAULT_HOST, help=f"MongoDB 主机，默认 {DEFAULT_HOST}")
    common.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"MongoDB 端口，默认 {DEFAULT_PORT}")
    common.add_argument("--database", default=DEFAULT_DB, help=f"数据库名，默认 {DEFAULT_DB}")

    subparsers.add_parser("inspect", parents=[common], help="查看数据库概况")

    backup_parser = subparsers.add_parser("backup", parents=[common], help="备份数据库为单个 archive 文件")
    backup_parser.add_argument("--out-dir", default=str(DEFAULT_BACKUP_DIR), help=f"备份目录，默认 {DEFAULT_BACKUP_DIR}")
    backup_parser.add_argument("--bin", default="mongodump", help="mongodump 可执行文件路径，默认从 PATH 查找")

    restore_parser = subparsers.add_parser("restore", parents=[common], help="从指定 archive 备份文件还原数据库")
    restore_parser.add_argument("archive", help="archive 备份文件路径")
    restore_parser.add_argument("--drop", action="store_true", help="还原前先清空同名集合")
    restore_parser.add_argument("--restore-bin", default="mongorestore", help="mongorestore 可执行文件路径，默认从 PATH 查找")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "inspect":
        inspect_db(args)
    elif args.command == "backup":
        backup_db(args)
    elif args.command == "restore":
        restore_db(args)


if __name__ == "__main__":
    main()