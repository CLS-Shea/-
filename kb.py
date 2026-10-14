# -*- coding: utf-8 -*-
"""本地知识库（data/kb/）检索 + 官网联网兜底 + 防编造闸门。

对外主要接口（llm.py / agent.py 调用）：
    build_prompt_context(msg)  → 拼进 system prompt 的"事实边界 + 资料"（事实边界每次都有）
    should_refuse(msg)         → 需要"没有可靠收录"固定话术时返回话术，否则 None

设计：
- 往 data/kb/ 里新增 .md/.txt 就会自动一起加载（重启软件后生效），按 Markdown 标题分块。
- 打分用「中文二元组 + 英文数字词」；疑问词/虚词以及高频泛词不当证据。
- 只有"问题里的具体词确实被资料命中"才算资料切题；只命中"学校/学院"这类泛词不算。
- 资料不够且问题与学校相关时联网补充，但**只采信学校官网 njit.edu.cn 的结果**。
- 学校"具体事实"提问若资料答不上 → 直接回固定话术，不调用大模型（从根上杜绝编造）。
"""
import json
import os
import random
import re
import threading
import reception

KB_DIR = os.path.join('data', 'kb')
MORE_SET_PATH = os.path.join('data', 'set', 'more_set.json')

MIN_SCORE = 1            # 命中分数下限（判定"资料切题"另见 relevant）
GENERIC_DF = 8           # 在这么多片段里都出现的词算"泛词"（学校/学院/南京…），不能作为切题证据
# 联网检索的等待上限（搜索服务不稳定时不阻塞回复）
WEB_TIMEOUT_SECONDS = 6
# 学校官网域名（联网补充时优先）
SCHOOL_SITE = 'njit.edu.cn'

# 注入到 system prompt 的资料使用规则（对应知识库文档"模块六：回答边界"）
KB_RULES = (
    "【参考资料使用规则】下面给出与当前问题相关的资料片段。"
    "凡是涉及学校事实（学校概况、校训、历史沿革、学院与专业、领导与职务、人数规模、地址、校园地标、"
    "设备使用方法等）的问题，必须严格以资料为准：资料里有的照实回答；"
    "资料里没有的，直接说“这个我这边没有可靠收录，建议查看学校官网或正式通知”，"
    "绝对不要凭印象编造人名、职务、数字、时间、政策、活动、地点。"
    "引用领导、人数等会变动的信息时要带上复核时间。"
    "不要说“资料”“知识库”“片段”这类词，像平常聊天一样自然地回答。"
)

# 每次对话都会注入的"事实边界"（不依赖是否检索到资料，这是防编造的第一道闸）
FACT_RULE_SHORT = (
    "【事实边界】绝对不要编造南京工程学院的具体信息——包括地点、建筑、道路、店铺、人物、职务、"
    "数字、时间、政策、活动、社团、联系方式。这类信息只能依据资料；资料里没有就说“这个我这边"
    "没有可靠收录，建议看学校官网或官方公众号”，绝不可以用想象补充。"
    "如果问题里只有一部分能在资料里找到，就只回答能找到的那部分，剩下那部分直接说没有可靠收录，"
    "不要推测、不要含糊带过。数字、日期、人名、电话、政策一律只能照抄资料。"
    "闲聊时也不要虚构校园里的具体地名、设施和活动。"
)

# 知识库"不得凭空回答"的主题：即便资料里提到过这些词，也不给具体答案，一律如实说查不到
_NEVER_ANSWER = ('分数线', '录取线', '录取分数', '招生', '招多少', '招几个', '报名', '学费', '住宿费',
                 '收费标准', '收费', '排名', '就业率', '升学率', '联系电话', '电话号码', '办公室电话',
                 '咨询电话', '活动时间', '几人间')

