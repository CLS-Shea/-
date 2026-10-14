import io
from vlm import *
import roles
import kb  # 本地知识库(data/kb) + 官网联网补充
import reception

with open('data/db/memory.db', 'r', encoding='utf-8') as memory_file:
    try:
        openai_history = json.load(memory_file)
    except:
        openai_history = []


# 大屏互动：控制回复长度（简短自然，语音输出不啰嗦）
LONG_REPLY_HINT = ("回答要像日常面对面聊天一样简短自然、口语化，一般不超过100个汉字，"
                   "切忌长篇大论，不要使用列表、编号或Markdown格式")


def limit_reply_length(text, max_len=100):  # 回复长度兜底截断
    """将回复限制在 max_len 字以内；超长时截断到最后一个完整句子，保持自然。"""
    if not text:
        return text
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    for sep in ("。", "！？", "？", "！", "……", "…", "?!", "!", "?", "."):
        idx = cut.rfind(sep)
        if idx >= 0:
            return cut[:idx + 1]
    for sep in ("，", "、", "；", ";", ",", " "):
        idx = cut.rfind(sep)
        if idx >= 0:
            return cut[:idx + 1]
    return cut


# ===== 同音字(拼音)模糊匹配：语音把角色名识别成同音字时也能正确切换角色 =====
try:
    from pypinyin import lazy_pinyin, Style
    _PYPINYIN_OK = True
except Exception:
    _PYPINYIN_OK = False

_py_cache = {}


def _py_seq(s):  # 字符串 -> 无音调拼音序列，如 "程小鹭" -> ['cheng','xiao','lu']
    if not _PYPINYIN_OK or not s:
        return []
    if s not in _py_cache:
        _py_cache[s] = [p for p in lazy_pinyin(s, style=Style.NORMAL) if p]
    return _py_cache[s]


def _py_edit_dist(a, b):  # 拼音串编辑距离，判断两个字是否同音/近音(cheng/chen)
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if abs(la - lb) > 2:
        return 99
    dp = list(range(lb + 1))
    for i in range(1, la + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, lb + 1):
            cur = dp[j]
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + (0 if a[i - 1] == b[j - 1] else 1))
            prev = cur
    return dp[lb]


def _role_name_candidates():
    """返回 [(唤醒词/角色名, 拼音序列, 角色名称)]，按拼音长度降序（优先匹配全名）"""
    cands = []
    for r in roles.ROLES:
        names = list(r.get("唤醒词", []))
        rname = r.get("名称", "")
        if rname and rname not in names:
            names.append(rname)
        for w in names:
            if not w:
                continue
            w_py = _py_seq(w)
            if not w_py or len(w_py) < 2:  # 单字太易误判，跳过
                continue
            cands.append((w, w_py, rname or w))
    cands.sort(key=lambda x: -len(x[1]))
    return cands


def _is_han(c):  # 是否汉字（拼音与字符一一对应的前提）
    return bool(re.match(r'[\u4e00-\u9fff]', c))


def _pinyin_role_spans(msg):
    """找出消息中与角色名/唤醒词近音的片段，返回 [(start, end, 命中的词, 角色名)]。

    用途：不但能判断"有没有叫角色"，还能定位到具体哪几个字，
    从而把语音识别出来的同音字（如"程小璐"→"程小鹭"）纠正回去。
    按位置升序、互不重叠；先匹配更长的名字（"程小鹭"优先于"小鹭"）。
    pypinyin 对汉字是一字一音节，因此拼音下标与汉字下标一一对应。"""
    spans = []
    if not _PYPINYIN_OK or not msg:
        return spans
    msg_py = _py_seq(msg)
    if not msg_py or len(msg_py) != len(msg):
        return spans
    for w, w_py, rname in _role_name_candidates():
        n = len(w_py)
        for i in range(len(msg_py) - n + 1):
            if any(not (i + n <= s or i >= e) for s, e, _, _ in spans):
                continue  # 与已命中的更长名字重叠 → 跳过
            if not all(_is_han(c) for c in msg[i:i + n]):
                continue  # 只对汉字片段纠错，避免改到标点/数字/英文
            total, ok = 0, True
            for j in range(n):
                d = _py_edit_dist(msg_py[i + j], w_py[j])
                if d > 1:  # 单字允许最多 1 处近音(如 cheng/chen)
                    ok = False
                    break
                total += d
            if not ok:
                continue
            if n == 2 and total > 0:
                continue  # 2字词必须完全同音，避免"小路"误判
            spans.append((i, i + n, w, rname))
    spans.sort(key=lambda x: x[0])
    return spans


