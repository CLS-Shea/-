from agent import *
import roles
import reception
from threading import Event, Thread
import time


def _reception_reply(msg):
    """现场接待专用请求：单请求、8 秒超时，迟到结果不再播报。"""
    if msg.strip() == reception.fixed_intro_trigger():
        notice("正在播放学院介绍")
        stream_insert(f"{roles.current_role_name() or mate_name}:\n    {reception.fixed_intro_text()}\n")
        reception.set_intro_playing(True)
        try:
            get_tts_play(reception.fixed_intro_text())
        finally:
            reception.set_intro_playing(False)
        reception.touch()
        return

    request_id = reception.begin_request()
    result_box = {}
    done = Event()

    def worker():
        try:
            result_box["text"] = chat_llm(msg)
        except Exception as exc:
            result_box["error"] = exc
        finally:
            done.set()

    Thread(target=worker, daemon=True).start()
    if not done.wait(reception.request_timeout_seconds()):
        notice("本次回答超时，请稍后重试")
        stream_insert(f"{roles.current_role_name() or mate_name}:\n    网络或问答服务响应超时，请稍后再试。\n")
        return
    if not reception.request_current(request_id):
        return
    if "error" in result_box:
        notice("问答服务暂时不可用")
        stream_insert(f"{roles.current_role_name() or mate_name}:\n    问答服务暂时不可用，请稍后再试。\n")
        return
    bot_response = limit_reply_length(result_box.get("text", ""), max_len=100)
    _rname = roles.current_role_name() or mate_name
    stream_insert(f"{_rname}:\n    {bot_response}\n")
    Thread(target=get_tts_play, args=(bot_response,), daemon=True).start()
    reception.touch()


def reception_watchdog():
    """现场模式空闲回收：结束一轮接待并恢复南小橙待机。"""
    while reception.enabled():
        try:
            if reception.idle_expired() and not reception.intro_playing():
                stop_tts()
                reception.finish_session()
                roles.switch_role(reception.CONFIG["default_role"])
                try:
                    clear_chat()
                except Exception:
                    pass
                notice("本轮接待结束，已回到待机")
            time.sleep(0.5)
        except Exception as exc:
            print(f"[现场接待] 状态回收失败: {exc}")
            time.sleep(1)


def common_chat(msg):  # 通用对话
    if reception.enabled():
        _reception_reply(msg)
        return
    output_box.insert("end", f"\n{username}:\n    {msg}\n")
    output_box.see("end")
    notice(f"{mate_name}正在思考中，请稍等...")
    # 天气关键词检测：无论哪种模式都优先走天气API（LLM没有实时天气数据）
    weather_keywords = ["天气", "气温", "下雨", "下雪", "刮风", "晴天", "阴天", "多少度", "冷不冷", "热不热",
                        "带伞", "降雨", "降雪", "台风", "雾霾", "空气"]
    if any(kw in msg for kw in weather_keywords) and ("什么" in msg or "吗" in msg or "么" in msg or "样" in msg
                                                       or "不" in msg or "如何" in msg or "没" in msg or len(msg) < 15):
        get_weather(msg)
        return
    # 日期时间关键词检测：注入当前时间后直接走LLM，避免被意图识别误判为"系统状态查询"
    time_keywords = ["几点", "多少点", "时间", "时候", "日期", "多少号", "几号", "星期", "周几", "礼拜", "几月", "日子", "年月日"]
    if any(kw in msg for kw in time_keywords):
        msg_with_time = f"[当前时间:{current_time()}]{msg}"
        normal_chat(msg_with_time)
        return
    if mode_menu.get() == "多智能体助手":
        user_task = user_intent_recognition(msg)
        notice(f"{mate_name}调用了[{user_task}]智能体")
        task_handlers = {
            "音乐播放": (play_music, (msg,)), "语音输入": (voice_input, (msg,)),
            "打开软件/网页": (open_app_select, (msg,)), "音量减小": (vol_down, ()), "音量增大": (vol_up, ()),
            "文本写作": (auto_input, (msg,)), "翻译屏幕内容": (translate_screen, (msg,)),
            "解释屏幕内容": (explain_screen, (msg,)), "总结屏幕内容": (summary_screen, (msg,)),
            "续写屏幕内容": (continue_write_screen, (msg,)), "灯类智能家居控制": (control_ha, ()),
            "天气查询": (get_weather, (msg,)), "热搜新闻": (get_news, (msg,)),
            "系统状态查询": (get_system_state, (msg,)), "联网搜索": (ol_search, (msg,)),
            "视频生成": (generate_video, (msg,))}
        for task, (handler, args) in task_handlers.items():
            if task in user_task:
                handler(*args)
                break
        else:
            normal_chat(msg)
    else:
        normal_chat(msg)


