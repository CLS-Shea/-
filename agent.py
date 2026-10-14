import psutil
import pynvml as nv
from xml.etree import ElementTree
from homeassistant_api import Client as hClient
from ping3 import ping
from websearch import search
from ase import *
import kb  # 本地知识库 + 学校官网检索（学校类问题避免编造）

def user_intent_recognition(msg):  # 意图识别
    return function_llm(
        """1、你是一个严格的意图匹配器，必须完全遵守以下约束：
   - 仅从提供的意图清单中选择输出
   - 禁止添加任何解释、说明或额外文本
   - 禁止修改或扩展意图清单内容
   - 若用户意图不在清单中则输出"日常闲聊"
   2、处理流程：
   - 步骤1：将用户输入与清单进行精确匹配
   - 步骤2：找到最接近的意图项（必须完全匹配）
   - 步骤3：输出且仅输出匹配到的意图词汇""",
        f"{all_task}。上面是可以使用的意图清单，你只能在上面的意图清单中的内容进行选择输出。下面是用户的消息，请你对其中的意图进行提取：{msg}。仅需输出提取后的意图，不要输出其他内容")


def play_music(song_name):  # 播放音乐
    music_folder = "data/music"
    try:
        mp3_files = [f for f in os.listdir(music_folder) if f.endswith('.mp3')]
        for character in song_name:
            matched_songs = [song for song in mp3_files if character in song]
            if matched_songs:
                selected_song = random.choice(matched_songs)
                song_name = selected_song.replace(".mp3", "").replace("data/music\\", "")
                stream_insert(f"{mate_name}:\n    好的，为您送上{song_name}\n")
                break
        else:
            selected_song = random.choice(mp3_files)
            song_name = selected_song.replace(".mp3", "").replace("data/music\\", "")
            stream_insert(f"{mate_name}:\n    好的，为您送上{song_name}\n")
        pg.mixer.init()
        get_tts_play(f"好的，为您送上{song_name}")
        time.sleep(6)
        pg.mixer.init()
        while pg.mixer.music.get_busy():
            pg.time.Clock().tick(1)
        time.sleep(0.1)
        pg.mixer.init()
        pg.mixer.music.load(os.path.join(music_folder, selected_song))
        pg.mixer.music.play()
        while pg.mixer.music.get_busy():
            pg.time.Clock().tick(1)
    except:
        notice("音乐文件夹位于data/music，可放入格式为mp3的音乐")


def auto_input(text):  # 接管电脑自动写作
    stream_insert(f"{mate_name}:\n    请将鼠标移动到想输入的地方\n")
    get_tts_play("请将鼠标移动到想输入的地方")
    content = function_llm("你是一个专业且高水平的写作助手，回答只需输出写作的内容，不要输出其他内容。", text)
    content = f"{content}\n(以上内容由AI生成)"
    get_tts_play("正在写作")
    for char in content:
        kb.write(char)
        time.sleep(0.01)


def translate_screen(msg):  # 翻译屏幕内容
    get_tts_play("正在翻译，请稍等")
    res = function_vlm(f"你是一个专业的翻译官，请你完整阅读图片中电脑屏幕中的文章的内容，回答只需用中文输出翻译后的内容。我的需求是：{msg}")
    get_tts_play("翻译完成")
    stream_insert(f"{mate_name}:\n    【翻译结果】{res}\n")


def explain_screen(msg):  # 解释屏幕内容
    get_tts_play("正在解释，请稍等")
    res = function_vlm(f"你是一个专业的解释大师，请你完整阅读图片中电脑屏幕中的内容，回答只需用中文输出解释后的内容。我的需求是：{msg}")
    get_tts_play("解释完成")
    stream_insert(f"{mate_name}:\n    【解释结果】{res}\n")


