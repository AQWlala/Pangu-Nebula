//! Computer Use Rust 模块 - 骨架入口
//!
//! 此模块为 Pangu Nebula v2.0.0 阶段5(T5.2)的 Rust 重写骨架。
//! 实际功能在 Python 端由 `server/services/computer_use_rust.py` mock 提供,
//! 待 Rust 编译链就绪后,通过 PyO3 暴露到 Python。
//!
//! 设计目标:
//! - 通过 accesskit/uiautomation 获取跨平台无障碍树
//! - SoM(Set-of-Mark) overlay 标注屏幕元素,供视觉 LLM 决策
//! - OCR 集成(tesseract-rs / PaddleOCR-rs)处理无 a11y 树的应用
//! - enigo 实现键盘/鼠标输入模拟
//!
//! 当前状态: 仅骨架,函数体为 TODO 占位,返回 Ok(false)/空集合。

use pyo3::prelude::*;

mod a11y;
mod som;
mod ocr;

/// 获取当前桌面的无障碍树根节点
///
/// 返回: A11yNode 的 JSON 字符串(骨架返回空字符串)
#[pyfunction]
fn get_a11y_tree() -> PyResult<String> {
    // TODO: 调用 a11y::get_root_node 并序列化为 JSON
    Ok(String::new())
}

/// 生成 SoM(Set-of-Mark) overlay 图像
///
/// 参数:
/// - `_screenshot_b64`: 截图 base64 编码
/// - `_a11y_json`: 无障碍树 JSON(可选)
///
/// 返回: 标注后的图像 base64(骨架返回空字符串)
#[pyfunction(signature = (_screenshot_b64, _a11y_json=None))]
fn generate_som_overlay(_screenshot_b64: &str, _a11y_json: Option<&str>) -> PyResult<String> {
    // TODO: 调用 som::overlay,在截图上绘制编号框
    Ok(String::new())
}

/// 对截图执行 OCR 识别
///
/// 参数:
/// - `_image_b64`: 图像 base64 编码
/// - `_lang`: 语言代码(如 chi_sim、eng)
///
/// 返回: 识别到的文本列表 JSON(骨架返回 "[]")
#[pyfunction(signature = (_image_b64, _lang=None))]
fn ocr_recognize(_image_b64: &str, _lang: Option<&str>) -> PyResult<String> {
    // TODO: 调用 ocr::recognize,返回 [{text, bbox, confidence}]
    Ok("[]".to_string())
}

/// 模块版本信息
#[pyfunction]
fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

/// 是否为骨架模式(未实现真实逻辑)
#[pyfunction]
fn is_skeleton() -> bool {
    true
}

/// PyO3 模块入口
#[pymodule]
fn computer_use(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(get_a11y_tree, m)?)?;
    m.add_function(wrap_pyfunction!(generate_som_overlay, m)?)?;
    m.add_function(wrap_pyfunction!(ocr_recognize, m)?)?;
    m.add_function(wrap_pyfunction!(version, m)?)?;
    m.add_function(wrap_pyfunction!(is_skeleton, m)?)?;
    m.add("__doc__", "Computer Use Rust 模块骨架(PyO3)")?;
    Ok(())
}
