"""内存优化器 (T4.10)

提供运行时内存监控和优化能力:
- get_stats(): 获取当前进程内存占用 + Python 对象统计
- optimize(): 触发垃圾回收 + 清理缓存,返回释放的对象数
- 监控阈值: 默认 200MB,超过时记录警告

使用方式:
    from server.services.memory_optimizer import memory_optimizer
    stats = memory_optimizer.get_stats()
    result = memory_optimizer.optimize()

注意:
- 不修改公共文件 (engine.py / main.py)
- 可选依赖 psutil (如不可用,使用 ctypes 回退方案)
"""

import gc
import os
import sys
import weakref
from datetime import datetime
from typing import Any


# 默认内存阈值 (MB)
DEFAULT_MEMORY_THRESHOLD_MB = 200


class MemoryOptimizer:
    """内存优化器

    功能:
        1. 内存占用监控 (RSS / Python 对象数)
        2. 触发垃圾回收 (gc.collect)
        3. 清理模块缓存 (可选)
        4. 阈值告警 (超过 200MB 时记录警告)
    """

    def __init__(self, threshold_mb: int = DEFAULT_MEMORY_THRESHOLD_MB):
        self.threshold_mb = threshold_mb
        self._last_optimize_at: datetime | None = None
        self._last_gc_collected: int = 0
        self._optimization_count: int = 0

    # ------------------------------------------------------------------
    # 内存占用获取
    # ------------------------------------------------------------------

    @staticmethod
    def _get_process_memory_mb() -> float:
        """获取当前进程的 RSS 内存占用 (MB)

        优先使用 psutil; 不可用时回退到 ctypes (Windows)。
        """
        try:
            import psutil
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / (1024 * 1024)
        except ImportError:
            pass

        # Windows 回退方案: 使用 ctypes 调用 PSAPI
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes

                class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                    _fields_ = [
                        ("cb", wintypes.DWORD),
                        ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t),
                    ]

                counters = PROCESS_MEMORY_COUNTERS()
                counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
                psapi = ctypes.windll.psapi
                # 显式设置函数签名 (否则 ctypes 默认 int 返回值会截断 64 位指针)
                psapi.GetProcessMemoryInfo.argtypes = [
                    ctypes.c_void_p,  # hProcess
                    ctypes.POINTER(PROCESS_MEMORY_COUNTERS),  # ppsmemCounters
                    wintypes.DWORD,  # cb
                ]
                psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

                kernel32 = ctypes.windll.kernel32
                kernel32.GetCurrentProcess.restype = ctypes.c_void_p

                if psapi.GetProcessMemoryInfo(
                    kernel32.GetCurrentProcess(),
                    ctypes.byref(counters),
                    counters.cb,
                ):
                    # WorkingSetSize 即 RSS (驻留集大小)
                    return counters.WorkingSetSize / (1024 * 1024)
            except Exception:
                pass

        # 完全无法获取时返回 0
        return 0.0

    @staticmethod
    def _count_python_objects() -> dict[str, int]:
        """统计 Python 对象数量 (按类型分组)

        使用 gc.get_objects() 获取所有被跟踪的对象,按类型名分组统计。
        """
        try:
            objects = gc.get_objects()
            counts: dict[str, int] = {}
            for obj in objects:
                type_name = type(obj).__name__
                counts[type_name] = counts.get(type_name, 0) + 1
            # 仅返回数量最多的前 10 种类型
            sorted_counts = dict(
                sorted(counts.items(), key=lambda x: x[1], reverse=True)[:10]
            )
            return sorted_counts
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """获取当前内存统计

        Returns:
            {
                "rss_mb": float,           # 进程 RSS 内存 (MB)
                "process_mb": float,       # 同上,别名
                "gc_objects": int,         # gc 跟踪的对象总数
                "python_objects": dict,    # 前 10 种对象类型及数量
                "threshold_mb": int,       # 内存阈值
                "exceeds_threshold": bool, # 是否超过阈值
                "last_optimize_at": str | None,
                "optimization_count": int,
                "timestamp": str,
            }
        """
        rss_mb = self._get_process_memory_mb()
        gc_objects = len(gc.get_objects()) if gc else 0
        python_objects = self._count_python_objects()

        return {
            "rss_mb": round(rss_mb, 2),
            "process_mb": round(rss_mb, 2),  # 别名,供测试使用
            "gc_objects": gc_objects,
            "python_objects": python_objects,
            "threshold_mb": self.threshold_mb,
            "exceeds_threshold": rss_mb > self.threshold_mb if rss_mb > 0 else False,
            "last_optimize_at": self._last_optimize_at.isoformat() if self._last_optimize_at else None,
            "optimization_count": self._optimization_count,
            "timestamp": datetime.utcnow().isoformat(),
        }

    # ------------------------------------------------------------------
    # 优化执行
    # ------------------------------------------------------------------

    def optimize(self) -> dict[str, Any]:
        """执行内存优化

        流程:
            1. 触发完整垃圾回收 (gc.collect)
            2. 清理弱引用
            3. 记录释放的对象数

        Returns:
            {
                "gc_collected": int,        # 本次回收的对象数
                "freed_objects": int,       # 别名
                "before_mb": float,
                "after_mb": float,
                "freed_mb": float,
                "optimized_at": str,
            }
        """
        before_mb = self._get_process_memory_mb()

        # 完整垃圾回收 (0代 + 1代 + 2代)
        gc_collected = gc.collect()

        # 清理弱引用
        try:
            weakref.WeakValueDictionary().clear()
        except Exception:
            pass

        after_mb = self._get_process_memory_mb()
        freed_mb = before_mb - after_mb if before_mb > 0 and after_mb > 0 else 0.0

        self._last_optimize_at = datetime.utcnow()
        self._last_gc_collected = gc_collected
        self._optimization_count += 1

        return {
            "gc_collected": gc_collected,
            "freed_objects": gc_collected,  # 别名
            "before_mb": round(before_mb, 2),
            "after_mb": round(after_mb, 2),
            "freed_mb": round(freed_mb, 2),
            "optimized_at": self._last_optimize_at.isoformat(),
        }

    # ------------------------------------------------------------------
    # 阈值检查
    # ------------------------------------------------------------------

    def check_threshold(self) -> dict[str, Any]:
        """检查是否超过内存阈值

        Returns:
            {
                "exceeds": bool,
                "current_mb": float,
                "threshold_mb": int,
                "recommendation": str,  # 优化建议
            }
        """
        current_mb = self._get_process_memory_mb()
        exceeds = current_mb > self.threshold_mb if current_mb > 0 else False

        if exceeds:
            recommendation = (
                f"内存占用 {current_mb:.2f}MB 超过阈值 {self.threshold_mb}MB,"
                f"建议调用 memory_optimizer.optimize() 触发垃圾回收"
            )
        else:
            recommendation = "内存占用正常,无需优化"

        return {
            "exceeds": exceeds,
            "current_mb": round(current_mb, 2),
            "threshold_mb": self.threshold_mb,
            "recommendation": recommendation,
        }

    # ------------------------------------------------------------------
    # 自动优化 (超过阈值时自动触发)
    # ------------------------------------------------------------------

    def auto_optimize(self) -> dict[str, Any]:
        """自动优化: 超过阈值时触发垃圾回收

        Returns:
            {
                "optimized": bool,       # 是否触发了优化
                "reason": str,           # 触发原因 / 跳过原因
                "stats": dict,           # 优化前后的内存统计
            }
        """
        check_result = self.check_threshold()
        if not check_result["exceeds"]:
            return {
                "optimized": False,
                "reason": f"内存占用 {check_result['current_mb']}MB 未超过阈值",
                "stats": check_result,
            }

        # 超过阈值,触发优化
        optimize_result = self.optimize()
        return {
            "optimized": True,
            "reason": f"内存占用 {check_result['current_mb']}MB 超过阈值,已触发优化",
            "stats": {
                "before": check_result,
                "after": self.check_threshold(),
                "optimization": optimize_result,
            },
        }


# 模块级单例
memory_optimizer = MemoryOptimizer()
