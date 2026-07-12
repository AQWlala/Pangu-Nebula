//! 无障碍树(a11y tree)骨架
//!
//! 设计参考:
//! - accesskit: Rust 跨平台 a11y 框架
//! - Windows: uiautomation crate (UI Automation API)
//! - macOS: accessibility-sys
//! - Linux: atspi
//!
//! 骨架状态: 仅声明类型与函数签名,函数体为 TODO。

/// 无障碍树节点 - 跨平台抽象
#[derive(Debug, Clone, Default)]
pub struct A11yNode {
    /// 节点唯一 ID(运行时分配)
    pub node_id: String,
    /// 角色(button、text、window、menu 等,平台相关)
    pub role: String,
    /// 可读名称
    pub name: String,
    /// 节点值(如文本框内容、滑块位置)
    pub value: String,
    /// 节点描述
    pub description: String,
    /// 是否可见
    pub visible: bool,
    /// 是否可操作
    pub actionable: bool,
    /// 是否启用
    pub enabled: bool,
    /// 屏幕坐标与尺寸
    pub bounds: Bounds,
    /// 父节点 ID
    pub parent_id: Option<String>,
    /// 子节点 ID 列表
    pub child_ids: Vec<String>,
    /// 平台原生属性(Windows: automationId、ariaRole 等)
    pub native_properties: std::collections::HashMap<String, String>,
}

/// 节点边界框
#[derive(Debug, Clone, Copy, Default)]
pub struct Bounds {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

impl Bounds {
    /// 中心点坐标
    pub fn center(&self) -> (f64, f64) {
        (self.x + self.width / 2.0, self.y + self.height / 2.0)
    }

    /// 是否包含某点
    pub fn contains(&self, x: f64, y: f64) -> bool {
        x >= self.x && x <= self.x + self.width && y >= self.y && y <= self.y + self.height
    }
}

impl A11yNode {
    /// 创建空节点
    pub fn new(node_id: impl Into<String>, role: impl Into<String>) -> Self {
        Self {
            node_id: node_id.into(),
            role: role.into(),
            name: String::new(),
            value: String::new(),
            description: String::new(),
            visible: true,
            actionable: false,
            enabled: true,
            bounds: Bounds::default(),
            parent_id: None,
            child_ids: Vec::new(),
            native_properties: std::collections::HashMap::new(),
        }
    }

    /// 转换为简短描述(供 LLM 阅读)
    pub fn to_description(&self) -> String {
        let action = if self.actionable { "Y" } else { "N" };
        let vis = if self.visible { "Y" } else { "N" };
        format!(
            "[{}] {} value='{}' (actionable={} visible={} enabled={})",
            self.role, self.name, self.value, action, vis, self.enabled
        )
    }
}

/// 获取桌面的 a11y 根节点(骨架返回 None)
///
/// 未来实现:
/// - Windows: uiautomation::UIElement::focused_element 或 root_element
/// - macOS: accessibility-sys 的 AXUIElementCopyAttributeValue
/// - Linux: atspi 的 get_root
pub fn get_root_node() -> Option<A11yNode> {
    // TODO: 平台分支,获取桌面根节点并递归构建子树
    None
}

/// 查找当前焦点元素(骨架返回 None)
pub fn get_focused_node() -> Option<A11yNode> {
    // TODO: 调用平台 API 获取焦点元素
    None
}

/// 按 role 查找节点(骨架返回空 Vec)
pub fn find_by_role(_root: &A11yNode, _role: &str) -> Vec<A11yNode> {
    // TODO: 递归查找
    Vec::new()
}

/// 按名称查找节点(骨架返回空 Vec)
pub fn find_by_name(_root: &A11yNode, _name: &str) -> Vec<A11yNode> {
    // TODO: 模糊匹配 name 字段
    Vec::new()
}

/// 触发节点动作(点击/聚焦/选择)(骨架返回错误)
///
/// 参数:
/// - `_node_id`: 目标节点 ID
/// - `_action`: 动作类型(click/focus/select/value)
/// - `_value`: 可选值(用于 value 动作)
pub fn invoke_action(_node_id: &str, _action: &str, _value: Option<&str>) -> Result<(), String> {
    // TODO: 查找节点并调用平台 invoke / set_value / select
    Err("a11y invoke_action 尚未实现(skeleton)".to_string())
}