# 判断"是否与学校相关"的关键词（用于决定要不要联网补充）
_SCHOOL_KEYWORDS = (
    '南京工程', '南工程', 'njit', '学校', '学院', '校训', '校史', '校风', '校园', '校区', '校长', '书记',
    '领导', '院长', '党委书记', '天印湖', '图书馆', '体育场', '社团', '专业', '招生', '录取', '分数线',
    '学费', '住宿', '宿舍', '食堂', '就业', '考研', '升本', '毕业', '老师', '教师', '课程', '实验室',
    '工程训练', '创新创业', '沈国荣', '奥卢', '李泽湘', 'XbotPark', '机电', '电力', '自动化', '计算机',
    '机械', '材料', '建筑', '交通', '外国语', '数理', '马克思主义', '艺术', '商学院', '管理工程',
    '设备使用', '怎么唤醒', '唤醒',
)

# 常见虚词/疑问词：不参与打分（否则"怎么样""是什么"这类词会在很多片段里到处命中）
_STOPWORDS = {
    '什么', '怎么', '怎样', '么样', '如何', '多少', '几个', '哪个', '哪些', '哪里', '哪儿', '是谁', '为什',
    '请问', '告诉', '一下', '可以', '能不', '不能', '是不', '不是', '有没', '没有', '知道', '介绍',
    '我们', '你们', '他们', '这个', '那个', '一个', '现在', '今天', '明天', '昨天', '时候',
    '的话', '就是', '还是', '然后', '因为', '所以', '但是', '而且', '如果', '这样', '那样',
    '嗯嗯', '谢谢', '你好', '您好', '请问', '一下', '到底', '究竟',
}

# 疑问/虚词里的单字：由它们组成的二元组多是跨词边界的碎词（如"校有""少在""是什"），
# 检索与切题判断时忽略，避免"碰巧字面相同"造成误判
_FUNC_CHARS = set('的了是在有和与我你他她它们这那不也会能要就都还太真吗呢吧啊呀哦哪什怎怎么样多'
                  '少几个为如可没告诉请问一下什么')

# 学校事实类提问的判定词（决定"查不到要不要走固定话术"）
_FACT_ASK = ('是什么', '是谁', '是多少', '多少', '几', '哪些', '哪个', '哪里', '哪几', '在哪', '有没有',
             '是不是', '介绍', '讲讲', '告诉', '怎么走', '怎么去', '怎么坐', '排名', '分数线', '政策',
             '规定', '电话', '地址', '怎么样', '如何', '能不能', '可不可以', '好不好', '开放时间', '收费标准')
_FACT_ASK_RE = re.compile(r'有.{0,8}(吗|么|嘛|没)[？?。]?$')  # "有…吗"这类问法

# 没有可靠资料时的固定回应（不调用大模型，从根上杜绝编造）
REFUSE_TEXTS = [
    '这个我这边没有可靠收录呀，建议看看学校官网或者官方公众号～',
    '这个我不太确定，怕说错了误导你，还是以学校官网和正式通知为准吧～',
    '这个我这边没有查到可靠信息，不敢乱讲，你可以去学校官网确认一下～',
]

_chunks = None          # [(标题路径, 正文, 词元集合)]
_df = {}                # 词元 -> 出现片段数
_df_common = set()      # 出现片段过多（>35%）的词，打分时忽略
_load_lock = threading.Lock()
_web_cache = {}
_material_cache = {}    # (msg,top_k,allow_web) -> (资料正文, 最高分, 是否切题)


# ==================== 加载与分块 ====================
def _iter_kb_files():
    if not os.path.isdir(KB_DIR):
        return
    for name in sorted(os.listdir(KB_DIR)):
        if name.lower().endswith(('.md', '.txt')):
            yield os.path.join(KB_DIR, name)


def _split_chunks(text, source):
    """按 Markdown 标题切块；超长的块再按空行切分，保证每块不超过约 900 字。"""
    lines = text.splitlines()
    title_stack = []
    buf = []
    chunks = []

    def flush():
        body = "\n".join(buf).strip()
        if body:
            title = " / ".join(title_stack) if title_stack else source
            chunks.append((title, body))

    for line in lines:
        m = re.match(r'^(#{1,6})\s+(.*)$', line.strip())
        if m:
            flush()
            buf = []
            level = len(m.group(1))
            del title_stack[level - 1:]
            title_stack.append(m.group(2).strip())
            continue
        buf.append(line)
    flush()

    # 过长的块按空行再切
    result = []
    for title, body in chunks:
        if len(body) <= 900:
            result.append((title, body))
            continue
        parts, cur = [], ''
        for para in body.split('\n\n'):
            if len(cur) + len(para) > 900 and cur:
                parts.append(cur.strip())
                cur = ''
            cur += para + '\n\n'
        if cur.strip():
            parts.append(cur.strip())
        for i, part in enumerate(parts):
            result.append((f"{title}({i + 1})" if i else title, part))
    return result


