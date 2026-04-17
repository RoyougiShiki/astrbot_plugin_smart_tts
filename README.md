# astrbot_plugin_smart_tts

智能 TTS 插件 - 始终发送文字，纯文本时额外发送语音。

## 功能

- **始终发送文字回复**（不受影响）
- **智能判断文本格式**：仅在纯文本（无代码块、表格、HTML 等复杂格式）时额外发送语音
- **长度限制**：超过配置长度的文本不发送语音，避免长消息生成过长语音
- 支持 Edge TTS、Cloudflare MeloTTS 等任何已配置的 TTS Provider

## 安装

在 AstrBot WebUI → 插件管理 → 安装插件，输入：

```
https://github.com/RoyougiShiki/astrbot_plugin_smart_tts
```

## 配置

| 配置项 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `tts_provider_id` | string | `edge_tts` | AstrBot 中已配置的 TTS Provider ID |
| `max_text_length` | int | `500` | 超过此长度的文本不发送语音（字符数） |

## 格式检测规则

以下格式被视为"复杂格式"，**不会**触发语音发送：

- 代码块（` ``` `）
- 行内代码（`` `code` ``）
- 表格（`| col | col |`）
- HTML 标签（`<tag>`）
- 图片/链接（`![alt](url)` / `[text](url)`）
- 标题（`# heading`）
- 列表（`- item` / `1. item`）
- 引用（`> quote`）
- 粗体/斜体/删除线

纯自然语言文本**会**触发语音发送。

## 使用前提

1. AstrBot 中已配置并启用 TTS Provider（如 Edge TTS）
2. 建议关闭 AstrBot 原生 TTS（`provider_tts_settings.enable = false`），由本插件接管

## 许可证

MIT
