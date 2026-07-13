//! Pangu Nebula Sidecar 完整性校验 (v2.1.0 Phase 0 — P0-W5.1)
//!
//! 职责:
//! 1. 构建时生成 sidecar.sha256 清单 (由 scripts/gen_sidecar_hash.py 完成)
//! 2. Tauri 启动前校验 sidecar 文件哈希,防止篡改
//! 3. 哈希不匹配时拒绝启动 sidecar,emit "sidecar-integrity-failed" 事件
//!
//! 清单格式 (兼容 sha256sum):
//!   <sha256>  <relative_path>
//!   <sha256>  <relative_path>
//!
//! 清单文件位置:
//!   开发模式: 项目根目录 sidecar.sha256
//!   打包模式: Tauri resource 目录 sidecar.sha256

use sha2::{Digest, Sha256};
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use tauri::{AppHandle, Emitter, Manager};

/// 完整性校验结果
#[derive(Debug)]
pub struct IntegrityReport {
    /// 校验的文件总数
    pub total_files: usize,
    /// 校验通过的文件数
    pub verified: usize,
    /// 校验失败的文件列表 (path, expected, actual)
    pub mismatches: Vec<IntegrityMismatch>,
    /// 缺失的文件列表
    pub missing: Vec<String>,
}

/// 哈希不匹配记录
#[derive(Debug)]
pub struct IntegrityMismatch {
    pub path: String,
    pub expected: String,
    pub actual: String,
}

/// 查找 sidecar.sha256 清单文件
///
/// 查找顺序:
/// 1. Tauri resource 目录 (打包模式)
/// 2. 项目根目录 (开发模式, cargo tauri dev)
fn find_manifest(app: &AppHandle) -> Option<PathBuf> {
    // 1. 打包模式: Tauri resource
    if let Some(resource_dir) = app.path().resource_dir().ok() {
        let manifest = resource_dir.join("sidecar.sha256");
        if manifest.exists() {
            return Some(manifest);
        }
    }

    // 2. 开发模式: 项目根目录 (src-tauri/../sidecar.sha256)
    // Cargo manifest dir 在编译时已知
    let dev_manifest = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("sidecar.sha256");
    if dev_manifest.exists() {
        return Some(dev_manifest);
    }

    None
}

/// 解析 sidecar.sha256 清单文件
///
/// 返回 (relative_path, expected_sha256) 列表
fn parse_manifest(manifest_path: &Path) -> Result<Vec<(String, String)>, String> {
    let content = fs::read_to_string(manifest_path)
        .map_err(|e| format!("Failed to read manifest {}: {}", manifest_path.display(), e))?;

    let mut entries = Vec::new();
    for (line_num, line) in content.lines().enumerate() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }

        // 格式: <sha256>  <path> (两个空格分隔,兼容 sha256sum)
        let parts: Vec<&str> = line.splitn(2, |c: char| c.is_whitespace()).collect();
        if parts.len() != 2 {
            return Err(format!(
                "Invalid manifest line {} (expected '<sha256>  <path>')",
                line_num + 1
            ));
        }

        let hash = parts[0].trim().to_string();
        let path = parts[1].trim().to_string();

        if hash.len() != 64 {
            return Err(format!(
                "Invalid SHA-256 hash length at line {}: expected 64, got {}",
                line_num + 1,
                hash.len()
            ));
        }

        entries.push((path, hash));
    }

    Ok(entries)
}

/// 计算文件 SHA-256 哈希
fn compute_file_hash(path: &Path) -> Result<String, String> {
    let mut file = fs::File::open(path)
        .map_err(|e| format!("Failed to open {}: {}", path.display(), e))?;
    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 8192];

    loop {
        let n = file
            .read(&mut buffer)
            .map_err(|e| format!("Failed to read {}: {}", path.display(), e))?;
        if n == 0 {
            break;
        }
        hasher.update(&buffer[..n]);
    }

    Ok(format!("{:x}", hasher.finalize()))
}

/// 解析 sidecar 文件相对路径为绝对路径
///
/// 开发模式: 项目根目录 (src-tauri/..)
/// 打包模式: Tauri resource 目录
fn resolve_sidecar_path(app: &AppHandle, relative: &str) -> Option<PathBuf> {
    // 开发模式
    let dev_path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join(relative);
    if dev_path.exists() {
        return Some(dev_path);
    }

    // 打包模式
    if let Some(resource_dir) = app.path().resource_dir().ok() {
        let pkg_path = resource_dir.join(relative);
        if pkg_path.exists() {
            return Some(pkg_path);
        }
    }

    None
}