def _tokens(s, clean=True):
    """中文二元组 + 英文/数字词。clean=True 时丢掉含疑问/虚词单字的碎词元（用于问题侧）。"""
    toks = set()
    for seg in re.findall(r'[\u4e00-\u9fff]+', s):
        if len(seg) == 1:
            toks.add(seg)
        for i in range(len(seg) - 1):
            bg = seg[i:i + 2]
            if clean and (bg[0] in _FUNC_CHARS or bg[1] in _FUNC_CHARS):
                continue
            toks.add(bg)
    for w in re.findall(r'[A-Za-z0-9]{2,}', s):
        toks.add(w.lower())
    return toks


def load_kb(force=False):
    """加载并缓存知识库分块（首次调用时执行）"""
    global _chunks, _df, _df_common
    with _load_lock:
        if _chunks is not None and not force:
            return _chunks
        chunks = []
        for path in _iter_kb_files():
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
            except Exception as e:
                print(f"[知识库] 读取失败 {path}: {e}")
                continue
            source = os.path.basename(path)
            for title, body in _split_chunks(text, source):
                chunks.append((title, body, _tokens(title + ' ' + body, clean=False)))
        _chunks = chunks
        df = {}
        for _t, _b, toks in chunks:
            for t in toks:
                df[t] = df.get(t, 0) + 1
        _df = df
        _df_common = {t for t, c in df.items() if c > max(4, int(len(chunks) * 0.35))}
        print(f"[知识库] 已加载 {len(chunks)} 个片段（{KB_DIR}）")
        return _chunks


def _query_tokens(query):
    """问题侧词元：去掉疑问词/虚词与高频泛词"""
    return {t for t in _tokens(query, clean=True) if t not in _STOPWORDS and t not in _df_common}


def _specific_tokens(query):
    """问题里"有信息量"的词元（非泛词）。用它判断资料是否真的答得上这个问题。"""
    return {t for t in _query_tokens(query) if _df.get(t, 0) < GENERIC_DF}


def search_kb(query, top_k=3):
    """返回 [(分数, 标题, 正文)]，按分数降序（调试/外部使用）"""
    chunks = load_kb()
    if not chunks or not query:
        return []
    q = _query_tokens(query)
    if not q:
        return []
    scored = []
    for title, body, toks in chunks:
        hit = q & toks
        if not hit:
            continue
        score = sum(2 if len(t) > 2 else 1 for t in hit) + 2 * len(q & _tokens(title, clean=False))
        scored.append((score, title, body))
    scored.sort(key=lambda x: -x[0])
    return scored[:top_k]


# ==================== 联网补充（优先学校官网）====================
def _web_flag_on():
    try:
        with open(MORE_SET_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return str(data.get('知识库联网补充(可选项:on/off)', 'on')).strip().lower() != 'off'
    except Exception:
        return True


def looks_school_related(msg):
    if not msg:
        return False
    low = msg.lower()
    return any(k.lower() in low for k in _SCHOOL_KEYWORDS)


def _baidu_search(query, num=5, timeout=WEB_TIMEOUT_SECONDS):
    """带超时的百度检索（websearch.search 内部没有超时设置，这里用子线程兜底）"""
    from websearch import search
    box = {}

    def worker():
        try:
            box['res'] = search(query, num_results=num) or []
        except Exception:
            box['res'] = []

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout)
    return box.get('res', []) if not t.is_alive() else []


