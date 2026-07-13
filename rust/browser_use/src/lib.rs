//! Browser Use Rust 模块 - 骨架入口
//!
//! 此模块为 Pangu Nebula v2.0.0 阶段5(T5.1)的 Rust 重写骨架。
//! v2.1.0 Phase 0: 改造为双目标 crate (cdylib + rlib)。
//! - `python` feature 启用: 编译为 cdylib,通过 PyO3 暴露到 Python
//! - 默认 (无 feature): 编译为 rlib,可供 Tauri 主进程链接
//!
//! 设计目标:
//! - 用 CDP(Chrome DevTools Protocol)替代 Playwright Python,降低内存占用
//! - ARIA 树监听,提供更稳定的元素定位(不依赖易变的 CSS selector)
//! - 异步 tokio runtime,与 Python asyncio 协同
//!
//! 当前状态: 仅骨架,函数体为 TODO 占位,返回 Ok(false)/空集合。

// cdp 和 aria 子模块不依赖 PyO3,始终编译
mod cdp;
mod aria;

// PyO3 绑定仅在 python feature 启用时编译
#[cfg(feature = "python")]
use pyo3::prelude::*;

/// CDP 连接入口 - 连接到 Chromium DevTools Protocol
///
/// 参数:
/// - `_url`: CDP websocket URL(例如 ws://127.0.0.1:9222/devtools/browser/...)
///
/// 返回: true 表示连接成功,false 表示失败(骨架始终返回 false)
#[cfg(feature = "python")]
#[pyfunction]
fn cdp_connect(_url: &str) -> PyResult<bool> {
    // TODO: 实现 CDP websocket 握手与协议初始化
    // 参考 chromiumoxide::Browser::launch / connect
    Ok(false)
}

/// ARIA 监听 - 订阅页面的 ARIA 可访问性树变更
///
/// 参数:
/// - `_page_id`: 目标页面 ID(由 cdp_connect 返回)
///
/// 返回: ARIA 元素描述列表(骨架返回空 Vec)
#[cfg(feature = "python")]
#[pyfunction]
fn aria_listen(_page_id: &str) -> PyResult<Vec<String>> {
    // TODO: 调用 cdp::listen_aria 并将事件转换为字符串列表
    Ok(vec![])
}

/// 模块版本信息
#[cfg(feature = "python")]
#[pyfunction]
fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

/// 是否为骨架模式(未实现真实逻辑)
#[cfg(feature = "python")]
#[pyfunction]
fn is_skeleton() -> bool {
    true
}

/// PyO3 模块入口 (仅 python feature 启用时编译)
#[cfg(feature = "python")]
#[pymodule]
fn browser_use(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(cdp_connect, m)?)?;
    m.add_function(wrap_pyfunction!(aria_listen, m)?)?;
    m.add_function(wrap_pyfunction!(version, m)?)?;
    m.add_function(wrap_pyfunction!(is_skeleton, m)?)?;
    m.add("__doc__", "Browser Use Rust 模块骨架(PyO3)")?;
    Ok(())
}