def _match_role_by_pinyin(msg):
    """兼容旧接口：返回第一个近音片段的唤醒词，没有则 None"""
    spans = _pinyin_role_spans(msg)
    return spans[0][2] if spans else None


def normalize_role_names(msg, min_len=3):
    """把语音识别成同音字的角色名纠正为正确名字（如"程小璐"→"程小鹭"）。
    只纠正式 3 字及以上的名字：2 字词（如"小鹿"）在其他语境下是普通词，不乱改。"""
    if not msg:
        return msg
    spans = [s for s in _pinyin_role_spans(msg) if s[1] - s[0] >= min_len]
    if not spans:
        return msg
    out, last = [], 0
    for s, e, _w, rname in spans:
        out.append(msg[last:s])
        out.append(rname)
        last = e
    out.append(msg[last:])
    return "".join(out)


def role_name_hint():  # 告诉模型自己叫什么，避免它复述识别出来的同音字
    """名字提示：语音识别把名字写成同音字时，也是在叫它，不要复述错别字。"""
    try:
        cur = roles.current_role_name()
        if not cur:
            return ""
        others = [r.get("名称", "") for r in roles.ROLES
                  if r.get("名称") and r.get("名称") != cur]
        hint = f"【称呼说明】你现在的名字是「{cur}」，这样叫你就是叫你。"
        if others:
            hint += f"另外你的同伴叫「{'」「'.join(others)}」。"
        hint += ("语音识别有时会把名字写成同音字（例如“程小璐”“陈小路”），那也是在叫你，"
                 "请按正确名字理解，不要复述或纠正错别字，也不要自称成别的名字。")
        return hint
    except Exception:
        return ""


def detect_and_switch_role(msg):  # 大屏双角色：检测消息中的角色名并切换
    """消息里出现角色名/唤醒词时，切换到对应角色（人设+音色+动嘴角色）。
    先精确匹配；语音识别成同音字时再用拼音模糊匹配，解决"程小鹭"被识别成同音字无法切换的问题。"""
    try:
        if not msg:
            return
        # 1) 精确匹配（文本输入 / 识别准确的场景）
        for r in roles.ROLES:
            for w in r.get("唤醒词", []):
                if w and w in msg:
                    if roles.switch_role(w):
                        try:
                            notice(f"已切换到「{roles.current_role_name()}」")
                        except Exception:
                            pass
                    return
        # 2) 同音字模糊匹配（语音把角色名识别成同音字也能切换）
        hit = _match_role_by_pinyin(msg)
        if hit and roles.switch_role(hit):
            try:
                notice(f"已切换到「{roles.current_role_name()}」")
            except Exception:
                pass
    except Exception:
        pass


def detect_wake(msg):  # 角色名唤醒：判断这句话是不是在喊某个角色的名字
    """消息含任一角色的唤醒词(含同音字模糊匹配)时，切换到该角色并返回角色名；否则返回 None。
    与 detect_and_switch_role 的区别：本函数需要"是否被唤醒"的判断结果，
    用于"喊名字才开始语音交互"的场景。"""
    try:
        if not msg:
            return None
        # 1) 精确匹配（文本输入 / 识别准确的场景）
        for r in roles.ROLES:
            for w in r.get("唤醒词", []):
                if w and w in msg:
                    if roles.switch_role(w):
                        return roles.current_role_name()
                    break  # 命中但切换失败 → 换下一个角色试
        # 2) 同音字模糊匹配（语音把角色名识别成同音字也能唤醒）
        hit = _match_role_by_pinyin(msg)
        if hit and roles.switch_role(hit):
            return roles.current_role_name()
    except Exception:
        pass
    return None


