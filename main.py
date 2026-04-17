"""智能 TTS 插件

功能：
1. 始终发送文字回复
2. 仅在纯文本（无代码块、表格、HTML 等复杂格式）时额外发送语音
3. 支持配置 TTS Provider 和最大文本长度

实现方式：拦截 AstrBot 的文本输出事件，在消息发送前判断格式，
如果是纯文本则调用 TTS Provider 生成语音并追加发送。
"""

from __future__ import annotations

import asyncio
import re

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.provider import ProviderType


@register(
    "astrbot_plugin_smart_tts",
    "RoyougiShiki",
    "智能 TTS - 纯文本时额外发送语音",
    "0.1.0",
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
        re.compile(r"^#{1,6}\s+"),                # 标题
        re.compile(r"^\s*[-*+]\s+"),             # 列表项
        re.compile(r"^\s*\d+\.\s+"),             # 有序列表
        re.compile(r"^\s*>\s+"),                 # 引用
        re.compile(r"---\s*$"),                   # 分隔线
        re.compile(r"\*\*.*?\*\*"),              # 粗体
        re.compile(r"\*.*?\*"),                  # 斜体
        re.compile(r"~~.*?~~"),                  # 删除线
    ]

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.conf = config
        self.tts_provider_id = config.get("tts_provider_id", "edge_tts")
        self.max_text_length = config.get("max_text_length", 500)

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, response: str) -> None:
        """拦截 LLM 响应，判断是否需要额外发送语音"""
        if not response or not response.strip():
            return

        text = response.strip()

        # 判断是否为纯文本
        is_plain = self._is_plain_text(text)

        if is_plain:
            # 检查长度限制
            if len(text) <= self.max_text_length:
                # 异步生成并发送语音（不阻塞文字发送）
                asyncio.create_task(self._send_tts(event, text))
            else:
                logger.debug(f"[SmartTTS] 文本过长 ({len(text)} > {self.max_text_length})，跳过语音")
        else:
            logger.debug(f"[SmartTTS] 检测到复杂格式，跳过语音")

    def _is_plain_text(self, text: str) -> bool:
        """判断文本是否为纯文本（无复杂格式）"""
        for pattern in self.COMPLEX_PATTERNS:
            if pattern.search(text):
                return False
        return True

    async def _send_tts(self, event: AstrMessageEvent, text: str) -> None:
        """调用 TTS Provider 生成并发送语音"""
        try:
            # 获取 Provider Manager
            prov_mgr = self.context.provider_manager
            if not prov_mgr:
                logger.warning("[SmartTTS] Provider Manager 不可用")
                return

            # 获取 TTS Provider
            tts_provider = prov_mgr.inst_map.get(self.tts_provider_id)
            if not tts_provider:
                logger.warning(f"[SmartTTS] TTS Provider '{self.tts_provider_id}' 未找到")
                return

            # 检查 Provider 类型
            if not hasattr(tts_provider, "get_audio"):
                logger.warning(f"[SmartTTS] Provider '{self.tts_provider_id}' 不是 TTS Provider")
                return

            # 生成语音
            logger.info(f"[SmartTTS] 生成语音: {text[:50]}...")
            audio_path = await tts_provider.get_audio(text)

            if audio_path and isinstance(audio_path, str):
                # 发送语音消息
                from astrbot.api.message_components import Record
                await event.send(Record(file=audio_path))
                logger.info(f"[SmartTTS] 语音已发送: {audio_path}")
            else:
                logger.warning(f"[SmartTTS] TTS 返回空路径")

        except Exception as e:
            logger.error(f"[SmartTTS] 语音生成失败: {e}")
