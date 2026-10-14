# 枫云AI虚拟伙伴Web版 — 开发指南

Python 3.12 的开源 AI 虚拟伙伴框架（自带便携 `runtime/`），支持语音/文本交互、双角色（Live2D/MMD/VRM）、多智能体助手。Web 界面默认端口 **5260**。架构与功能总览见 [`README.md`](./README.md)。

## 阿里云（百炼 / DashScope）API 接入 — 重点

项目通过「自定义API」机制接入阿里云百炼，覆盖对话(LLM)、图像识别(VLM)、语音合成(TTS)。面向用户的完整配置说明见 [`阿里云百炼接入说明.txt`](./阿里云百炼接入说明.txt)。

### 密钥与配置位置（三处，改漏一处就会"一半生效一半失效"）
| 能力 | 配置文件 | 字段 |
|---|---|---|
| LLM + VLM | `data/db/config.json` | `自定义API-base_url`、`自定义API-api_key`、`自定义API-model`(默认 `qwen-plus`)、`自定义API-VLM`(默认 `qwen-vl-plus`) |
| 自定义API-TTS | `data/set/custom_tts_set.txt` | `[base_url]`、`[model]`(默认 `qwen-tts`)、`[voice]`、`[api_key]`（固定行索引 1/4/7/10） |
| 双角色实时TTS | `data/db/roles.json` | 每角色 `TTS引擎`(阿里云实时TTS)、`TTS音色`(非实时)、`实时TTS音色`(实时) |

- base_url = `https://dashscope.aliyuncs.com/compatible-mode/v1`（**北京地域，API Key 按地域绑定**，其他地域 key 会 401）。
- `data/set/cloud_ai_key_set.json` **不含阿里云 key**（只有智谱/硅基流动/百度/腾讯/讯飞），别去那里找。
- 配置由 `sys_init.py` 读入模块级变量，经 `from sys_init import *` 全局传递；改配置后需重启生效。

### 关键代码路径
- **LLM**：`llm.py` 的 `chat_llm()`，自定义API分支 = `OpenAI(base_url=custom_url, api_key=custom_key).chat.completions.create(...)`；多智能体入口在 `function.py` 的 `function_llm()`。
- **VLM**：`vlm.py` 的 `custom_vlm_cam/screen/photo()`，视觉消息为 OpenAI 格式（base64 data URL）。
- **TTS**：`tts.py` 的 `custom_tts()`（自定义API-TTS）与 `_synthesize_realtime_segment()`（阿里云实时TTS，WebSocket）。

### 易踩坑（历史教训，务必先看）
1. **实时TTS 的 key 只能走全局属性**：`QwenTtsRealtime(model, callback, url)` 构造时内部读 `dashscope.api_key`，**必须先 `_dashscope.api_key = custom_tts_key` 再构造**（`tts.py` 中 `_synthesize_realtime_segment` / `_tts_realtime_play_full` 都有此赋值）。
2. **百炼 TTS 不走 OpenAI 兼容 `/audio/speech`（404）**：必须走原生 `https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation`，音频在 `output.audio.url`（OSS 临时链接）需二次下载。`custom_tts()` 已按 `custom_tts_url` 是否含 `dashscope.aliyuncs.com` 自动分流。
3. **实时模型按音色前缀自动选**（`tts.py` 的 `_realtime_tts_model()`）：`qwen-tts-vd-*`→`qwen3-tts-vd-realtime-2026-01-15`、`qwen-tts-vc-*`→VC 实时模型、其他(系统音色如 Ethan/Serena/Mochi/Momo)→`qwen3-tts-flash-realtime`。
4. **自定义音色绑定创建时的 target_model**：`qwen-tts-vd-bailian-voice-...` 是给非实时 `qwen-tts` 创建的，实时模型会报 `CLIENT_ERROR`；要用于实时需在百炼控制台【声音设计】重建，`target_model` 选 `qwen3-tts-vd-realtime-2026-01-15`。
5. **错误码含义**：`401 Invalid API-key`= key 地域不对（须北京）；`Arrearage`= 账户欠费/未开通对应模型（各模型计费独立，TTS 有额度不代表 LLM 有）。
6. **dashscope 不在 `requirements.txt`**：由自带 runtime 提供（已装 `1.27.2`），要求 `>=1.25.11` 才有实时 TTS；缺失时 `_realtime_tts_ready=False`，引擎会提示安装。
7. **"配置填了没生效"先怀疑未保存**：`custom_tts_set.txt` 是纯文本按行读取，VS Code 里改了但未 Ctrl+S，程序读磁盘仍是旧值。
8. **密钥安全**：`data/set/`、`data/db/` 不暴露给 Web 访问者；不要把 key 打印日志或回传网页端。

## 阿里云 OpenAPI（SDK / CLI）

- 本项目**业务代码没有调用**阿里云 ECS/OSS 等 OpenAPI；`package.json` 的 `@alicloud/ecs20140526` 与 `node_modules` 是实验性死依赖，可忽略，别被误导。
- 若需用 SDK 调阿里云 OpenAPI：Python 用 `alibabacloud_*` 系列包 + `open_config` 构造 `Config`（`access_key_id`/`access_key_secret`/`region_id`/`endpoint`）；Node 用 `@alicloud/openapi-client` 的 `Config`。CLI 用 `aliyun configure` 配置凭据后 `aliyun <product> <action>` 调用。

## 运行与验证

- **启动**：`runtime\pythonw main.py`（无控制台，正式）；**调试**：`runtime\python main.py`（打印日志，排查用）。
- **Web**：`http://127.0.0.1:5260`（端口在 config.json `对话网页端口`）；大屏模式见 `大屏模式-网页全屏.bat`（`MATEWEB_KIOSK=1`）。
- **配置验证**：GUI 设置窗口「测试API」按钮 = `custom_api_test`（`gui.py`），用当前 key+url 调 `OpenAI(...).models.list()` 列出可用模型。
- **语音验证**：调试模式下看 `[阿里云实时TTS]` / `[TTS]` 日志；无声先查第 7 条（未保存）与第 4 条（音色/模型不匹配）。
