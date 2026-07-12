//! ARIA(可访问性树)监听骨架
//!
//! 设计目标:
//! - 取代易变的 CSS selector,使用 ARIA 角色定位元素
//! - 通过 CDP Accessibility 域订阅 AXTreeUpdated 事件
//! - 输出简化的元素描述,供 LLM 决策
//!
//! 骨架状态: 仅声明类型与函数签名,函数体为 TODO。

/// ARIA 元素节点 - 简化的可访问性树节点
///
/// 对应 CDP AXNode 的子集字段。
#[derive(Debug, Clone, Default)]
pub struct AriaNode {
    /// 节点 ID(CDP 内部 id)
    pub node_id: String,
    /// ARIA 角色(如 button、link、textbox、menuitem)
    pub role: String,
    /// 可读名称(由 aria-label 或子文本计算)
    pub name: String,
    /// 节点值(如文本框内容)
    pub value: String,
    /// 是否可操作(可点击/可编辑)
    pub actionable: bool,
    /// 是否可见
    pub visible: bool,
    /// 父节点 ID(根节点为空)
    pub parent_id: Option<String>,
    /// 子节点 ID 列表
    pub child_ids: Vec<String>,
    /// 屏幕坐标与尺寸(由 DOM.getBoxModel 填充)
    pub bounding_box: Option<BoundingBox>,
}

/// 元素包围盒 - 用于点击坐标计算
#[derive(Debug, Clone, Copy, Default)]
pub struct BoundingBox {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

impl BoundingBox {
    /// 计算中心点坐标(用于点击)
    pub fn center(&self) -> (f64, f64) {
        (self.x + self.width / 2.0, self.y + self.height / 2.0)
    }
}

impl AriaNode {
    /// 创建空的 ARIA 节点
    pub fn new(node_id: impl Into<String>, role: impl Into<String>) -> Self {
        Self {
            node_id: node_id.into(),
            role: role.into(),
            name: String::new(),
            value: String::new(),
            actionable: false,
            visible: true,
            parent_id: None,
            child_ids: Vec::new(),
            bounding_box: None,
        }
    }

    /// 转换为简短描述字符串(供 LLM 阅读)
    ///
    /// 格式: `[role] name (actionable=Y visible=Y)`
    pub fn to_description(&self) -> String {
        let action = if self.actionable { "Y" } else { "N" };
        let vis = if self.visible { "Y" } else { "N" };
        format!("[{}] {} (actionable={} visible={})", self.role, self.name, action, vis)
    }

    /// 是否为可点击的交互元素
    pub fn is_clickable(&self) -> bool {
        matches!(
            self.role.as_str(),
            "button" | "link" | "menuitem" | "tab" | "checkbox" | "radio" | "option"
        )
    }

    /// 是否为可输入的文本元素
    pub fn is_editable(&self) -> bool {
        matches!(self.role.as_str(), "textbox" | "searchbox" | "combobox" | "spinbutton")
    }
}

/// 将 ARIA 树扁平化为元素描述字符串列表(骨架返回空)
///
/// 未来实现:
/// 1. 递归遍历 ARIA 树
/// 2. 仅保留 actionable=true 的节点
/// 3. 按 DOM 顺序输出描述字符串
pub fn flatten_aria_tree(_root: &AriaNode) -> Vec<String> {
    // TODO: 递归遍历,过滤 actionable 节点,调用 to_description
    Vec::new()
}

/// 根据 ARIA 角色查找元素(骨架返回空)
pub fn find_by_role(_root: &AriaNode, _role: &str) -> Vec<AriaNode> {
    // TODO: 递归查找所有匹配角色的节点
    Vec::new()
}

/// 根据可读名称查找元素(骨架返回空)
pub fn find_by_name(_root: &AriaNode, _name_pattern: &str) -> Vec<AriaNode> {
    // TODO: 模糊匹配 name 字段(支持子串与正则)
    Vec::new()
}