/// 执行完整性校验
///
/// 流程:
/// 1. 查找 sidecar.sha256 清单文件
/// 2. 解析清单获取 (path, expected_hash) 列表
/// 3. 逐个计算文件实际哈希并比对
/// 4. 返回 IntegrityReport
///
/// 清单文件不存在时返回 Ok(report) 且 total_files=0 (开发模式跳过校验)
pub fn verify_integrity(app: &AppHandle) -> Result<IntegrityReport, String> {
    let manifest_path = match find_manifest(app) {
        Some(p) => p,
        None => {
            tracing::warn!("sidecar.sha256 manifest not found, skipping integrity check (dev mode)");
            return Ok(IntegrityReport {
                total_files: 0,
                verified: 0,
                mismatches: Vec::new(),
                missing: Vec::new(),
            });
        }
    };

    tracing::info!("Verifying sidecar integrity using {}", manifest_path.display());

    let entries = parse_manifest(&manifest_path)?;
    let total = entries.len();

    let mut verified = 0;
    let mut mismatches = Vec::new();
    let mut missing = Vec::new();

    for (rel_path, expected_hash) in &entries {
        let abs_path = match resolve_sidecar_path(app, rel_path) {
            Some(p) => p,
            None => {
                tracing::error!("Sidecar file missing: {}", rel_path);
                missing.push(rel_path.clone());
                continue;
            }
        };

        match compute_file_hash(&abs_path) {
            Ok(actual_hash) => {
                if actual_hash == *expected_hash {
                    verified += 1;
                    tracing::debug!("Integrity OK: {}", rel_path);
                } else {
                    tracing::error!(
                        "Integrity mismatch: {} (expected {}, got {})",
                        rel_path,
                        expected_hash,
                        actual_hash
                    );
                    mismatches.push(IntegrityMismatch {
                        path: rel_path.clone(),
                        expected: expected_hash.clone(),
                        actual: actual_hash,
                    });
                }
            }
            Err(e) => {
                tracing::error!("Failed to hash {}: {}", rel_path, e);
                missing.push(rel_path.clone());
            }
        }
    }

    let report = IntegrityReport {
        total_files: total,
        verified,
        mismatches,
        missing,
    };

    if report.mismatches.is_empty() && report.missing.is_empty() {
        tracing::info!(
            "Sidecar integrity verified: {}/{} files OK",
            report.verified,
            report.total_files
        );
    } else {
        tracing::error!(
            "Sidecar integrity FAILED: {} OK, {} mismatched, {} missing (of {} total)",
            report.verified,
            report.mismatches.len(),
            report.missing.len(),
            report.total_files
        );
    }

    Ok(report)
}

/// 校验 sidecar 完整性,失败时 emit 事件并返回 false
///
/// 在 spawn_and_wait_ready 之前调用:
/// 1. 调用 verify_integrity()
/// 2. 如果有 mismatch 或 missing,emit "sidecar-integrity-failed" 事件
/// 3. 返回 false 阻止 sidecar 启动
pub fn check_and_emit(app: &AppHandle) -> bool {
    match verify_integrity(app) {
        Ok(report) => {
            if report.total_files == 0 {
                // 开发模式无清单,跳过校验
                return true;
            }

            if report.mismatches.is_empty() && report.missing.is_empty() {
                return true;
            }

            // 校验失败,emit 事件
            let _ = app.emit(
                "sidecar-integrity-failed",
                serde_json::json!({
                    "total": report.total_files,
                    "verified": report.verified,
                    "mismatches": report.mismatches.iter().map(|m| {
                        serde_json::json!({
                            "path": m.path,
                            "expected": m.expected,
                            "actual": m.actual,
                        })
                    }).collect::<Vec<_>>(),
                    "missing": report.missing,
                }),
            );
            false
        }
        Err(e) => {
            tracing::error!("Integrity check error: {}", e);
            let _ = app.emit(
                "sidecar-integrity-failed",
                serde_json::json!({ "error": e }),
            );
            false
        }
    }
}
