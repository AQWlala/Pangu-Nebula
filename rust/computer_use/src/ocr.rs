//! OCR 集成骨架
//!
//! 设计目标:
//! - 对无 a11y 树的应用(如游戏、PDF 阅读器)提供文本识别能力
//! - 优先使用 PaddleOCR-rs(中文识别更准确),回退到 tesseract-rs
//! - 输出包含文本、bbox、置信度的结构化结果
//!
//! 骨架状态: 仅声明类型与函数签名,函数体为 TODO。

/// OCR 识别结果项
#[derive(Debug, Clone, Default)]
pub struct OcrItem {
    /// 识别到的文本
    pub text: String,
    /// 文本区域边界框(像素坐标)
    pub bbox: Bbox,
    /// 置信度(0.0-1.0)
    pub confidence: f32,
    /// 检测到的语言
    pub lang: String,
}

/// 边界框(像素坐标)
#[derive(Debug, Clone, Copy, Default)]
pub struct Bbox {
    pub x: u32,
    pub y: u32,
    pub width: u32,
    pub height: u32,
}

impl Bbox {
    /// 中心点坐标
    pub fn center(&self) -> (u32, u32) {
        (self.x + self.width / 2, self.y + self.height / 2)
    }
}

impl OcrItem {
    /// 创建空 OCR 项
    pub fn new(text: impl Into<String>) -> Self {
        Self {
            text: text.into(),
            bbox: Bbox::default(),
            confidence: 0.0,
            lang: String::new(),
        }
    }
}

/// OCR 引擎后端选择
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OcrBackend {
    /// PaddleOCR-rs(中文优先,精度高)
    Paddle,
    /// tesseract-rs(通用,多语言)
    Tesseract,
    /// 自动选择(优先 Paddle,回退 Tesseract)
    Auto,
}

impl Default for OcrBackend {
    fn default() -> Self {
        OcrBackend::Auto
    }
}

/// 对图像执行 OCR 识别(骨架返回空 Vec)
///
/// 参数:
/// - `_image_b64`: 图像 base64 编码
/// - `_lang`: 语言代码(如 "chi_sim"、"eng"、"chi_sim+eng")
/// - `_backend`: OCR 引擎后端
///
/// 返回: OcrItem 列表(骨架返回空)
///
/// 未来实现:
/// 1. base64 解码为字节,用 image::load_from_memory 解码
/// 2. 根据 backend 选择引擎
/// 3. 调用 engine.ocr(image) 获取结果
/// 4. 转换为 OcrItem 列表返回
pub fn recognize(_image_b64: &str, _lang: Option<&str>, _backend: OcrBackend) -> Vec<OcrItem> {
    // TODO: 解码图像,选择后端,执行识别
    Vec::new()
}

/// 检查 OCR 后端是否可用(骨架返回 false)
pub fn is_backend_available(backend: OcrBackend) -> bool {
    match backend {
        OcrBackend::Paddle => false,    // TODO: 检查 paddleocr-rs 是否加载
        OcrBackend::Tesseract => false, // TODO: 检查 tesseract 库与语言数据
        OcrBackend::Auto => false,
    }
}

/// 列出可用的 OCR 语言(骨架返回空 Vec)
pub fn list_available_languages() -> Vec<String> {
    // TODO: 扫描 tesseract tessdata 目录或 paddleocr 模型目录
    Vec::new()
}

/// 在 OCR 结果中查找包含指定文本的项(骨架返回空 Vec)
pub fn find_text<'a>(items: &'a [OcrItem], pattern: &str) -> Vec<&'a OcrItem> {
    items.iter().filter(|item| item.text.contains(pattern)).collect()
}
