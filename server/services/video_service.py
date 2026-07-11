"""视频分析服务 - 使用 ffmpeg 抽帧 + 多模态 LLM 分析"""

import base64
import json
import os
import shutil
import subprocess
import tempfile

from sqlalchemy import select

from ..db.engine import async_session
from ..db.orm import Persona
from ..providers.base import Message as ProviderMessage
from ..providers.registry import get_provider, is_registered
from .vision_service import VisionService


class VideoService:
    """视频分析服务，通过 ffmpeg 抽取关键帧后调用视觉识别"""

    def __init__(self):
        self.vision = VisionService()

    async def analyze_video(
        self,
        persona_id: int | None,
        video_base64: str | None = None,
        video_path: str | None = None,
        prompt: str = "请分析这个视频的内容",
        max_frames: int = 10,
        model_name: str | None = None,
    ) -> dict:
        """视频分析：抽取关键帧 → 逐帧识别 → LLM 汇总

        Args:
            persona_id: Persona ID
            video_base64: base64 编码的视频（小文件）
            video_path: 视频文件路径（大文件）
            prompt: 分析提示词
            max_frames: 抽取的最大帧数
            model_name: 模型名

        Returns:
            {"summary": "...", "frames_analyzed": N, "frame_descriptions": [...]}
        """
        if not video_base64 and not video_path:
            raise ValueError("必须提供 video_base64 或 video_path")

        # 检查 ffmpeg 是否可用
        if not self._check_ffmpeg():
            raise ValueError("ffmpeg 不可用，无法抽取视频帧")

        tmp_video_path: str | None = None
        tmp_dir: str | None = None

        try:
            # 获取视频文件路径
            if video_path:
                if not os.path.exists(video_path):
                    raise ValueError(f"视频文件不存在: {video_path}")
                source_path = video_path
            else:
                # 解码 base64 视频到临时文件
                raw_base64 = video_base64
                if video_base64.startswith("data:") and "," in video_base64:
                    raw_base64 = video_base64.split(",", 1)[1]
                try:
                    video_bytes = base64.b64decode(raw_base64)
                except Exception as exc:
                    raise ValueError("无效的 base64 视频数据") from exc

                tmp_fd, tmp_video_path = tempfile.mkstemp(suffix=".mp4")
                with os.fdopen(tmp_fd, "wb") as f:
                    f.write(video_bytes)
                source_path = tmp_video_path

            # 创建临时目录存放帧
            tmp_dir = tempfile.mkdtemp(prefix="nebula_frames_")

            # 抽取关键帧
            frame_paths = await self.extract_frames(
                source_path, max_frames, tmp_dir
            )

            if not frame_paths:
                raise ValueError("无法从视频中抽取帧")

            # 对每个帧调用视觉识别
            frame_descriptions: list[dict] = []
            for i, frame_path in enumerate(frame_paths):
                # 读取帧文件并转 base64
                with open(frame_path, "rb") as f:
                    frame_bytes = f.read()
                frame_b64 = base64.b64encode(frame_bytes).decode("utf-8")

                frame_prompt = f"这是视频的第 {i + 1}/{len(frame_paths)} 帧。请简要描述这一帧的内容。"
                try:
                    result = await self.vision.analyze_image(
                        persona_id=persona_id,
                        image_base64=frame_b64,
                        prompt=frame_prompt,
                        model_name=model_name,
                    )
                    description = result.get("description", "")
                except Exception as exc:
                    description = f"帧 {i + 1} 识别失败: {exc}"

                frame_descriptions.append(
                    {
                        "frame_index": i + 1,
                        "description": description,
                    }
                )

            # 调用 LLM 汇总所有帧描述
            summary = await self._summarize_frames(
                persona_id, prompt, frame_descriptions, model_name
            )

            return {
                "summary": summary,
                "frames_analyzed": len(frame_descriptions),
                "frame_descriptions": frame_descriptions,
            }
        finally:
            # 清理临时文件
            if tmp_video_path and os.path.exists(tmp_video_path):
                try:
                    os.unlink(tmp_video_path)
                except OSError:
                    pass
            if tmp_dir and os.path.exists(tmp_dir):
                try:
                    shutil.rmtree(tmp_dir)
                except OSError:
                    pass

    async def extract_frames(
        self, video_path: str, max_frames: int, output_dir: str
    ) -> list[str]:
        """使用 ffmpeg 抽取关键帧

        均匀抽取 max_frames 帧，保存到 output_dir 目录。

        Args:
            video_path: 视频文件路径
            max_frames: 最大帧数
            output_dir: 输出目录

        Returns:
            帧文件路径列表
        """
        # 获取视频时长（秒）
        duration = self._get_video_duration(video_path)
        if duration <= 0:
            return []

        # 计算抽帧间隔
        actual_frames = min(max_frames, max(1, int(duration)))
        if actual_frames <= 0:
            actual_frames = 1

        # 计算 fps：在时长内均匀抽取 actual_frames 帧
        fps = actual_frames / duration

        output_pattern = os.path.join(output_dir, "frame_%04d.png")

        # 使用 ffmpeg 按指定 fps 抽帧
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-vf", f"fps={fps:.6f}",
            "-frames:v", str(actual_frames),
            "-y",
            output_pattern,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError("ffmpeg 抽帧超时") from exc
        except Exception as exc:
            raise ValueError(f"ffmpeg 执行失败: {exc}") from exc

        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace")
            raise ValueError(f"ffmpeg 抽帧失败: {stderr[:500]}")

        # 收集生成的帧文件
        frame_paths: list[str] = []
        for i in range(1, actual_frames + 1):
            frame_file = os.path.join(output_dir, f"frame_{i:04d}.png")
            if os.path.exists(frame_file):
                frame_paths.append(frame_file)

        return frame_paths

    async def _summarize_frames(
        self,
        persona_id: int | None,
        prompt: str,
        frame_descriptions: list[dict],
        model_name: str | None,
    ) -> str:
        """调用 LLM 基于所有帧描述生成视频总结"""
        # 构建 frames 描述文本
        frames_text = "\n".join(
            f"第 {f['frame_index']} 帧: {f['description']}"
            for f in frame_descriptions
        )

        system_prompt = "你是一个视频分析助手。请根据用户提供的各帧描述，生成视频内容的综合分析。"
        user_content = f"{prompt}\n\n以下是视频中抽取的各帧描述：\n\n{frames_text}\n\n请综合以上信息，给出视频内容的总结分析。"

        # 获取 provider 配置
        provider_name = "openai"
        persona_model_name: str | None = None
        temperature = 0.7
        max_tokens = 4096

        if persona_id is not None:
            async with async_session() as session:
                result = await session.execute(
                    select(Persona).where(Persona.id == persona_id)
                )
                persona = result.scalar_one_or_none()
                if persona:
                    provider_name = persona.model_provider or "openai"
                    persona_model_name = persona.model_name
                    temperature = persona.temperature
                    max_tokens = persona.max_tokens

        final_model = model_name or persona_model_name or "gpt-4o-mini"

        if not is_registered(provider_name):
            # 如果没有注册的 provider，直接返回帧描述拼接
            return f"（无法调用 LLM 汇总，provider '{provider_name}' 未注册）\n\n{frames_text}"

        try:
            provider = get_provider(provider_name)
        except ValueError:
            return f"（无法获取 provider，汇总失败）\n\n{frames_text}"

        messages = [
            ProviderMessage(role="system", content=system_prompt),
            ProviderMessage(role="user", content=user_content),
        ]

        chunks: list[str] = []
        try:
            async for chunk in provider.generate(
                messages, final_model, temperature=temperature, max_tokens=max_tokens
            ):
                chunks.append(chunk)
        except Exception as exc:
            return f"（LLM 汇总失败: {exc}）\n\n{frames_text}"

        summary = "".join(chunks).strip()
        if not summary:
            return frames_text

        return summary

    @staticmethod
    def _check_ffmpeg() -> bool:
        """检查 ffmpeg 是否可用"""
        return shutil.which("ffmpeg") is not None

    @staticmethod
    def _get_video_duration(video_path: str) -> float:
        """使用 ffprobe 获取视频时长（秒）"""
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            # 如果 ffprobe 不可用，尝试用 ffmpeg 解析
            ffprobe = "ffprobe"

        cmd = [
            ffprobe,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            video_path,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, timeout=30)
        except Exception:
            return 0.0

        if result.returncode != 0:
            return 0.0

        try:
            data = json.loads(result.stdout.decode("utf-8", errors="replace"))
            duration_str = data.get("format", {}).get("duration", "0")
            return float(duration_str)
        except (json.JSONDecodeError, ValueError, TypeError):
            return 0.0