def role_name_in_message(msg):
    """返回消息中命中的角色名，但不执行切换，用于现场模式确认切换。"""
    if not msg:
        return None
    for r in roles.ROLES:
        for w in r.get("唤醒词", []):
            if w and w in msg:
                return r.get("名称")
    hit = _match_role_by_pinyin(msg)
    return hit


def strip_wake_words(msg):  # 去掉唤醒词，取出真正要说的内容
    """移除消息里的角色名称/唤醒词（含被听成同音字的写法），返回剩余内容；仅喊名字时返回空字符串。"""
    if not msg:
        return ""
    # 1) 先按拼音定位删除（"程小璐"这类同音字也能删掉）
    spans = _pinyin_role_spans(msg)
    if spans:
        out, last = [], 0
        for s, e, _w, _rname in spans:
            out.append(msg[last:s])
            last = e
        out.append(msg[last:])
        msg = "".join(out)
    # 2) 再删完全一致的写法（拼音匹配要求逐字对应汉字，个别情况可能漏）
    words = set()
    for r in roles.ROLES:
        for w in r.get("唤醒词", []):
            if w:
                words.add(w)
        rname = r.get("名称", "")
        if rname:
            words.add(rname)
    out = msg
    for w in sorted(words, key=len, reverse=True):  # 先删长词(全名)，避免短唤醒词残留
        out = out.replace(w, "")
    return out.strip(" \t\r\n，,。.！!？?、；;：:~～—-")


