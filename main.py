"""智能 TTS 插件

功能：
1. 始终发送文字回复（不受影响）
2. 仅在纯文本（无代码块、表格、HTML 等复杂格式）时额外追加语音组件
3. 支持配置 TTS Provider 和最大文本长度

实现方式：
- 监听 on_decorating_result 事件（消息发送前）
- 判断 LLM 回复的文本格式
- 如果是纯文本，调用 TTS Provider 生成语音并追加到消息链
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.message_components import Plain, Record
from astrbot.api.star import Context, Star, register


@register(
    "astrbot_plugin_smart_tts",
    "RoyougiShiki",
    "智能 TTS - 纯文本时额外发送语音",
    "0.1.2",
)
class SmartTTSPlugin(Star):
    """智能 TTS 插件"""

    # 需要排除的 Markdown / HTML 格式模式
    COMPLEX_PATTERNS = [
        re.compile(r"```[\s\S]*?```"),           # 代码块
        re.compile(r"`[^`]+`"),                   # 行内代码
        re.compile(r"\|[^\n]+\|"),                # 表格行
        re.compile(r"<[^>]+>"),                   # HTML 标签
        re.compile(r"!\[.*?\]\(.*?\)"),          # 图片
        re.compile(r"\[.*?\]\(.*?\)"),           # 链接
        re.compile(r"^#{1,6}\s+", re.MULTILINE),  # 标题
        re.compile(r"^\s*[-*+]\s+", re.MULTILINE),  # 列表项
        re.compile(r"^\s*\d+\.\s+", re.MULTILINE),  # 有序列表
        re.compile(r"^\s*>\s+", re.MULTILINE),    # 引用
        re.compile(r"---\s*$", re.MULTILINE),     # 分隔线
    ]

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.conf = config
        self.tts_provider_id = config.get("tts_provider_id", "")
        self.max_text_length = config.get("max_text_length", 500)

        # Check if reinstall_edge_tts is triggered
        if self.conf.get("reinstall_edge_tts", False):
            self._reinstall_deps()

    def _reinstall_deps(self):
        """重新安装 TTS 所需依赖"""
        logger.info("[SmartTTS] 正在重新安装 TTS 依赖...")

        pip_path = os.path.join(os.path.dirname(sys.executable), "pip.exe")
        if not os.path.exists(pip_path):
            pip_path = os.path.join(os.path.dirname(sys.executable), "pip")

        # 1. Install edge-tts
        logger.info("[SmartTTS] 正在安装 edge-tts...")
        try:
            r = subprocess.run(
                [pip_path, "install", "edge-tts"],
                capture_output=True, text=True, timeout=120
            )
            if r.returncode == 0:
                logger.info("[SmartTTS] edge-tts 安装成功")
            else:
                logger.error(f"[SmartTTS] edge-tts 安装失败: {r.stderr[:200]}")
        except Exception as e:
            logger.error(f"[SmartTTS] edge-tts 安装异常: {e}")

        # 2. Install pilk (try direct install first, fallback to pysilk compat layer)
        logger.info("[SmartTTS] 正在安装 pilk...")
        pilk_installed = False
        try:
            subprocess.run(
                [pip_path, "install", "pilk"],
                capture_output=True, text=True, timeout=120
            )
            # Verify it actually works (can import)
            r2 = subprocess.run(
                [sys.executable, "-c", "import pilk; print('ok')"],
                capture_output=True, text=True, timeout=10
            )
            if "ok" in r2.stdout:
                pilk_installed = True
                logger.info("[SmartTTS] pilk 安装成功")
        except Exception:
            pass

        if not pilk_installed:
            logger.info("[SmartTTS] pilk 直接安装失败，使用 pysilk 兼容层...")
            try:
                # Install pysilk
                r = subprocess.run(
                    [pip_path, "install", "pysilk"],
                    capture_output=True, text=True, timeout=60
                )
                if r.returncode == 0:
                    # Create pilk compatibility wrapper
                    site_packages = os.path.join(os.path.dirname(sys.executable), "..", "Lib", "site-packages")
                    pilk_dir = os.path.join(site_packages, "pilk")
                    os.makedirs(pilk_dir, exist_ok=True)

                    init_content = '''"""pilk compatibility wrapper - delegates to pysilk"""
import os
import io
import pysilk


def encode(input_path, output_path, pcm_rate=24000, tencent=True, **kwargs):
    if isinstance(input_path, (str, bytes, os.PathLike)):
        with open(input_path, 'rb') as fin:
            pcm_data = fin.read()
        input_bio = io.BytesIO(pcm_data)
    else:
        input_bio = input_path

    if isinstance(output_path, (str, bytes, os.PathLike)):
        output_bio = io.BytesIO()
    else:
        output_bio = output_path

    pysilk.encode(
        input_bio,
        output_bio,
        pcm_rate,
        pcm_rate,
        tencent=tencent,
    )

    if isinstance(output_path, (str, bytes, os.PathLike)):
        with open(output_path, 'wb') as fout:
            fout.write(output_bio.getvalue())

    try:
        duration = get_duration(output_path if isinstance(output_path, (str, bytes, os.PathLike)) else output_bio.getvalue())
    except Exception:
        duration = len(pcm_data) / (pcm_rate * 2) * 1000

    return int(duration)


def decode(input_path, output_path, pcm_rate=24000):
    if isinstance(input_path, (str, bytes, os.PathLike)):
        with open(input_path, 'rb') as fin:
            silk_data = fin.read()
        input_bio = io.BytesIO(silk_data)
    else:
        input_bio = input_path

    if isinstance(output_path, (str, bytes, os.PathLike)):
        output_bio = io.BytesIO()
    else:
        output_bio = output_path

    pysilk.decode(input_bio, output_bio, pcm_rate)

    if isinstance(output_path, (str, bytes, os.PathLike)):
        with open(output_path, 'wb') as fout:
            fout.write(output_bio.getvalue())


def get_duration(silk_path, frame_ms=20):
    if isinstance(silk_path, (str, bytes, os.PathLike)):
        with open(silk_path, 'rb') as f:
            data = f.read()
    elif isinstance(silk_path, bytes):
        data = silk_path
    else:
        data = silk_path.read() if hasattr(silk_path, 'read') else silk_path

    if data.startswith(b'#!SILK_V3'):
        data = data[9:]

    duration_ms = 0
    offset = 0
    while offset < len(data) - 1:
        if offset + 2 > len(data):
            break
        frame_size = data[offset] + data[offset + 1] * 16
        if frame_size <= 0 or offset + 2 + frame_size > len(data):
            break
        offset += 2 + frame_size
        duration_ms += frame_ms

    return duration_ms
'''

                    init_path = os.path.join(pilk_dir, '__init__.py')
                    with open(init_path, 'w', encoding='utf-8') as f:
                        f.write(init_content)

                    # Verify
                    r3 = subprocess.run(
                        [sys.executable, "-c", "import pilk; print('ok')"],
                        capture_output=True, text=True, timeout=10
                    )
                    if "ok" in r3.stdout:
                        logger.info("[SmartTTS] pilk 兼容层（基于 pysilk）安装成功")
                        pilk_installed = True
                    else:
                        logger.error(f"[SmartTTS] pilk 兼容层创建失败: {r3.stderr[:200]}")
            except Exception as e:
                logger.error(f"[SmartTTS] pilk 兼容层安装异常: {e}")

        if pilk_installed:
            logger.info("[SmartTTS] 所有依赖安装完成！请重启 AstrBot 使其生效。")
        else:
            logger.warning("[SmartTTS] pilk 安装失败，QQ 语音发送可能异常")

        # Auto-reset the switch
        self.conf["reinstall_edge_tts"] = False

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent) -> None:
        """在消息发送前，判断是否需要追加语音"""
        result = event.get_result()
        if result is None or not result.chain:
            return

        # 只对 LLM 回复处理
        if not result.is_llm_result():
            return

        # 提取纯文本内容
        text = ""
        for comp in result.chain:
            if isinstance(comp, Plain):
                text += comp.text

        if not text.strip():
            return

        text = text.strip()

        # 判断是否为纯文本
        if not self._is_plain_text(text):
            logger.debug("[SmartTTS] 检测到复杂格式，跳过语音")
            return

        # 检查长度限制
        if len(text) > self.max_text_length:
            logger.debug(f"[SmartTTS] 文本过长 ({len(text)} > {self.max_text_length})，跳过语音")
            return

        # 生成语音并追加到消息链
        try:
            # 清理 Markdown 格式符号，避免 TTS 读出星号等符号
            clean_text = self._strip_markdown(text)
            audio_path = await self._generate_tts(clean_text)
            if audio_path:
                result.chain.append(Record(file=audio_path))
                # 注册临时文件，pipeline 结束后自动清理
                event.track_temporary_local_file(audio_path)
                logger.info(f"[SmartTTS] 已追加语音: {audio_path}")
        except Exception as e:
            logger.error(f"[SmartTTS] 语音生成失败: {e}")

    def _is_plain_text(self, text: str) -> bool:
        """判断文本是否为纯文本（无复杂格式）"""
        for pattern in self.COMPLEX_PATTERNS:
            if pattern.search(text):
                return False
        return True

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """清理常见 Markdown 格式符号，避免 TTS 读出星号、井号等"""
        # 加粗/斜体 **text** / *text* / __text__ / _text_
        text = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", text)
        text = re.sub(r"_{1,2}([^_]+)_{1,2}", r"\1", text)
        # 删除线 ~~text~~
        text = re.sub(r"~~([^~]+)~~", r"\1", text)
        # 剩余独立的 Markdown 符号
        text = re.sub(r"[*#`~|>]", "", text)
        # 合并多余空格
        text = re.sub(r"\s+", " ", text).strip()
        return text

    async def _generate_tts(self, text: str) -> str | None:
        """调用 TTS Provider 生成语音"""
        prov_mgr = self.context.provider_manager
        if not prov_mgr:
            logger.warning("[SmartTTS] Provider Manager 不可用")
            return None

        # 获取 TTS Provider
        tts_provider = None
        if self.tts_provider_id:
            tts_provider = prov_mgr.inst_map.get(self.tts_provider_id)
        if not tts_provider:
            # 找第一个 TTS Provider
            for pid, prov in prov_mgr.inst_map.items():
                if hasattr(prov, "get_audio"):
                    tts_provider = prov
                    break
        if not tts_provider:
            logger.warning("[SmartTTS] 未找到可用的 TTS Provider")
            return None

        if not hasattr(tts_provider, "get_audio"):
            logger.warning(f"[SmartTTS] Provider 不是 TTS Provider")
            return None

        logger.info(f"[SmartTTS] 生成语音: {text[:50]}...")
        audio_path = await tts_provider.get_audio(text)
        return audio_path if audio_path else None
