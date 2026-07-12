"""语音合成服务 (TTS) - 双模式: 有 edge-tts 走真实合成, 无则降级为 mock"""

import os
import tempfile

# 尝试导入 edge-tts（可选依赖，运行时 try/except）
try:
    import edge_tts  # type: ignore

    _HAS_EDGE_TTS = True
except ImportError:
    edge_tts = None  # type: ignore
    _HAS_EDGE_TTS = False


# mock 模式返回的固定音频字节
_MOCK_TTS_AUDIO = b"mock_tts_audio_data"


async def synthesize(text: str, voice: str = "zh-CN-XiaoxiaoNeural") -> bytes:
    """文字转语音（双模式）

    - 安装了 edge-tts 时调用真实合成
    - 未安装 edge-tts 时返回 mock 音频字节

    Args:
        text: 要合成的文本
        voice: edge-tts 音色名（默认 zh-CN-XiaoxiaoNeural）

    Returns:
        音频字节（mp3 格式）；mock 模式返回 b"mock_tts_audio_data"
    """
    if not text:
        # 空文本时返回 mock 数据，避免 edge-tts 报错
        return _MOCK_TTS_AUDIO

    # 无 edge-tts 时降级为 mock
    if not _HAS_EDGE_TTS:
        return _MOCK_TTS_AUDIO

    # 调用 edge-tts 真实合成
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp3")
    os.close(tmp_fd)
    try:
        try:
            communicate = edge_tts.Communicate(text, voice)  # type: ignore[union-attr]
            await communicate.save(tmp_path)
        except Exception:
            # edge-tts 调用失败时降级为 mock
            return _MOCK_TTS_AUDIO

        with open(tmp_path, "rb") as f:
            audio_bytes = f.read()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if not audio_bytes:
        return _MOCK_TTS_AUDIO

    return audio_bytes


class TTSService:
    """语音合成服务（兼容旧接口，封装模块级 synthesize 函数）

    双模式:
    - 安装了 edge-tts 时调用真实合成
    - 未安装时返回 mock 音频字节
    """

    async def synthesize(
        self,
        text: str,
        voice: str = "zh-CN-XiaoxiaoNeural",
    ) -> bytes:
        """文字转语音（双模式，返回 bytes）

        Args:
            text: 要合成的文本
            voice: 音色（edge-tts 音色名）

        Returns:
            音频字节；mock 模式返回 b"mock_tts_audio_data"
        """
        return await synthesize(text, voice)