def summary_screen(msg):  # 总结屏幕内容
    get_tts_play("正在总结，请稍等")
    res = function_vlm(f"你是一个专业的总结大师，请你完整阅读图片中电脑屏幕中的内容，回答只需用中文输出总结后的内容。我的需求是：{msg}")
    get_tts_play("总结完成")
    stream_insert(f"{mate_name}:\n    【总结结果】{res}\n")


def continue_write_screen(msg):  # 续写屏幕内容
    get_tts_play("请将鼠标移动到想续写的地方")
    content = function_vlm(f"你是一个专业且高水平的续写助手，请你完整阅读图片中电脑屏幕中的文章的内容，回答只需输出续写的内容，不要输出其他内容。我的需求是：{msg}")
    content = f"{content}\n(以上内容由AI生成)"
    get_tts_play("正在续写")
    stream_insert(f"{mate_name}:\n    开始续写...\n")
    for char in content:
        kb.write(char)
        time.sleep(0.01)


def control_ha():  # Home Assistant智能家居控制
    def control_ha2():
        try:
            client = hClient(f"http://{ha_api}/api/", ha_key)
            button = client.get_domain("button")
        except Exception as e:
            notice(f"请前往data/set/home_assistant_set.txt正确配置Home Assistant API，错误详情：{e}")
            return "Home Assistant API配置错误"
        try:
            result = button.press(entity_id=entity_id)
            if len(result) == 0:
                notice("设备不在线")
                return "设备不在线"
        except:
            notice("设备不在线")
            return "设备不在线"
        return "操作成功"

    ha_result = control_ha2()
    get_tts_play(ha_result)


# open_source_project_address:https://github.com/swordswind/ai_virtual_mate_web
def get_weather(msg):  # 天气查询
    def get_weather2():
        def extract_weather_city_name(msg2):  # 提取天气城市名称
            return cloud_function_llm(
                "你是一个专业的城市名称提取器，需要把用户输入信息中想查询的城市名称提取出来。仅需输出提取后的城市名称，不要输出其他内容",
                f"下面是用户的消息，请你对其中的城市名称进行提取：{msg2}。仅需输出提取后的城市名称，不要输出其他内容。如果用户输入不包含城市名称，则输出{weather_city}")

        try:
            input_city = extract_weather_city_name(msg)
            # 方案1: 使用 wttr.in API（免费、无需Key、全球城市都支持）
            try:
                # 用中文城市名查询，wttr.in会自动识别
                api_url = f"https://wttr.in/{input_city}?format=j1&lang=zh"
                res = rq.get(api_url, timeout=10).json()
                current = res['current_condition'][0]
                weather_desc = current['lang_zh'][0]['value']
                temp = current['temp_C']
                humidity = current['humidity']
                wind = current['windspeedKmph']
                wind_dir = current['winddir16Point']
                weather_result = (f"{input_city}：{weather_desc}，"
                                  f"气温{temp}度，湿度{humidity}%，"
                                  f"{wind_dir}风{wind}公里/时")
            except:
                # 方案2: 备用 - 使用 Open-Meteo API（免费、无需Key）
                try:
                    # 先通过geocoding获取城市坐标
                    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={input_city}&count=1&language=zh"
                    geo_res = rq.get(geo_url, timeout=10).json()
                    if 'results' in geo_res and len(geo_res['results']) > 0:
                        lat = geo_res['results'][0]['latitude']
                        lon = geo_res['results'][0]['longitude']
                        city_name = geo_res['results'][0].get('name', input_city)
                        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&timezone=auto"
                        weather_res = rq.get(weather_url, timeout=10).json()
                        cw = weather_res['current_weather']
                        temp = cw['temperature']
                        wind = cw['windspeed']
                        code = cw.get('weathercode', 0)
                        weather_codes = {0:"晴朗",1:"大部晴朗",2:"多云",3:"阴天",45:"雾",48:"雾凇",
                                         51:"小毛毛雨",53:"毛毛雨",55:"大毛毛雨",61:"小雨",63:"中雨",65:"大雨",
                                         71:"小雪",73:"中雪",75:"大雪",80:"阵雨",81:"中阵雨",82:"大阵雨",
                                         85:"小雪阵",86:"大雪阵",95:"雷暴"}
                        w_desc = weather_codes.get(code, f"代码{code}")
                        weather_result = (f"{city_name}：{w_desc}，"
                                          f"气温{temp}度，风力{wind}公里/时")
                    else:
                        weather_result = "未找到该城市信息，请输入国内城市名"
                except:
                    weather_result = "气象服务暂时不可用，请稍后再试"
            return cloud_function_llm(
                "请你扮演一名专业的天气观察员和我对话，阅读我给你的天气信息，并简要地回答我的问题，输出为一句话，不要分段，不要用MarkDown格式",
                f"{weather_result}。上面是天气信息，请你根据天气信息，回答我的问题，我的问题是：{msg}？回答不要超过100个字")
        except:
            return "气象服务暂时不可用，请稍后再试"

    res2 = limit_reply_length(get_weather2())  # 大屏互动：控制回复长度
    stream_insert(f"{mate_name}:\n    {res2}\n")
    get_tts_play(res2)


