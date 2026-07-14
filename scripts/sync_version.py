#!/usr/bin/env python3
"""Pangu Nebula 版本号同步脚本 (v2.1.0 Phase 0 — P0-W7.5)

tauri.conf.json > version 为单一真相源,
同步到 Cargo.toml + pyproject.toml + frontend/package.json + launch.py

用法:
    python scripts/sync_version.py              # 读取 tauri.conf.json,同步到其他文件
    python scripts/sync_version.py --version 2.1.1  # 设置指定版本号并同步
    python scripts/sync_version.py --check      # 仅检查一致性,不修改文件 (CI 用)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 版本号来源 (单一真相源)
TAURI_CONF = PROJECT_ROOT / "src-tauri" / "tauri.conf.json"

# 同步目标文件
CARGO_TOML = PROJECT_ROOT / "src-tauri" / "Cargo.toml"
PYPROJECT_TOML = PROJECT_ROOT / "pyproject.toml"
FRONTEND_PACKAGE = PROJECT_ROOT / "frontend" / "package.json"
LAUNCH_PY = PROJECT_ROOT / "launch.py"
UPDATE_SERVICE = PROJECT_ROOT / "server" / "services" / "update_service.py"


def read_tauri_version() -> str:
    """从 tauri.conf.json 读取版本号"""
    content = TAURI_CONF.read_text(encoding="utf-8")
    config = json.loads(content)
    version = config.get("version")
    if not version:
        raise ValueError(f"version field not found in {TAURI_CONF}")
    return version


def write_tauri_version(version: str) -> None:
    """写入版本号到 tauri.conf.json"""
    content = TAURI_CONF.read_text(encoding="utf-8")
    config = json.loads(content)
    config["version"] = version
    TAURI_CONF.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def sync_cargo_toml(version: str, check_only: bool = False) -> tuple[bool, str]:
    """同步 Cargo.toml 中的 version 字段"""
    content = CARGO_TOML.read_text(encoding="utf-8")
    pattern = r'(\[package\][^\[]*?version\s*=\s*)"[^"]+"'
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return False, "version field not found in Cargo.toml"

    current = match.group(0).split('"')[-2]
    if current == version:
        return True, f"Cargo.toml: already {version}"

    if check_only:
        return False, f"Cargo.toml: {current} ≠ {version}"

    new_content = re.sub(
        pattern,
        lambda m: f'{m.group(1)}"{version}"',
        content,
        count=1,
        flags=re.DOTALL,
    )
    CARGO_TOML.write_text(new_content, encoding="utf-8")
    return True, f"Cargo.toml: {current} → {version}"


def sync_pyproject_toml(version: str, check_only: bool = False) -> tuple[bool, str]:
    """同步 pyproject.toml 中的 version 字段"""
    content = PYPROJECT_TOML.read_text(encoding="utf-8")
    pattern = r'(\[project\][^\[]*?version\s*=\s*)"[^"]+"'
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return False, "version field not found in pyproject.toml"

    current = match.group(0).split('"')[-2]
    if current == version:
        return True, f"pyproject.toml: already {version}"

    if check_only:
        return False, f"pyproject.toml: {current} ≠ {version}"

    new_content = re.sub(
        pattern,
        lambda m: f'{m.group(1)}"{version}"',
        content,
        count=1,
        flags=re.DOTALL,
    )
    PYPROJECT_TOML.write_text(new_content, encoding="utf-8")
    return True, f"pyproject.toml: {current} → {version}"


def sync_frontend_package(version: str, check_only: bool = False) -> tuple[bool, str]:
    """同步 frontend/package.json 中的 version 字段"""
    content = FRONTEND_PACKAGE.read_text(encoding="utf-8")
    config = json.loads(content)
    current = config.get("version", "")
    if current == version:
        return True, f"frontend/package.json: already {version}"

    if check_only:
        return False, f"frontend/package.json: {current} ≠ {version}"

    config["version"] = version
    FRONTEND_PACKAGE.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return True, f"frontend/package.json: {current} → {version}"


def sync_launch_py(version: str, check_only: bool = False) -> tuple[bool, str]:
    """同步 launch.py 中的 VERSION 变量"""
    content = LAUNCH_PY.read_text(encoding="utf-8")
    pattern = r'(VERSION\s*=\s*)"[^"]+"'
    match = re.search(pattern, content)
    if not match:
        return False, "VERSION variable not found in launch.py"

    current = match.group(0).split('"')[-2]
    if current == version:
        return True, f"launch.py: already {version}"

    if check_only:
        return False, f"launch.py: {current} ≠ {version}"

    new_content = re.sub(
        pattern,
        lambda m: f'{m.group(1)}"{version}"',
        content,
        count=1,
    )
    LAUNCH_PY.write_text(new_content, encoding="utf-8")
    return True, f"launch.py: {current} → {version}"


def sync_update_service(version: str, check_only: bool = False) -> tuple[bool, str]:
    content = UPDATE_SERVICE.read_text(encoding="utf-8")
    pattern = r'(CURRENT_VERSION\s*=\s*)"[^"]+"'
    match = re.search(pattern, content)
    if not match:
        return False, "CURRENT_VERSION not found in update_service.py"

    current = match.group(0).split('"')[-2]
    if current == version:
        return True, f"update_service.py: already {version}"

    if check_only:
        return False, f"update_service.py: {current} != {version}"

    new_content = re.sub(
        pattern,
        lambda m: f'{m.group(1)}"{version}"',
        content,
        count=1,
    )
    UPDATE_SERVICE.write_text(new_content, encoding="utf-8")
    return True, f"update_service.py: {current} -> {version}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync version across project files (tauri.conf.json as source of truth)"
    )
    parser.add_argument(
        "--version",
        default=None,
        help="Set specific version (default: read from tauri.conf.json)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check-only mode: report inconsistencies without modifying files (CI use)",
    )
    args = parser.parse_args()

    # 确定版本号
    if args.version:
        version = args.version
        if not re.match(r"^\d+\.\d+\.\d+", version):
            print(f"ERROR: Invalid version format: {version}", file=sys.stderr)
            return 1
        if not args.check:
            write_tauri_version(version)
            print(f"tauri.conf.json: set to {version}")
    else:
        version = read_tauri_version()
        print(f"Source: tauri.conf.json version = {version}")

    print(f"Mode: {'check-only' if args.check else 'sync'}")
    print("-" * 50)

    # 同步各文件
    results = [
        sync_cargo_toml(version, check_only=args.check),
        sync_pyproject_toml(version, check_only=args.check),
        sync_frontend_package(version, check_only=args.check),
        sync_launch_py(version, check_only=args.check),
        sync_update_service(version, check_only=args.check),
    ]

    all_ok = True
    for ok, msg in results:
        status = "[OK]" if ok else "[FAIL]"
        print(f"  {status} {msg}")
        if not ok:
            all_ok = False

    print("-" * 50)
    if all_ok:
        print(f"[OK] All files synchronized at version {version}")
        return 0
    else:
        if args.check:
            print(f"[FAIL] Version mismatch detected (expected {version})")
        else:
            print(f"[FAIL] Some files failed to sync")
        return 1


if __name__ == "__main__":
    sys.exit(main())