def chat_preprocess(msg):  # 聊天预处理
    try:
        msg = normalize_role_names(msg)  # 同音字纠正："程小璐"→"程小鹭"，避免把错字喂给大模型
        detect_and_switch_role(msg)  # 大屏双角色：先识别唤醒了哪个角色
        # 学校事实类提问：本地知识库+官网都查不到 → 用固定话术回应，不给大模型编造的机会
        _refuse = kb.should_refuse(msg)
        if _refuse:
            notice("没有查到相关信息，已如实告知")
            return _refuse
        if ("屏幕" in msg or "画面" in msg or "图像" in msg or "看到" in msg or "看看" in msg or "看见" in msg
              or "照片" in msg or "摄像头" in msg or "图片" in msg) and img_menu.get() != "关闭图像识别":
            if mode_menu.get() == "角色扮演聊天":
                msg = f"{prompt}。你需要根据其中内容和我聊天。我的问题是：{msg}"
            vlm_mapping = {
                "photo": {"GLM-4V-Flash": glm_4v_photo, "本地Ollama VLM": ollama_vlm_photo,
                          "本地LM Studio": lmstudio_vlm_photo, "本地QwenVL整合包": qwen_vlm_photo,
                          "本地Janus整合包": janus_photo, "自定义API-VLM": custom_vlm_photo},
                "screen": {"GLM-4V-Flash": glm_4v_screen, "本地Ollama VLM": ollama_vlm_screen,
                           "本地LM Studio": lmstudio_vlm_screen, "本地QwenVL整合包": qwen_vlm_screen,
                           "本地Janus整合包": janus_screen, "自定义API-VLM": custom_vlm_screen},
                "cam": {"GLM-4V-Flash": glm_4v_cam, "本地Ollama VLM": ollama_vlm_cam, "本地LM Studio": lmstudio_vlm_cam,
                        "本地QwenVL整合包": qwen_vlm_cam, "本地Janus整合包": janus_cam, "自定义API-VLM": custom_vlm_cam}}
            if "图片" in msg:
                if os.path.exists("data/cache/cache.png"):
                    selected_model = img_menu.get()
                    content = vlm_mapping["photo"][selected_model](msg)
                    notice(f"{mate_name}识别了上传的图片")
                    os.remove("data/cache/cache.png")
                else:
                    content = "请先点击右下方按钮上传图片"
                    notice("请先点击右下方按钮上传图片")
            elif any(keyword in msg for keyword in ["看到", "看见", "看看", "照片", "摄像头"]) and cam_permission == "开启":
                selected_model = img_menu.get()
                content = vlm_mapping["cam"][selected_model](msg)
                notice(f"{mate_name}拍了照片，调用[摄像头识别]")
            else:
                selected_model = img_menu.get()
                content = vlm_mapping["screen"][selected_model](msg)
                notice(f"{mate_name}捕获了屏幕，调用[电脑屏幕识别]")
        elif "画" in msg and prefer_draw != "关闭AI绘画":
            msg = re.sub(r"画|绘画", "", msg)
            content = "正在进行AI绘画"
            notice(f"{mate_name}正在进行AI绘画，请稍等...")
            if prefer_draw == "本地SD API":
                local_sd(msg)
            elif prefer_draw == "本地Janus整合包":
                local_janus(msg)
            elif prefer_draw == "云端CogView-3":
                cloud_cogview(msg)
            elif prefer_draw == "云端Kolors":
                cloud_kolors(msg)
            elif prefer_draw == "云端文心Web":
                content = "绘画完成"
                msg = re.sub(r"画|绘画", "", msg)
                wb.open(f'https://image.baidu.com/front/aigc?tn=aigc&word={msg}')
                notice(f"{mate_name}打开了浏览器，调用[云AI绘画]")
        else:
            if mode_menu.get() == "多智能体助手":
                _role = roles.get_current_role()
                _persona = _role.get("人设") or prompt
                _rname = _role.get("名称") or mate_name
                _sys = (f"{_persona}。你是{_rname}，是专属于我({username})的多智能体助手，支持调用多种智能体，"
                        f"拥有以下功能：{all_task}。{LONG_REPLY_HINT}。{role_name_hint()}。")
                _sys += kb.build_prompt_context(msg)  # 知识库(学校事实) + 必要时官网联网补充
                content = function_llm(_sys, msg)
            else:
                content = chat_llm(msg)
            notice(f"收到{mate_name}回复")
        # 现场接待模式不持久化访客对话，避免下一位访客继承上一轮上下文。
        if not reception.enabled():
            with open('data/db/memory.db', 'w', encoding='utf-8') as f:
                json.dump(openai_history, f, ensure_ascii=False, indent=4)
        return content
    except Exception as e:
        notice(f"图像识别引擎配置错误，错误详情：{e}")
        return "图像识别引擎配置错误"


