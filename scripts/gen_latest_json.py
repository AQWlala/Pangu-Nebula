#!/usr/bin/env python3
"""Pangu Nebula latest.json 生成器 (v2.1.0 Phase 0 — P0-W6.3)

为 Tauri Updater 生成 latest.json 更新清单,上传到 GitHub Release。
Tauri 应用通过 tauri.conf.json 中配置的 endpoints URL 拉取此文件。

用法:
    python scripts/gen_latest_json.py --version 2.1.0 --notes "Release notes" \\
        --windows-url https://github.com/.../pangu-nebula_2.1.0_x64-setup.exe \\
        --windows-sig ... \\
        --output latest.json

latest.json 格式 (Tauri 2 Updater):
    {
      "version": "2.1.0",
      "notes": "Release notes",
      "pub_date": "2026-07-13T00:00:00Z",
      "platforms": {
        "windows-x86_64": {
          "signature": "...",
          "url": "https://..."
        },
        "darwin-aarch64": { ... },
        "darwin-x86_64": { ... },
        "linux-x86_64": { ... }
      }
    }
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path


def generate_latest_json(
    version: str,
    notes: str,
    pub_date: str,
    platforms: dict,
) -> dict:
    """生成 latest.json 内容"""
    return {
        "version": version,
        "notes": notes,
        "pub_date": pub_date,
        "platforms": platforms,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate latest.json for Tauri Updater"
    )
    parser.add_argument(
        "--version",
        required=True,
        help="Release version (e.g. 2.1.0)",
    )
    parser.add_argument(
        "--notes",
        default="",
        help="Release notes (plain text)",
    )
    parser.add_argument(
        "--pub-date",
        default=None,
        help="Publication date (ISO 8601, default: current UTC time)",
    )
    parser.add_argument(
        "--windows-url",
        default=None,
        help="Windows x86_64 download URL",
    )
    parser.add_argument(
        "--windows-sig",
        default=None,
        help="Windows x86_64 signature (.sig file content)",
    )
    parser.add_argument(
        "--windows-sig-file",
        default=None,
        help="Windows x86_64 signature file path (alternative to --windows-sig)",
    )
    parser.add_argument(
        "--macos-aarch64-url",
        default=None,
        help="macOS ARM64 download URL",
    )
    parser.add_argument(
        "--macos-aarch64-sig-file",
        default=None,
        help="macOS ARM64 signature file path",
    )
    parser.add_argument(
        "--macos-x86_64-url",
        default=None,
        help="macOS Intel download URL",
    )
    parser.add_argument(
        "--macos-x86_64-sig-file",
        default=None,
        help="macOS Intel signature file path",
    )
    parser.add_argument(
        "--linux-url",
        default=None,
        help="Linux x86_64 download URL (AppImage)",
    )
    parser.add_argument(
        "--linux-sig-file",
        default=None,
        help="Linux x86_64 signature file path",
    )
    parser.add_argument(
        "--output",
        default="latest.json",
        help="Output file path (default: latest.json)",
    )
    args = parser.parse_args()

    # 发布日期 (默认当前 UTC)
    pub_date = args.pub_date or datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    # 读取签名文件辅助函数
    def read_sig(sig_file: str | None) -> str | None:
        if not sig_file:
            return None
        return Path(sig_file).read_text(encoding="utf-8").strip()

    # 构建 platforms
    platforms: dict = {}

    if args.windows_url:
        sig = args.windows_sig or read_sig(args.windows_sig_file) or ""
        platforms["windows-x86_64"] = {
            "signature": sig,
            "url": args.windows_url,
        }

    if args.macos_aarch64_url:
        sig = read_sig(args.macos_aarch64_sig_file) or ""
        platforms["darwin-aarch64"] = {
            "signature": sig,
            "url": args.macos_aarch64_url,
        }

    if args.macos_x86_64_url:
        sig = read_sig(args.macos_x86_64_sig_file) or ""
        platforms["darwin-x86_64"] = {
            "signature": sig,
            "url": args.macos_x86_64_url,
        }

    if args.linux_url:
        sig = read_sig(args.linux_sig_file) or ""
        platforms["linux-x86_64"] = {
            "signature": sig,
            "url": args.linux_url,
        }

    if not platforms:
        print("ERROR: At least one platform URL is required", file=sys.stderr)
        return 1

    # 生成 latest.json
    latest = generate_latest_json(args.version, args.notes, pub_date, platforms)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(latest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Generated {output}")
    print(f"  version: {args.version}")
    print(f"  pub_date: {pub_date}")
    print(f"  platforms: {list(platforms.keys())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
