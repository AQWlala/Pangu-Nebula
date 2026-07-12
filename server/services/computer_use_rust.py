"""Rust Computer Use 模块的 Python mock 实现

Pangu Nebula v2.0.0 阶段5(T5.2):
Rust 端的 computer_use 模块尚未编译,此处提供 Python mock 作为功能占位。
当 Rust 模块编译完成并安装为 PyO3 扩展后,会自动切换到调用 Rust 实现。

切换机制:
- 检测到 `computer_use` PyO3 模块时,标记 HAS_RUST=True
- 调用时若 HAS_RUST,走真实 Rust 调用路径
- 否则返回 mock 数据,字段结构与未来 Rust 返回值保持一致

模块映射:
- Rust: rust/computer_use/src/lib.rs::get_a11y_tree
- Mock: ComputerUseRust.get_a11y_tree
- Rust: rust/computer_use/src/lib.rs::generate_som_overlay
- Mock: ComputerUseRust.generate_som_overlay
- Rust: rust/computer_use/src/lib.rs::ocr_recognize
- Mock: ComputerUseRust.ocr_recognize
"""

from __future__ import annotations

import json
from typing import Any

# 尝试导入 Rust 编译产物(PyO3 扩展模块)
try:
    import computer_use as _computer_use_rust  # type: ignore

    HAS_RUST = True
    RUST_VERSION: str | None = getattr(_computer_use_rust, "version", lambda: None)()
except ImportError:
    _computer_use_rust = None  # type: ignore
    HAS_RUST = False
    RUST_VERSION = None


