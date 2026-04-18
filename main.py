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

import re

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.message_components import Plain, Record
from astrbot.api.star import Context, Star, register


@register(
    "astrbot_plugin_smart_tts",
    "RoyougiShiki",
    "智能 TTS - 纯文本时额外发送语音",
    "0.1.1",
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