def chat_llm(msg):  # 大语言模型聊天
    msg = normalize_role_names(msg)  # 同音字纠正："程小璐"→"程小鹭"，避免把错字喂给大模型
    detect_and_switch_role(msg)  # 大屏双角色：先识别唤醒了哪个角色
    # 学校事实类提问：本地知识库+官网都查不到 → 用固定话术回应，不给大模型编造的机会
    _refuse = kb.should_refuse(msg)
    if _refuse:
        try:
            openai_history.append({"role": "user", "content": msg})
            openai_history.append({"role": "assistant", "content": _refuse})
        except Exception:
            pass
        return _refuse
    _role = roles.get_current_role()
    _persona = _role.get("人设") or prompt
    prompt1 = _persona + f"/no_think。{role_name_hint()}。{LONG_REPLY_HINT}。"
    prompt1 += kb.build_prompt_context(msg)  # 知识库(学校事实) + 必要时官网联网补充
    if "几点" in msg or "多少点" in msg or "时间" in msg or "时候" in msg or "日期" in msg or "多少号" in msg or "几号" in msg or "星期" in msg or "周几" in msg or "礼拜" in msg:
        msg = f"[当前时间:{current_time()}]{msg}"
    try:
        if llm_menu.get() == "GLM-4-Flash":
            client = ZhipuAI(api_key=glm_key)
            openai_history.append({"role": "user", "content": msg})
            messages = [{"role": "system", "content": prompt1}]
            messages.extend(openai_history)
            completion = client.chat.completions.create(model=glm_llm_model, messages=messages)
            openai_history.append({"role": "assistant", "content": completion.choices[0].message.content})
            return completion.choices[0].message.content.strip()
        elif llm_menu.get() == "DeepSeek-R1-8B":
            client = OpenAI(base_url=sf_url, api_key=sf_key)
            openai_history.append({"role": "user", "content": msg})
            messages = [{"role": "system", "content": prompt1}]
            messages.extend(openai_history)
            completion = client.chat.completions.create(model="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
                                                        messages=messages)
            openai_history.append({"role": "assistant", "content": completion.choices[0].message.content})
            res = completion.choices[0].message.content
            if think_filter_switch == "on":
                res = res.split("</think>")[-1].strip()
            return res
        elif llm_menu.get() == "通义千问3-8B":
            client = OpenAI(base_url=sf_url, api_key=sf_key)
            openai_history.append({"role": "user", "content": msg})
            messages = [{"role": "system", "content": prompt1}]
            messages.extend(openai_history)
            completion = client.chat.completions.create(model="Qwen/Qwen3-8B", messages=messages)
            openai_history.append({"role": "assistant", "content": completion.choices[0].message.content})
            return completion.choices[0].message.content.strip()
        elif llm_menu.get() == "文心一言Speed":
            client = OpenAI(base_url=bd_url, api_key=bd_key)
            openai_history.append({"role": "user", "content": msg})
            messages = [{"role": "system", "content": prompt1}]
            messages.extend(openai_history)
            completion = client.chat.completions.create(model=bd_model, messages=messages)
            openai_history.append({"role": "assistant", "content": completion.choices[0].message.content})
            return completion.choices[0].message.content
        elif llm_menu.get() == "腾讯混元Lite":
            client = OpenAI(base_url=hy_url, api_key=hy_key)
            openai_history.append({"role": "user", "content": msg})
            messages = [{"role": "system", "content": prompt1}]
            messages.extend(openai_history)
            completion = client.chat.completions.create(model=hy_model, messages=messages)
            openai_history.append({"role": "assistant", "content": completion.choices[0].message.content})
            return completion.choices[0].message.content
        elif llm_menu.get() == "讯飞星火Lite":
            client = OpenAI(base_url=xf_url, api_key=xf_key)
            openai_history.append({"role": "user", "content": msg})
            messages = [{"role": "system", "content": prompt1}]
            messages.extend(openai_history)
            completion = client.chat.completions.create(model=xf_model, messages=messages)
            openai_history.append({"role": "assistant", "content": completion.choices[0].message.content})
            return completion.choices[0].message.content
        elif llm_menu.get() == "本地Transformers":
            try:
                client = OpenAI(base_url=f"http://{local_llm_ip}:{tf_port}/v1", api_key="transformers")
                openai_history.append({"role": "user", "content": msg})
                messages = [{"role": "system", "content": prompt1}]
                messages.extend(openai_history)
                completion = client.chat.completions.create(model=tf_model, messages=messages, stream=False)
                chunks = re.findall(r'^data:\s*(.+)$', completion, flags=re.MULTILINE)
                result_content = []
                for chunk in chunks:
                    try:
                        data = json.loads(chunk)
                        content = data.get("choices", [{}])[0].get("delta", {}).get("content")
                        if content is not None:
                            result_content.append(content)
                    except json.JSONDecodeError:
                        continue
                result_content = "".join(result_content).replace("\n", "")
                openai_history.append({"role": "assistant", "content": result_content})
                res = result_content
                if think_filter_switch == "on":
                    res = res.split("</think>")[-1].strip()
                return res
            except Exception as e:
                return f"本地Transformers服务未开启，错误详情：{e}"
        elif llm_menu.get() == "本地LM Studio":
            try:
                client = OpenAI(base_url=f"http://{local_llm_ip}:{lmstudio_port}/v1", api_key="lm-studio")
                openai_history.append({"role": "user", "content": msg})
                messages = [{"role": "system", "content": prompt1}]
                messages.extend(openai_history)
                completion = client.chat.completions.create(model="", messages=messages)
                openai_history.append({"role": "assistant", "content": completion.choices[0].message.content})
                res = completion.choices[0].message.content
                if think_filter_switch == "on":
                    res = res.split("</think>")[-1].strip()
                return res
            except Exception as e:
                return f"本地LM Studio软件API服务未开启，错误详情：{e}"
        elif llm_menu.get() == "本地Ollama LLM":
            try:
                try:
                    rq.get(f'http://{local_llm_ip}:{ollama_port}')
                except:
                    Popen(f"ollama pull {ollama_model_name}", shell=False)
                client = Client(host=f'http://{local_llm_ip}:{ollama_port}')
                openai_history.append({"role": "user", "content": msg})
                messages = [{"role": "system", "content": prompt1}]
                messages.extend(openai_history)
                response = client.chat(model=ollama_model_name, messages=messages)
                openai_history.append({"role": "assistant", "content": response['message']['content']})
                res = response['message']['content']
                if think_filter_switch == "on":
                    res = res.split("</think>")[-1].strip()
                return res
            except Exception as e:
                return f"本地Ollama LLM配置错误，错误详情：{e}"
        elif llm_menu.get() == "Dify聊天助手":
            try:
                res = chat_dify(msg)
                return res
            except Exception as e:
                return f"本地Dify聊天助手配置错误，错误详情：{e}"
        elif llm_menu.get() == "AnythingLLM":
            try:
                res = chat_anything_llm(msg)
                return res
            except Exception as e:
                return f"本地AnythingLLM知识库配置错误，错误详情：{e}"
        else:
            try:
                client = OpenAI(base_url=custom_url, api_key=custom_key)
                openai_history.append({"role": "user", "content": msg})
                messages = [{"role": "system", "content": prompt1}]
                messages.extend(openai_history)
                completion = client.chat.completions.create(model=custom_model, messages=messages)
                openai_history.append({"role": "assistant", "content": completion.choices[0].message.content})
                res = completion.choices[0].message.content
                if think_filter_switch == "on":
                    res = res.split("</think>")[-1].strip()
                return res.strip()
            except Exception as e:
                return f"自定义API配置错误，错误详情：{e}"
    except:
        return f"{llm_menu.get()}服务未正确设置，请前往软件设置→云端AI Key设置"