class ComputerUseRust:
    """Computer Use Rust 模块的 Python 包装/mock

    提供与未来 Rust 实现一致的接口:
    - get_a11y_tree(): 获取桌面无障碍树
    - generate_som_overlay(screenshot_b64, a11y_json): 生成 SoM 标注图
    - ocr_recognize(image_b64, lang): OCR 识别
    - get_status(): 获取模块状态

    所有方法均返回 {"ok": bool, "data": ..., "error": ...} 统一格式。
    """

    def __init__(self) -> None:
        # 缓存的 a11y 树(mock 模式下用于跨调用共享)
        self._cached_a11y: dict[str, Any] | None = None

    # ===== 状态查询 =====

    def get_status(self) -> dict:
        """获取模块状态"""
        skeleton = False
        if HAS_RUST:
            sk_fn = getattr(_computer_use_rust, "is_skeleton", None)
            if callable(sk_fn):
                skeleton = bool(sk_fn())
        return {
            "rust_available": HAS_RUST,
            "rust_version": RUST_VERSION,
            "skeleton": skeleton,
            "mock": not HAS_RUST,
        }

    # ===== 无障碍树 =====

    async def get_a11y_tree(self) -> dict:
        """获取当前桌面的无障碍树

        返回 data 字段:
        - tree: A11yNode 树(根节点 dict,含 children 列表)
        - mock: 是否为 mock 模式
        """
        if HAS_RUST:
            try:
                tree_json = _computer_use_rust.get_a11y_tree()
                if tree_json:
                    tree = json.loads(tree_json)
                else:
                    tree = None
                return {
                    "ok": True,
                    "data": {"tree": tree, "mock": False},
                    "error": None,
                }
            except Exception as e:
                return {"ok": False, "data": None, "error": f"Rust 调用失败: {e}"}

        # Mock 模式: 返回一个示例 a11y 树,体现未来返回结构
        mock_tree = {
            "node_id": "root",
            "role": "desktop",
            "name": "Desktop",
            "visible": True,
            "actionable": False,
            "enabled": True,
            "bounds": {"x": 0, "y": 0, "width": 1920, "height": 1080},
            "child_ids": ["win-1", "win-2"],
            "children": [
                {
                    "node_id": "win-1",
                    "role": "window",
                    "name": "Notepad",
                    "visible": True,
                    "actionable": True,
                    "enabled": True,
                    "bounds": {"x": 100, "y": 100, "width": 800, "height": 600},
                    "child_ids": ["btn-save", "edit-area"],
                    "children": [
                        {
                            "node_id": "btn-save",
                            "role": "button",
                            "name": "Save",
                            "visible": True,
                            "actionable": True,
                            "enabled": True,
                            "bounds": {"x": 120, "y": 130, "width": 80, "height": 30},
                            "child_ids": [],
                            "children": [],
                        },
                        {
                            "node_id": "edit-area",
                            "role": "edit",
                            "name": "Text Editor",
                            "value": "Hello, world!",
                            "visible": True,
                            "actionable": True,
                            "enabled": True,
                            "bounds": {"x": 120, "y": 180, "width": 760, "height": 500},
                            "child_ids": [],
                            "children": [],
                        },
                    ],
                }
            ],
        }
        self._cached_a11y = mock_tree
        return {
            "ok": True,
            "data": {
                "tree": mock_tree,
                "mock": True,
                "note": "Rust computer_use 模块未编译,返回 mock a11y 树",
            },
            "error": None,
        }

    # ===== SoM 标注 =====

    async def generate_som_overlay(
        self, screenshot_b64: str, a11y_json: str | None = None
    ) -> dict:
        """为截图生成 SoM(Set-of-Mark)标注图

        参数:
        - screenshot_b64: 原始截图 base64
        - a11y_json: 无障碍树 JSON(可选,用于精确标注)

        返回 data 字段:
        - image_b64: 标注后的图像 base64(mock 模式下返回原图)
        - marks: 标注列表 [{mark_id, node_id, label, x, y, width, height}]
        - mock: 是否为 mock 模式
        """
        if HAS_RUST:
            try:
                image_b64 = _computer_use_rust.generate_som_overlay(
                    screenshot_b64, a11y_json
                )
                return {
                    "ok": True,
                    "data": {
                        "image_b64": image_b64,
                        "marks": [],
                        "mock": False,
                    },
                    "error": None,
                }
            except Exception as e:
                return {"ok": False, "data": None, "error": f"Rust 调用失败: {e}"}

        # Mock 模式: 不真正绘制,但根据缓存的 a11y 树生成示例 marks
        marks: list[dict[str, Any]] = []
        if a11y_json:
            try:
                tree = json.loads(a11y_json)
                _collect_actionable_mock(tree, marks, [1])
            except json.JSONDecodeError:
                pass
        elif self._cached_a11y is not None:
            _collect_actionable_mock(self._cached_a11y, marks, [1])

        return {
            "ok": True,
            "data": {
                "image_b64": screenshot_b64,  # mock 模式直接返回原图
                "marks": marks,
                "mock": True,
                "note": "Rust computer_use 模块未编译,返回未标注截图与 mock marks",
            },
            "error": None,
        }

    # ===== OCR 识别 =====

    async def ocr_recognize(
        self, image_b64: str, lang: str | None = None
    ) -> dict:
        """对图像执行 OCR 识别

        参数:
        - image_b64: 图像 base64 编码
        - lang: 语言代码(如 "chi_sim"、"eng"),None 表示自动检测

        返回 data 字段:
        - items: [{text, bbox, confidence, lang}]
        - mock: 是否为 mock 模式
        """
        if HAS_RUST:
            try:
                items_json = _computer_use_rust.ocr_recognize(image_b64, lang)
                items = json.loads(items_json) if items_json else []
                return {
                    "ok": True,
                    "data": {"items": items, "mock": False},
                    "error": None,
                }
            except Exception as e:
                return {"ok": False, "data": None, "error": f"Rust 调用失败: {e}"}

        # Mock 模式: 返回示例 OCR 结果
        mock_items = [
            {
                "text": "File",
                "bbox": {"x": 10, "y": 5, "width": 40, "height": 20},
                "confidence": 0.98,
                "lang": lang or "auto",
            },
            {
                "text": "Edit",
                "bbox": {"x": 55, "y": 5, "width": 40, "height": 20},
                "confidence": 0.97,
                "lang": lang or "auto",
            },
            {
                "text": "Hello, world!",
                "bbox": {"x": 120, "y": 180, "width": 200, "height": 30},
                "confidence": 0.95,
                "lang": lang or "auto",
            },
        ]
        return {
            "ok": True,
            "data": {
                "items": mock_items,
                "mock": True,
                "note": "Rust computer_use 模块未编译,返回 mock OCR 结果",
            },
            "error": None,
        }


def _collect_actionable_mock(
    node: dict[str, Any], marks: list[dict[str, Any]], next_id: list[int]
) -> None:
    """递归收集 actionable 节点为 SoM mark(mock 辅助函数)"""
    if not isinstance(node, dict):
        return
    if node.get("actionable") and node.get("visible"):
        bounds = node.get("bounds", {})
        marks.append(
            {
                "mark_id": next_id[0],
                "node_id": node.get("node_id", ""),
                "label": f"[{node.get('role', '')}] {node.get('name', '')}",
                "x": bounds.get("x", 0),
                "y": bounds.get("y", 0),
                "width": bounds.get("width", 0),
                "height": bounds.get("height", 0),
            }
        )
        next_id[0] += 1
    for child in node.get("children", []):
        _collect_actionable_mock(child, marks, next_id)


# 模块级单例
computer_use_rust = ComputerUseRust()