def get_news(msg):  # 新闻查询
    def get_news2():
        def get_news_from_wb():
            response = rq.get('https://weibo.com/ajax/side/hotSearch')
            result = response.json()['data']
            hot_names = []
            for item in result.get('realtime', []):
                hot_names.append(item.get('word', ''))
            return '\n'.join(hot_names)

        def get_news_from_zxw(news_url):
            res = rq.get(news_url)
            xml_content = res.content.decode("utf-8")
            root1 = ElementTree.fromstring(xml_content)
            titles = []
            for item in root1.findall(".//item"):
                title_elem = item.find("title")
                if title_elem is not None and title_elem.text:
                    titles.append(title_elem.text.strip())
            result = "\n".join(titles)
            return result

        try:
            if "微博" in msg:
                news_result = get_news_from_wb()
            elif "世界" in msg or "国际" in msg:
                news_result = get_news_from_zxw("https://www.chinanews.com.cn/rss/world.xml")
            elif "财经" in msg or "经济" in msg:
                news_result = get_news_from_zxw("https://www.chinanews.com.cn/rss/finance.xml")
            else:
                news_result = get_news_from_zxw("https://www.chinanews.com.cn/rss/society.xml")
            return cloud_function_llm(
                "请你扮演一名专业的新闻评论员和我对话，完整阅读我给你的新闻热搜，并简要地回答我的问题，输出为一段话，不要分段，不要用MarkDown格式",
                f"{news_result}。上面是完整的新闻热搜，请你根据这些热搜，分析并发表你的观点见解并回答我的问题，我的问题是：{msg}？回答不要超过100个字")
        except:
            return "新闻服务维护中，请一段时间后再试"

    res2 = limit_reply_length(get_news2())  # 大屏互动：控制回复长度
    stream_insert(f"{mate_name}:\n    {res2}\n")
    get_tts_play(res2)