def normal_chat(msg):  # 普通对话
    bot_response = chat_preprocess(msg)
    bot_response = bot_response.replace("#", "").replace("*", "")
    bot_response = limit_reply_length(bot_response)  # 大屏互动：控制回复长度，语音输出更简洁
    _rname = roles.current_role_name() or mate_name  # 大屏双角色：显示当前角色名
    # 先开始文字流式输出（打字机效果）
    stream_insert(f"{_rname}:\n    {bot_response}\n")
    # 再启动语音合成与播放（与文字输出重叠进行）
    Thread(target=get_tts_play, args=(bot_response,)).start()


# open_source_project_address:https://github.com/swordswind/ai_virtual_mate_web
def open_app_select(msg):  # 打开软件
    def find_app_path(app_path):
        possible_paths = [
            f"C:/Program Files (x86)/{app_path}", f"C:/Program Files/{app_path}", f"D:/Program Files (x86)/{app_path}",
            f"D:/Program Files/{app_path}", f"E:/Program Files (x86)/{app_path}", f"E:/Program Files/{app_path}",
            f"F:/Program Files (x86)/{app_path}", f"F:/Program Files/{app_path}",
            os.path.join(os.environ['APPDATA'], app_path)]
        for path2 in possible_paths:
            if os.path.exists(path2):
                return path2
        return None

    def open_app(app_name2, app_path):
        app_full_path = find_app_path(app_path)
        if app_full_path:
            Popen(app_full_path)
            notice(f"{mate_name}打开了{app_name2}")
            get_tts_play(f"好的，已为您打开{app_name2}")
        else:
            stream_insert(f"{mate_name}:\n    未找到{app_name2}安装路径\n")
            notice(f"未找到{app_name2}安装路径")
            get_tts_play(f"未找到{app_name2}安装路径")

    app_mappings = {
        '微信': ('微信', 'Tencent/Weixin/Weixin.exe'), 'QQ': ('QQ', 'Tencent/QQNT/QQ.exe'),
        '文档': ('Word文档', 'Microsoft Office/root/Office16/WINWORD.EXE'),
        '音乐': ('网易云音乐', 'NetEase/CloudMusic/cloudmusic.exe'),
        '崩坏': ('崩坏：星穹铁道', 'miHoYo Launcher/games/Star Rail Game/StarRail.exe'),
        '原神': ('原神', 'miHoYo Launcher/games/Genshin Impact Game/YuanShen.exe'),
        '绝区零': ('绝区零', 'miHoYo Launcher/games/ZenlessZoneZero Game/ZenlessZoneZero.exe'),
        '记事本': ('记事本', None), '便签': ('记事本', None), '备忘录': ('记事本', None), '笔记': ('记事本', None),
        '计算器': ('计算器', None), '文件管理': ('资源管理器', None), '资源管理': ('资源管理器', None),
        '任务管理': ('任务管理器', None), '画图': ('画图工具', None), '绘图': ('画图工具', None), '控制面板': ('控制面板', None)}
    special_commands = {'悟空': ('黑神话：悟空', 'steam://rungameid/2358720', wb.open),
                        '我的世界': ('我的世界', 'fevergames://mygame/?gameId=1', wb.open)}
    builtin_commands = {
        '记事本': ('notepad', Popen), '计算器': ('calc', Popen), '资源管理器': ('explorer', Popen),
        '任务管理器': ('taskmgr', Popen), '画图工具': ('mspaint', Popen), '控制面板': ('control', Popen)}
    for keyword, (app_name, path, func) in special_commands.items():
        if keyword in msg:
            func(path)
            notice(f"{mate_name}打开了{app_name}")
            get_tts_play(f"好的，已为您打开{app_name}")
            return
    for keyword, (app_name, path) in app_mappings.items():
        if keyword in msg:
            if path is None:
                cmd, func = builtin_commands[app_name]
                func(cmd)
                notice(f"{mate_name}打开了{app_name}")
                get_tts_play(f"好的，已为您打开{app_name}")
            else:
                open_app(app_name, path)
            return
    try:
        content = function_llm(
            "请你扮演一个Windows CMD命令转换器。每当我输入自然语言命令时，你必须仅输出对应的CMD命令，不能添加任何其他文字或说明。",
            msg)
        result = os.system(content)
        if result == 0:
            notice(f"{mate_name}接管了电脑")
        else:
            text_to_cmd_error = "抱歉，这个我还不会，可尝试更换对话语言模型"
            stream_insert(f"{mate_name}:\n    {text_to_cmd_error}\n")
            notice(text_to_cmd_error)
            get_tts_play(text_to_cmd_error)
    except:
        text_to_cmd_error = "暂不支持打开该软件"
        stream_insert(f"{mate_name}:\n    {text_to_cmd_error}\n")
        notice(text_to_cmd_error)
        get_tts_play(text_to_cmd_error)