# open_source_project_address:https://github.com/swordswind/ai_virtual_mate_web
def chat_dify(msg):  # Dify聊天助手
    headers = {"Authorization": f"Bearer {dify_key}", "Content-Type": "application/json"}
    data = {"query": msg, "inputs": {}, "response_mode": "blocking", "user": username, "conversation_id": None}
    res = rq.post(f"http://{dify_ip}/v1/chat-messages", headers=headers, data=json.dumps(data))
    res = res.json()['answer'].strip()
    if think_filter_switch == "on":
        res = res.split("</think>")[-1].strip()
    return res


def chat_anything_llm(msg):  # AnythingLLM知识库
    url = f"http://{local_llm_ip}:3001/api/v1/workspace/{anything_llm_ws}/chat"
    headers = {"Authorization": f"Bearer {anything_llm_key}", "Content-Type": "application/json"}
    data = {"message": msg}
    res = rq.post(url, json=data, headers=headers)
    res = res.json().get("textResponse")
    if think_filter_switch == "on":
        res = res.split("</think>")[-1].strip()
    return res


def clear_chat():  # 删除聊天记录
    global openai_history
    if messagebox.askokcancel(f"清除{mate_name}的聊天记录",
                              f"您确定要清除{mate_name}的聊天记录吗？\n如有需要可先点击🔼导出记录再开启新对话\n(该操作不影响伙伴记忆，\n如果想删除记忆可右键聊天框)"):
        output_box.delete("1.0", "end")
        notice("聊天记录已清空")


