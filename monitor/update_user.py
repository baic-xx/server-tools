#!/usr/bin/env python3
"""服务器-用户映射管理工具

用法:
    python manage.py sync            # 从 servers.json 导入映射到 MongoDB
    python manage.py sync --json /path/to/servers.json  # 指定 JSON 文件
    python manage.py show            # 显示当前数据库中的映射
    python manage.py clear           # 清空映射数据
"""
import sys
import os
import json
import argparse

# 添加 server/ 目录到模块搜索路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "server"))
from pymongo import MongoClient
from config import MONGO_URI, MONGO_DB

# 宿主机运行时，MongoDB 端口映射为 30253（Docker 内部仍是 27017）
# 如果 MONGO_URI 仍是默认的 27017，自动替换为宿主机端口
_host_mongo_port = os.getenv("MONGODB_PORT", "30253")
if "27017" in MONGO_URI:
    MONGO_URI = MONGO_URI.replace("27017", _host_mongo_port)


def get_collection():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[MONGO_DB]
    return db["server_mapping"], client


def cmd_sync(json_path: str):
    """从 JSON 文件同步映射到 MongoDB"""
    if not os.path.isfile(json_path):
        print(f"[错误] 文件不存在: {json_path}")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    servers = data.get("servers", {})
    users = data.get("users", [])

    col, client = get_collection()
    col.drop()

    # 写入服务器 → 公网 IP 映射
    for hostname, public_ip in servers.items():
        col.update_one(
            {"hostname": hostname},
            {"$set": {"public_ip": public_ip}},
            upsert=True,
        )

    # 写入服务器 → 归属人映射
    for user in users:
        name = user["name"]
        for hostname in user["servers"]:
            col.update_one(
                {"hostname": hostname},
                {"$addToSet": {"users": name}},
                upsert=True,
            )

    count = col.count_documents({})
    client.close()
    print(f"[完成] 已同步 {count} 台服务器的映射数据")


def cmd_show():
    """显示当前映射"""
    col, client = get_collection()
    docs = list(col.find({"_id": 0}).sort("hostname", 1))

    if not docs:
        print("[空] 数据库中暂无映射数据")
    else:
        print(f"共 {len(docs)} 台服务器:\n")
        for doc in docs:
            hostname = doc["hostname"]
            public_ip = doc.get("public_ip", "--")
            users = ", ".join(doc.get("users", []))
            print(f"  {hostname:20s}  公网IP: {public_ip:25s}  归属人: {users}")

    client.close()


def cmd_clear():
    """清空映射数据"""
    col, client = get_collection()
    count = col.count_documents({})
    col.drop()
    client.close()
    print(f"[完成] 已清空 {count} 条映射数据")


def main():
    parser = argparse.ArgumentParser(description="服务器-用户映射管理工具")
    sub = parser.add_subparsers(dest="command")

    sync_parser = sub.add_parser("sync", help="从 JSON 文件导入映射")
    sync_parser.add_argument("--json", default=os.path.join(os.path.dirname(__file__), "servers.json"),
                             help="JSON 文件路径 (默认: 同目录下 servers.json)")

    sub.add_parser("show", help="显示当前映射")
    sub.add_parser("clear", help="清空映射数据")

    args = parser.parse_args()

    if args.command == "sync":
        cmd_sync(args.json)
    elif args.command == "show":
        cmd_show()
    elif args.command == "clear":
        cmd_clear()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