def get_system_state(msg):  # 系统状态查询
    def get_system_state2():
        try:
            cpu_usage = psutil.cpu_percent(interval=1)
            memory_usage = psutil.virtual_memory().percent
            try:
                web_ping = int(ping('www.baidu.com', unit='ms', timeout=10))
                game_ping = int(ping('www.qq.com', unit='ms', timeout=10))
                if web_ping == 0 and game_ping == 0:
                    web_ping, game_ping = "超时", "超时"
            except:
                web_ping, game_ping = "超时", "超时"
            try:
                nv.nvmlInit()
                gpu_handle = nv.nvmlDeviceGetHandleByIndex(0)
                temperature = nv.nvmlDeviceGetTemperature(gpu_handle, 0)
                gpu_usage = nv.nvmlDeviceGetUtilizationRates(gpu_handle).memory
                system_state = f"CPU占用{cpu_usage}%；内存占用{memory_usage}%；GPU占用{gpu_usage}%，温度{temperature}℃；网页平均延迟{web_ping}ms；游戏平均延迟{game_ping}ms"
            except:
                system_state = f"CPU占用{cpu_usage}%；内存占用{memory_usage}%；网页平均延迟{web_ping}ms；游戏平均延迟{game_ping}ms"
            return cloud_function_llm(
                "请你扮演一名专业的电脑系统状态分析员和我对话，阅读我给你的系统状态信息，并简要地回答我的问题，输出为一句话，不要分段，不要用MarkDown格式",
                f"{system_state}。上面是系统状态，请你根据系统状态，回答我的问题，我的问题是：{msg}？回答不要超过100个字")
        except:
            return "获取系统状态失败"

    res = limit_reply_length(get_system_state2())  # 大屏互动：控制回复长度
    stream_insert(f"{mate_name}:\n    {res}\n")
    get_tts_play(res)


def ol_search(msg):  # 联网搜索
    def ol_search2():
        msg2 = re.sub(r"联网|连网|搜索|查|查询|查找|资料", "", msg)
        try:
            # 学校相关问题：优先限定南京工程学院官网检索，并把本地知识库一起给模型，避免编造校情
            school = kb.looks_school_related(msg)
            results = search(f"{msg2} 南京工程学院 site:{kb.SCHOOL_SITE}" if school else msg, num_results=5)
            if school and len(results) < 2:
                results = search(f"{msg2} 南京工程学院 官网", num_results=5)
            if not results:
                raise RuntimeError("无搜索结果")
            search_result = "".join((r.get('abstract') or '') for r in results[:5])
            sys_prompt = "你是一个专业的搜索总结助手，我输入我的问题和杂乱的内容，你输出整理好的内容为详细的一段话，不要分段，不要用MarkDown格式"
            sys_prompt += kb.build_prompt_context(msg, allow_web=False)  # 已自行搜过网，不重复检索
            return cloud_function_llm(
                sys_prompt,
                f"{search_result}。上面是完整的搜索结果，请你根据这些搜索结果，分析并回答我的问题，我的问题是：{msg2}？回答不要超过100个字")
        except:
            return "联网搜索服务维护中，请一段时间后再试"

    res = limit_reply_length(ol_search2())  # 大屏互动：控制回复长度
    stream_insert(f"{mate_name}:\n    {res}\n")
    get_tts_play(res)


def generate_video(msg):  # 视频生成
    def generate_video_th():
        msg2 = re.sub(r"生成视频|视频生成|做视频|制作视频", "", msg)
        bot_response = "正在生成视频，请稍等约30秒..."
        stream_insert(f"{mate_name}:\n    {bot_response}\n")
        get_tts_play(bot_response)
        cogvideo_error = "云端CogVideo视频生成未正确配置，请前往软件设置→云端AI Key设置GLM智谱BigModel开放平台key"
        try:
            client = ZhipuAI(api_key=glm_key)
            res = client.videos.generations(model="cogvideox-flash", prompt=msg2, quality="speed",
                                            with_audio=False, size="720x480", fps=30)
            task_id = res.id
            while True:
                result = client.videos.retrieve_videos_result(id=task_id)
                if result.task_status == 'SUCCESS':
                    video_url = result.video_result[0].url
                    res = rq.get(video_url, stream=True)
                    video_path = "data/cache/video_aigc.mp4"
                    with open(video_path, 'wb') as f:
                        for chunk in res.iter_content(chunk_size=1024):
                            f.write(chunk)
                    notice(f"视频生成完成，已保存至{video_path}.mp4")
                    os.startfile("data\\cache\\video_aigc.mp4")
                    break
                elif result.task_status == 'FAIL':
                    notice(cogvideo_error)
                    break
                else:
                    time.sleep(1)
        except:
            notice(cogvideo_error)

    Thread(target=generate_video_th).start()