def local_sd(msg):  # 本地Stable Diffusion
    def local_sd_th():
        try:
            sd_prompt = function_llm("你是一个专业且高水平的Stable Diffusion AI绘画提示词生成器，擅长把我的自然语言转换成Stable Diffusion AI绘画英文提示词。回答只需输出AI绘画英文提示词，提示词由英文单词组成，用英文逗号隔开，不要输出其他内容。",
                                     f"请你根据我的下述需求生成AI绘画提示词，提示词由英文单词组成，用英文逗号隔开，不要输出其他内容：{msg}")
            payload = {"prompt": sd_prompt, "steps": 20}
            res = rq.post(f"http://{local_draw_ip}:{sd_port}/sdapi/v1/txt2img", json=payload)
            data = res.json()
            sd_draw_path = "data/cache/draw/sd_aigc.png"
            with open(sd_draw_path, 'wb') as f:
                f.write(b64decode(data['images'][0]))
            notice("绘画完成")
            draw_box("Stable Diffusion", "sd_aigc")
        except Exception as e:
            notice(f"本地SD AI绘画出错，错误详情：{e}")

    Thread(target=local_sd_th).start()


def local_janus(msg):  # 本地Janus
    def local_janus_th():
        try:
            janus_prompt = function_llm("你是一个专业且高水平的翻译官，擅长把我的语言翻译成英文。回答只需输出翻译成英文的结果，不要输出其他内容。",
                                        f"把下列内容翻译成英文，回答只需输出翻译成英文的结果：{msg}")
            data = {'prompt': janus_prompt, 'seed': None, 'guidance': 5}
            response = rq.post(f"http://{local_draw_ip}:8082/generate_images/", data=data, stream=True)
            buffer = io.BytesIO()
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    buffer.write(chunk)
            buffer.seek(0)
            image = Image.open(buffer)
            janus_draw_path = "data/cache/draw/janus_aigc.png"
            image.save(janus_draw_path)
            notice("绘画完成")
            draw_box("Janus", "janus_aigc")
        except Exception as e:
            notice(f"本地Janus AI绘画出错，错误详情：{e}")

    Thread(target=local_janus_th).start()


def cloud_cogview(msg):  # 云端CogView
    def cloud_cogview_th():
        try:
            client = ZhipuAI(api_key=glm_key)
            res = client.images.generations(model="cogview-3-flash", prompt=msg)
            image_response = rq.get(res.data[0].url)
            cogview_draw_path = "data/cache/draw/cogview_aigc.png"
            with open(cogview_draw_path, "wb") as f:
                f.write(image_response.content)
            notice("绘画完成")
            draw_box("CogView", "cogview_aigc")
        except:
            notice("云端Cogview绘画未正确配置，请前往软件设置→云端AI Key设置GLM智谱BigModel开放平台key")

    Thread(target=cloud_cogview_th).start()


def cloud_kolors(msg):  # 云端Kolors
    def cloud_kolors_th():
        try:
            url = f"{sf_url}/images/generations"
            payload = {"model": "Kwai-Kolors/Kolors", "prompt": msg}
            headers = {"Authorization": f"Bearer {sf_key}", "Content-Type": "application/json"}
            res = rq.request("POST", url, json=payload, headers=headers)
            image_response = rq.get(res.json()["images"][0]["url"])
            kolors_draw_path = "data/cache/draw/kolors_aigc.png"
            with open(kolors_draw_path, "wb") as f:
                f.write(image_response.content)
            notice("绘画完成")
            draw_box("Kolors", "kolors_aigc")
        except:
            notice("云端Kolors绘画未正确配置，请前往软件设置→云端AI Key设置SiliconCloud硅基流动平台key")

    Thread(target=cloud_kolors_th).start()
