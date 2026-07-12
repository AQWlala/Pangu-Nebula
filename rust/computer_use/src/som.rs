//! SoM(Set-of-Mark) overlay 骨架
//!
//! SoM 方法: 在屏幕截图上为每个可交互元素绘制编号框,
//! 让视觉 LLM 通过引用编号来指定目标元素,避免坐标误识别。
//!
//! 设计参考: Microsoft SoM 论文、Anthropic Computer Use
//!
//! 骨架状态: 仅声明类型与函数签名,函数体为 TODO。

use crate::a11y::A11yNode;

/// SoM 标注元素 - 截图上的一个编号框
#[derive(Debug, Clone, Default)]
pub struct SomMark {
    /// 元素编号(从 1 开始)
    pub mark_id: u32,
    /// 对应的 a11y 节点 ID
    pub node_id: String,
    /// 边界框(屏幕坐标)
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
    /// 角色简短描述(供 LLM 阅读)
    pub label: String,
}

impl SomMark {
    /// 中心点坐标
    pub fn center(&self) -> (f64, f64) {
        (self.x + self.width / 2.0, self.y + self.height / 2.0)
    }
}

/// SoM 标注结果 - 包含标注列表与渲染后的图像
#[derive(Debug, Clone, Default)]
pub struct SomOverlay {
    /// 标注列表
    pub marks: Vec<SomMark>,
    /// 渲染后的图像 base64(骨架返回空)
    pub image_b64: String,
    /// 原始截图尺寸
    pub width: u32,
    pub height: u32,
}

/// 为截图生成 SoM 标注
///
/// 参数:
/// - `_screenshot_b64`: 原始截图 base64
/// - `a11y_root`: 无障碍树根节点(若提供,则只标注 a11y 节点)
///
/// 返回: SomOverlay(骨架返回空 marks 与空 image_b64)
///
/// 未来实现:
/// 1. 解码截图为 image::DynamicImage
/// 2. 若提供 a11y_root,递归收集 actionable 节点;否则使用 OCR 检测文本块
/// 3. 为每个元素分配 mark_id,在图像上绘制编号框(用不同颜色区分 role)
/// 4. 编码回 base64 返回
pub fn overlay(_screenshot_b64: &str, a11y_root: Option<&A11yNode>) -> SomOverlay {
    let mut result = SomOverlay::default();
    if let Some(root) = a11y_root {
        // 递归收集 actionable 节点
        collect_actionable(root, &mut result.marks, &mut 1u32);
    }
    // TODO: 解码图像,绘制编号框,编码回 base64
    result
}

/// 递归收集 actionable 节点为 SomMark(内部辅助)
fn collect_actionable(node: &A11yNode, marks: &mut Vec<SomMark>, next_id: &mut u32) {
    if node.actionable && node.visible {
        marks.push(SomMark {
            mark_id: *next_id,
            node_id: node.node_id.clone(),
            x: node.bounds.x,
            y: node.bounds.y,
            width: node.bounds.width,
            height: node.bounds.height,
            label: format!("[{}] {}", node.role, node.name),
        });
        *next_id += 1;
    }
    // 递归子节点(骨架不递归,因 a11y_root 在骨架下为空)
    // TODO: 实现 child_ids 解析与递归
}

/// 根据 mark_id 查找对应的节点 ID(骨架返回 None)
pub fn find_mark_by_id(overlay: &SomOverlay, mark_id: u32) -> Option<&SomMark> {
    overlay.marks.iter().find(|m| m.mark_id == mark_id)
}

/// 根据 LLM 输出的 mark_id 列表执行点击(骨架返回错误)
pub fn click_marks(_overlay: &SomOverlay, _mark_ids: &[u32]) -> Result<(), String> {
    // TODO: 对每个 mark_id 查找节点,计算中心坐标,调用 enigo::mouse_click
    Err("SoM click_marks 尚未实现(skeleton)".to_string())
}