def web_lookup(msg, max_items=4):
    """联网检索学校信息：**只采信南京工程学院官网(njit.edu.cn)的结果**。
    官网搜不到就返回空 → 交给"没有可靠收录"话术，绝不拿网上杂内容凑数。"""
    if not msg or not _web_flag_on() or not reception.search_topic_approved(msg):
        return ""
    key = (msg, max_items)
    if key in _web_cache:
        return _web_cache[key]
    result = ''
    try:
        items = _baidu_search(f'{msg} 南京工程学院 site:{SCHOOL_SITE}', num=8)
        lines = []
        for it in items:
            url = (it.get('url') or '')
            abstract = (it.get('abstract') or '').strip()
            if SCHOOL_SITE not in url or not abstract:  # 过滤掉广告/无关站点
                continue
            lines.append(f"- {(it.get('title') or '').strip()}：{abstract}")
            if len(lines) >= max_items:
                break
        if lines:
            result = '\n'.join(lines)
    except Exception as e:
        print(f"[知识库] 联网检索失败: {e}")
        result = ''
    _web_cache[key] = result
    return result


# ==================== 对外入口 ====================
def _material(msg, top_k=3, allow_web=True):
    """返回 (资料正文, 最高分, 是否切题)。按消息缓存，避免重复检索/重复联网。"""
    key = (msg, top_k, allow_web)
    if key in _material_cache:
        return _material_cache[key]

    chunks = load_kb()
    q = _query_tokens(msg)
    if not q and is_school_fact_question(msg):
        # 问题只由"南京工程学院/学校"这类泛词组成（例如"介绍一下南京工程学院"）：
        # 上面的过滤会把它们全当高频词去掉，这里退回用泛词检索，给出学校概况类资料
        q = {t for t in _tokens(msg, clean=True) if t not in _STOPWORDS}
    idx_scores = []
    matched = set()
    for title, body, toks in chunks:
        hit = q & toks
        if not hit:
            continue
        matched |= hit
        score = sum(2 if len(t) > 2 else 1 for t in hit) + 2 * len(q & _tokens(title, clean=False))
        idx_scores.append((score, title, body))
    idx_scores.sort(key=lambda x: -x[0])
    best = idx_scores[0][0] if idx_scores else 0

    # 关键：只命中"学校/学院"这类泛词不算资料切题；
    # 问题里的具体词一个都没命中（如"游泳馆""奶茶店"），说明知识库答不上这个具体问题
    specific = _specific_tokens(msg)
    relevant = (not specific) or bool(specific & matched)
    body = ''
    if idx_scores and best >= MIN_SCORE and relevant:
        body = '【本地知识库】\n' + '\n\n'.join(f"〔{t}〕\n{b}" for _, t, b in idx_scores[:top_k])
    elif not relevant:
        best = 0

    if allow_web and best < MIN_SCORE and looks_school_related(msg):
        web = web_lookup(msg)
        if web:
            body = ('【联网检索结果（南京工程学院官网 njit.edu.cn）】\n' + web +
                    '\n（联网结果仅作参考，与本地知识库冲突时以本地知识库为准）')
            best = max(best, 1)

    _material_cache[key] = (body, best, relevant)
    return _material_cache[key]


def build_prompt_context(msg, top_k=3, allow_web=True):
    """给 system prompt 用的事实约束 + 资料。
    事实约束**每次都会给**（这是防止模型凭空编造的关键）；有资料时再附上资料。"""
    body, _best, _rel = _material(msg, top_k=top_k, allow_web=allow_web)
    if body:
        return f"\n\n{FACT_RULE_SHORT}\n{KB_RULES}\n\n{body}\n"
    return f"\n\n{FACT_RULE_SHORT}\n"


def is_school_fact_question(msg):
    """是不是"关于学校具体事实的提问"（是的话，没资料就必须用固定话术）"""
    if not msg or not looks_school_related(msg):
        return False
    if any(k in msg for k in _FACT_ASK):
        return True
    return bool(_FACT_ASK_RE.search(msg))


def should_refuse(msg, allow_web=True):
    """需要"没有可靠收录"固定话术时返回话术，否则返回 None"""
    if not is_school_fact_question(msg):
        return None
    # 知识库明确要求"不得凭空回答"的主题：一律如实说查不到（即使检索到了只提到这个词的片段）
    if any(k in msg for k in _NEVER_ANSWER):
        return random.choice(REFUSE_TEXTS)
    body, _best, _rel = _material(msg, allow_web=allow_web)
    if body:
        return None
    return random.choice(REFUSE_TEXTS)
