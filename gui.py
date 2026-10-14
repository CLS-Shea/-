import wave
import pyaudio
from base64 import b64decode
from threading import Thread
from openai import OpenAI
from gui_sub import *


# open_source_project_address:https://github.com/swordswind/ai_virtual_mate_web
def open_setting_w():  # 设置窗口
    def show_menu_set(event):
        menu = Menu(setting_w, tearoff=0)
        menu.add_command(label="✂剪切 Ctrl+X", command=lambda: setting_w.focus_get().event_generate('<<Cut>>'))
        menu.add_command(label="📄复制 Ctrl+C", command=lambda: setting_w.focus_get().event_generate('<<Copy>>'))
        menu.add_command(label="📋粘贴 Ctrl+V", command=lambda: setting_w.focus_get().event_generate('<<Paste>>'))
        menu.add_separator()
        menu.add_command(label="🗑删除 Del", command=lambda: setting_w.focus_get().event_generate('<<Clear>>'))
        menu.post(event.x_root, event.y_root)

    def save_and_close():
        new_config = {
            "虚拟伙伴名称": mate_name_entry.get(),
            "虚拟伙伴人设": prompt_text.get("1.0", "end").replace("\n", ""),
            "用户名": username_entry.get(), "VITS-ONNX模型名": vits_menu.get(), "PaddleTTS语速": rate_menu.get(),
            "PaddleTTS语言": lang_menu.get(), "对话网页端口": chatweb_port_entry.get(),
            "L2D角色网页端口": live2d_port_entry.get(), "MMD角色网页端口": mmd_port_entry.get(),
            "VRM角色网页端口": vrm_port_entry.get(), "本地LLM服务器IP": llm_server_ip_entry.get(),
            "AnythingLLM工作区": allm_ws_entry.get(), "摄像头权限": cam_permission_menu.get(),
            "AnythingLLM密钥": allm_key_entry.get(), "Ollama大语言模型": ollama_model_name_entry.get(),
            "流式语音合成开关": stream_tts_menu.get(), "自定义API-base_url": custom_url_entry.get(),
            "自定义API-api_key": custom_key_entry.get(), "自定义API-model": custom_model_entry.get(),
            "实时语音开关键": voice_key_entry.get(), "对话网页开关": web_switch_menu.get(),
            "桌面宠物置顶": pet_top_menu.get(), "Ollama多模态VLM": ollama_vlm_name_entry.get(),
            "自定义语音唤醒词": wake_word_entry.get(), "桌宠位置x": pet_x_entry.get(),
            "桌宠位置y": pet_y_entry.get(), "实时语音打断": voice_break_menu.get(),
            "语音识别灵敏度": asr_sensi_menu.get(), "默认天气城市": weather_city_entry.get(),
            "Dify知识库IP": dify_ip_entry.get(), "Dify知识库密钥": dify_key_entry.get(),
            "edge-tts音色": edge_speaker_menu.get(), "edge-tts语速": edge_rate_entry.get(),
            "edge-tts音高": pitch_entry.get(), "自定义API-VLM": custom_vlm_entry.get(),
            "图像生成引擎": draw_menu.get(), "声纹识别": voiceprint_sw_menu.get()}
        with open('data/db/config.json', 'w', encoding='utf-8') as f:
            json.dump(new_config, f, ensure_ascii=False, indent=4)
        messagebox.showinfo("保存成功", "保存成功！重启软件生效")
        setting_w.destroy()

    def restore_set():
        if messagebox.askokcancel("恢复默认设置", "您确定要重置枫云AI虚拟伙伴吗？\n记忆、聊天记录不受影响"):
            with open('data/db/config.json', 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, indent=4)
            with open('data/db/init.db', 'w', encoding="utf-8") as f:
                f.write("0")
            with open('data/set/custom_tts_set.txt', 'w', encoding='utf-8') as f:
                f.write('[base_url]\n把该行替换为服务提供方地址，例如 https://api.siliconflow.cn/v1/\n\n')
                f.write('[model]\n把该行替换为服务提供方支持的模型名称，例如 FunAudioLLM/CosyVoice2-0.5B\n\n')
                f.write('[voice]\n"把该行替换为服务提供方支持的发音人名称，例如 FunAudioLLM/CosyVoice2-0.5B:anna"\n\n')
                f.write('[api_key]\n把该行替换为从服务提供方控制台获取的密钥，例如 sk-xxxxxxxxxx')
            with open('data/db/vrm_model_name.db', 'w', encoding="utf-8") as f:
                f.write("小月.vrm")
            try:
                from sys_init import build_live2d_js as _build_live2d
                _build_live2d()  # 大屏双角色：重新生成双角色 live2d.js（模型配置在 roles.json）
            except Exception:
                pass
            with open('dist/assets/mmd_core/mmd_js_set.txt', 'w', encoding='utf-8') as f:
                f.write('[模型路径]\n小月/小月.pmx\n\n')
                f.write('[动作路径]\nexample.vmd\n\n')
                f.write('[模型嘴索引]\n135\n\n')
                f.write('[模型眼索引]\n60')
            with open('dist/assets/mmd.js', 'w', encoding='utf-8') as f:
                f.write(
                    mmd_js_part1 + "小月/小月.pmx" + mmd_js_part2 + "133" + mmd_js_part3 + "60" + mmd_js_part4)
            with open('dist/assets/mmd_vmd.js', 'w', encoding='utf-8') as f:
                f.write(
                    mmd_vmd_js_part1 + "小月/小月.pmx" + mmd_vmd_js_part2 + "example.vmd" + mmd_vmd_js_part3)
            with open('data/set/more_set.json', 'w', encoding="utf-8") as f:
                json.dump(default_more_set, f, ensure_ascii=False, indent=4)
            with open('data/set/cloud_ai_key_set.json', 'w', encoding="utf-8") as f:
                json.dump(default_cloud_ai_key_set, f, ensure_ascii=False, indent=4)
            with open('data/set/home_assistant_set.txt', 'w', encoding='utf-8') as f:
                f.write('[Home Assistant服务器地址]\n把该行替换为HA服务器地址，例如 127.0.0.1:8123\n\n')
                f.write('[实体ID(仅支持按钮)]\n把该行替换为实体ID，例如 button.yeelink_cn_xxxxxxxxx_lamp4_toggle_a_2_1\n\n')
                f.write('[长期访问令牌]\n把该行替换为长期访问令牌，例如 xxxx.xxxx.xxxx-xxxx')
            messagebox.showinfo("恢复默认设置成功", "恢复默认设置成功！重启软件生效")
            setting_w.destroy()

    def custom_api_test():
        def custom_api_test_th():
            test_client = OpenAI(api_key=custom_key_entry.get(), base_url=custom_url_entry.get())
            try:
                response = test_client.models.list()
                model_ids = "\n".join([model.id for model in response.data])
                msg_box("自定义API测试成功", f"自定义API支持的模型列表:\n{model_ids}")
            except Exception as e:
                messagebox.showinfo("自定义API测试失败", f"自定义API测试失败，错误信息:\n{e}")

        Thread(target=custom_api_test_th).start()

    def ollama_test():
        def ollama_test_th():
            try:
                try:
                    rq.get(f'http://{local_llm_ip}:{ollama_port}')
                except:
                    Popen("ollama ps", shell=False)
            except:
                print("本地Ollama未安装")
            url = f'http://{local_llm_ip}:{ollama_port}/api/tags'
            try:
                response = rq.get(url)
                models = response.json().get('models', [])
                model_names = [model['name'] for model in models]
                model_ids = '\n'.join(model_names)
                msg_box("本地Ollama测试成功", f"本地Ollama支持的模型列表:\n{model_ids}")
            except Exception as e:
                messagebox.showinfo("本地Ollama测试失败", f"本地Ollama测试失败，错误信息:\n{e}")

        Thread(target=ollama_test_th).start()

    def open_voiceprint_manage():
        FILE_PATH = 'data/cache/voiceprint/myvoice.wav'
        FORMAT = pyaudio.paInt16
        CHANNELS, RATE, CHUNK = 1, 16000, 1024
        RECORD_SECONDS = 5

        def record_audio():
            p = pyaudio.PyAudio()
            stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK,
                            input_device_index=mic_num)
            print("开始录音...")
            frames = []
            for _ in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
                data = stream.read(CHUNK)
                frames.append(data)
            print("录音结束")
            stream.stop_stream()
            stream.close()
            p.terminate()
            wf = wave.open(FILE_PATH, 'wb')
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(p.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(b''.join(frames))
            wf.close()
            messagebox.showinfo("成功",
                                f"声纹录制完成\n您可以在软件设置中开启声纹识别\n虚拟伙伴将只应答您的语音\n保存重启软件后生效\n(您的声纹文件位于{FILE_PATH})")

        def start_recording():
            if os.path.exists(FILE_PATH):
                result = messagebox.askyesno("确认",
                                             "声纹已存在，是否重新录制？将录制5秒钟音频\n请确保在安静的环境中录制\n点击“是”后，请说“你好，很高兴遇见你，这是我的声音”")
            else:
                result = messagebox.askyesno("确认",
                                             "是否开始录制声纹？将录制5秒钟音频\n请确保在安静的环境中录制\n点击“是”后，请说“你好，很高兴遇见你，这是我的声音”")
            if result:
                record_audio()

        def delete_voiceprint():
            if os.path.exists(FILE_PATH):
                result = messagebox.askyesno("确认", f"是否确认删除声纹文件？\n(您的声纹文件位于{FILE_PATH})")
                if result:
                    try:
                        os.remove(FILE_PATH)
                        messagebox.showinfo("完成", "声纹文件已删除")
                    except Exception as e:
                        messagebox.showerror("错误", f"删除文件时出错，错误详情：{e}")
            else:
                messagebox.showinfo("提示", "没有录制的声纹文件，无需删除")

        voiceprint_manage_w = tk.Toplevel(root)
        voiceprint_manage_w.title("声纹管理 - 枫云AI虚拟伙伴Web版")
        original_window_size4 = (315, 110)
        scaled_window_size4 = scaled_size(original_window_size4)
        voiceprint_manage_w.geometry(f"{scaled_window_size4[0]}x{scaled_window_size4[1]}")
        Button(voiceprint_manage_w, text="开始录制", command=start_recording, bg="green", fg="white").pack(pady=10)
        Button(voiceprint_manage_w, text="删除声纹", command=delete_voiceprint, bg="#FF7700", fg="white").pack(pady=10)
        voiceprint_manage_w.iconbitmap("data/image/logo.ico")

    def open_cloud_key_set():
        res = messagebox.askyesno("提示", "是否进入云端AI Key设置？\n修改完后保存重启软件生效")
        if res:
            Popen("notepad data/set/cloud_ai_key_set.json")

    def open_more_set():
        res = messagebox.askyesno("提示",
                                  "是否进入更多设置？\n需细心修改，修改失误会导致软件无法打开\n修改完后保存重启软件生效")
        if res:
            Popen("notepad data/set/more_set.json")

    def convert_text(text):
        return b64decode(text).decode('utf-8')

    setting_w = tk.Toplevel(root)
    setting_w.title("软件设置 - 枫云AI虚拟伙伴Web版")
    original_window_size2 = (1020, 635)
    scaled_window_size2 = scaled_size(original_window_size2)
    setting_w.geometry(f"{scaled_window_size2[0]}x{scaled_window_size2[1]}")
    logo_label2 = Label(setting_w, image=logo_photo)
    logo_label2.place(relx=0.012, rely=0.02)
    Label(setting_w, text="ASR与TTS", font=("楷体", 18, "bold"), fg="#587EF4").place(relx=0.06, rely=0.022)
    Label(setting_w, text="虚拟伙伴信息", font=("楷体", 18, "bold"), fg="#587EF4").place(relx=0.22, rely=0.022)
    Label(setting_w, text="网页与桌宠", font=("楷体", 18, "bold"), fg="#587EF4").place(relx=0.42, rely=0.022)
    Label(setting_w, text="LLM,VLM,知识库", font=("楷体", 18, "bold"), fg="#587EF4").place(relx=0.59, rely=0.022)
    Label(setting_w, text="其他设置", font=("楷体", 18, "bold"), fg="#587EF4").place(relx=0.82, rely=0.022)
    Label(setting_w, text='VITS-ONNX模型名:').place(relx=0.04, rely=0.096)
    vits_list = [item for item in os.listdir(vits_target_dir) if os.path.isdir(os.path.join(vits_target_dir, item))]
    vits_var = StringVar(setting_w)
    vits_var.set(vits_model_name)  # 设置默认语言
    vits_menu = ttk.Combobox(setting_w, textvariable=vits_var, values=vits_list, width=20, state="readonly",
                             justify='center', font=("楷体", 11))
    vits_menu.place(relx=0.022, rely=0.145)
    Label(setting_w, text='PaddleTTS语速:').place(relx=0.005, rely=0.189)
    rate_list = ["1", "2", "3", "4", "5", "6", "7"]
    rate_var = StringVar(setting_w)
    rate_var.set(paddle_rate)  # 设置默认语速
    rate_menu = ttk.Combobox(setting_w, textvariable=rate_var, values=rate_list, width=4, state="readonly",
                             justify='center', font=("楷体", 11))
    rate_menu.place(relx=0.05, rely=0.238)
    Label(setting_w, text='语言:').place(relx=0.145, rely=0.189)
    lang_list = ["中文", "英语", "日语", "韩语"]
    lang_var = StringVar(setting_w)
    lang_var.set(paddle_lang)  # 设置默认语言
    lang_menu = ttk.Combobox(setting_w, textvariable=lang_var, values=lang_list, width=4, state="readonly",
                             justify='center', font=("楷体", 11))
    lang_menu.place(relx=0.145, rely=0.238)
    Label(setting_w, text='edge-tts音色:').place(relx=0.05, rely=0.276)
    edge_speaker_var = StringVar(setting_w)
    edge_speaker_var.set(edge_speaker)
    edge_speaker_menu = ttk.Combobox(setting_w, textvariable=edge_speaker_var, values=edge_speaker_list,
                                     height=16, width=20, state="readonly", justify='center', font=("楷体", 11))
    edge_speaker_menu.place(relx=0.022, rely=0.325)
    Label(setting_w, text='edge-tts语速:').place(relx=0.005, rely=0.364)
    edge_rate_entry = Entry(setting_w, width=4, justify='center')
    edge_rate_entry.insert("end", edge_rate)
    edge_rate_entry.place(relx=0.05, rely=0.413)
    Label(setting_w, text='音高:').place(relx=0.145, rely=0.364)
    pitch_entry = Entry(setting_w, width=4, justify='center')
    pitch_entry.insert("end", edge_pitch)
    pitch_entry.place(relx=0.145, rely=0.413)
    Label(setting_w, text="流式语音合成开关:").place(relx=0.025, rely=0.452)
    stream_tts_var = StringVar(setting_w)
    stream_tts_var.set(stream_tts_switch)
    stream_tts_menu = ttk.Combobox(setting_w, textvariable=stream_tts_var, values=["开启", "关闭"], width=4,
                                     state="readonly", justify='center', font=("楷体", 14))
    stream_tts_menu.place(relx=0.075, rely=0.491)
    Label(setting_w, text="实时语音开关键:").place(relx=0.039, rely=0.53)
    Label(setting_w, text="Alt+").place(relx=0.069, rely=0.569)
    voice_key_entry = Entry(setting_w, width=4, justify='center')
    voice_key_entry.insert("end", voice_key)
    voice_key_entry.place(relx=0.123, rely=0.569)
    Label(setting_w, text='自定义语音唤醒词:').place(relx=0.025, rely=0.608)
    wake_word_entry = Entry(setting_w, width=12, justify='center', font=("楷体", 12))
    wake_word_entry.insert("end", wake_word)
    wake_word_entry.place(relx=0.054, rely=0.647)
    Label(setting_w, text="语音识别灵敏度:").place(relx=0.039, rely=0.686)
    asr_sensi_options = ["高", "中", "低"]
    asr_sensi_var = StringVar(setting_w)
    asr_sensi_var.set(asr_sensitivity)
    asr_sensi_menu = ttk.Combobox(setting_w, textvariable=asr_sensi_var, values=asr_sensi_options, width=2,
                                  state="readonly", justify='center', font=("楷体", 14))
    asr_sensi_menu.place(relx=0.09, rely=0.735)
    Label(setting_w, text="实时语音打断:").place(relx=0.232, rely=0.686)
    voice_break_options = ["开启", "关闭"]
    voice_break_var = StringVar(setting_w)
    voice_break_var.set(voice_break)
    voice_break_menu = ttk.Combobox(setting_w, textvariable=voice_break_var, values=voice_break_options, width=4,
                                    state="readonly", justify='center', font=("楷体", 14))
    voice_break_menu.place(relx=0.265, rely=0.735)
    Label(setting_w, text='用户名:').place(relx=0.26, rely=0.098)
    username_entry = Entry(setting_w, width=16, justify='center')
    username_entry.insert("end", username)
    username_entry.place(relx=0.22, rely=0.147)
    Label(setting_w, text='虚拟伙伴名称:').place(relx=0.232, rely=0.198)
    mate_name_entry = Entry(setting_w, width=16, justify='center')
    mate_name_entry.insert("end", mate_name)
    mate_name_entry.place(relx=0.22, rely=0.247)
    Label(setting_w, text='虚拟伙伴人设:').place(relx=0.232, rely=0.296)
    prompt_text = ScrolledText(setting_w, width=18, height=14, font=("楷体", 11))
    prompt_text.insert("end", prompt)
    prompt_text.place(relx=0.22, rely=0.345)
    Label(setting_w, text="对话网页开关:").place(relx=0.426, rely=0.098)
    web_switch_options = ["开启", "关闭"]
    web_switch_var = StringVar(setting_w)
    web_switch_var.set(chat_web_switch)
    web_switch_menu = ttk.Combobox(setting_w, textvariable=web_switch_var, values=web_switch_options, width=4,
                                   state="readonly", justify='center', font=("楷体", 14))
    web_switch_menu.place(relx=0.452, rely=0.147)
    Label(setting_w, text="对话网页端口:").place(relx=0.426, rely=0.196)
    chatweb_port_entry = Entry(setting_w, width=5, justify='center')
    chatweb_port_entry.insert("end", chatweb_port)
    chatweb_port_entry.place(relx=0.457, rely=0.245)
    Label(setting_w, text="L2D角色网页端口:").place(relx=0.42, rely=0.294)
    live2d_port_entry = Entry(setting_w, width=5, justify='center')
    live2d_port_entry.insert("end", live2d_port)
    live2d_port_entry.place(relx=0.457, rely=0.343)
    Label(setting_w, text="MMD角色网页端口:").place(relx=0.42, rely=0.392)
    mmd_port_entry = Entry(setting_w, width=5, justify='center')
    mmd_port_entry.insert("end", mmd_port)
    mmd_port_entry.place(relx=0.457, rely=0.441)
    Label(setting_w, text='VRM角色网页端口:').place(relx=0.42, rely=0.49)
    vrm_port_entry = Entry(setting_w, width=5, justify='center')
    vrm_port_entry.insert("end", vrm_port)
    vrm_port_entry.place(relx=0.457, rely=0.539)
    Label(setting_w, text="桌面宠物置顶:").place(relx=0.426, rely=0.588)
    pet_top_options = ["开启", "关闭"]
    pet_top_var = StringVar(setting_w)
    pet_top_var.set(pet_top_switch)
    pet_top_menu = ttk.Combobox(setting_w, textvariable=pet_top_var, values=pet_top_options, width=4,
                                state="readonly", justify='center', font=("楷体", 14))
    pet_top_menu.place(relx=0.452, rely=0.637)
    Label(setting_w, text="桌宠初始位置:").place(relx=0.426, rely=0.686)
    Label(setting_w, text="x:").place(relx=0.41, rely=0.735)
    pet_x_entry = Entry(setting_w, width=4, justify='center')
    pet_x_entry.insert("end", pet_x)
    pet_x_entry.place(relx=0.44, rely=0.735)
    Label(setting_w, text="y:").place(relx=0.49, rely=0.735)
    pet_y_entry = Entry(setting_w, width=4, justify='center')
    pet_y_entry.insert("end", pet_y)
    pet_y_entry.place(relx=0.52, rely=0.735)
    Label(setting_w, text="本地LLM服务器IP:").place(relx=0.6, rely=0.098)
    llm_server_ip_entry = Entry(setting_w, width=15, justify='center')
    llm_server_ip_entry.insert("end", local_llm_ip)
    llm_server_ip_entry.place(relx=0.6, rely=0.147)
    Label(setting_w, text="Ollama大语言模型:").place(relx=0.6, rely=0.196)
    ollama_model_name_entry = Entry(setting_w, width=15, justify='center')
    ollama_model_name_entry.insert("end", ollama_model_name)
    ollama_model_name_entry.place(relx=0.6, rely=0.245)
    Label(setting_w, text="Ollama多模态VLM:").place(relx=0.6, rely=0.294)
    ollama_vlm_name_entry = Entry(setting_w, width=15, justify='center')
    ollama_vlm_name_entry.insert("end", ollama_vlm_name)
    ollama_vlm_name_entry.place(relx=0.6, rely=0.343)
    Label(setting_w, text="AnythingLLM工作区:").place(relx=0.6, rely=0.392)
    allm_ws_entry = Entry(setting_w, width=15, justify='center')
    allm_ws_entry.insert("end", anything_llm_ws)
    allm_ws_entry.place(relx=0.6, rely=0.441)
    Label(setting_w, text="AnythingLLM密钥:").place(relx=0.6, rely=0.49)
    allm_key_entry = Entry(setting_w, width=22, justify='center', font=("楷体", 10))
    allm_key_entry.insert("end", anything_llm_key)
    allm_key_entry.place(relx=0.6, rely=0.539)
    Label(setting_w, text='Dify知识库IP:').place(relx=0.6, rely=0.58)
    dify_ip_entry = Entry(setting_w, width=15, justify='center')
    dify_ip_entry.insert("end", dify_ip)
    dify_ip_entry.place(relx=0.6, rely=0.629)
    Label(setting_w, text='Dify知识库密钥:').place(relx=0.6, rely=0.678)
    dify_key_entry = Entry(setting_w, width=22, justify='center', font=("楷体", 10))
    dify_key_entry.insert("end", dify_key)
    dify_key_entry.place(relx=0.6, rely=0.727)
    Label(setting_w, text="摄像头权限:").place(relx=0.61, rely=0.78)
    cam_permission_options = ["开启", "关闭"]
    cam_permission_var = StringVar(setting_w)
    cam_permission_var.set(cam_permission)
    cam_permission_menu = ttk.Combobox(setting_w, textvariable=cam_permission_var, values=cam_permission_options, width=4,
                                     state="readonly", justify='center', font=("楷体", 14))
    cam_permission_menu.place(relx=0.63, rely=0.829)
    Label(setting_w, text="默认天气城:").place(relx=0.61, rely=0.881)
    weather_city_entry = Entry(setting_w, width=8, justify='center')
    weather_city_entry.insert("end", weather_city)
    weather_city_entry.place(relx=0.62, rely=0.93)
    Label(setting_w, text="图像生成引擎:").place(relx=0.82, rely=0.098)
    draw_options = ["云端CogView-3", "云端Kolors", "云端文心Web", "本地Janus整合包", "本地SD API", "关闭AI绘画"]
    draw_var = StringVar(setting_w)
    draw_var.set(prefer_draw)
    draw_menu = ttk.Combobox(setting_w, textvariable=draw_var, values=draw_options, width=14, state="readonly",
                             justify='center')
    draw_menu.place(relx=0.8, rely=0.147)
    Label(setting_w, text="声纹识别:").place(relx=0.84, rely=0.196)
    voiceprint_sw_options = ["开启", "关闭"]
    voiceprint_sw_var = StringVar(setting_w)
    voiceprint_sw_var.set(voiceprint_switch)
    voiceprint_sw_menu = ttk.Combobox(setting_w, textvariable=voiceprint_sw_var, values=voiceprint_sw_options, width=4,
                                      state="readonly", justify='center', font=("楷体", 14))
    voiceprint_sw_menu.place(relx=0.85, rely=0.245)
    Label(setting_w, text="自定义API-base_url:").place(relx=0.003, rely=0.794)
    custom_url_entry = Entry(setting_w, width=53, justify='center', font=("楷体", 10))
    custom_url_entry.insert("end", custom_url)
    custom_url_entry.place(relx=0.2, rely=0.804)
    Label(setting_w, text="自定义API-api_key:").place(relx=0.003, rely=0.833)
    custom_key_entry = Entry(setting_w, width=53, justify='center', font=("楷体", 10))
    custom_key_entry.insert("end", custom_key)
    custom_key_entry.place(relx=0.2, rely=0.843)
    Label(setting_w, text="自定义API-LLM-model:").place(relx=0.003, rely=0.872)
    custom_model_entry = Entry(setting_w, width=53, justify='center', font=("楷体", 10))
    custom_model_entry.insert("end", custom_model)
    custom_model_entry.place(relx=0.2, rely=0.882)
    Label(setting_w, text="自定义API-VLM-model:").place(relx=0.003, rely=0.912)
    custom_vlm_entry = Entry(setting_w, width=53, justify='center', font=("楷体", 10))
    custom_vlm_entry.insert("end", custom_vlm)
    custom_vlm_entry.place(relx=0.2, rely=0.922)
    Button(setting_w, text="测试API", command=custom_api_test, bg="#3E92ED", fg="white", font=("楷体", 11)).place(
        relx=0.5, rely=0.951)
    Button(setting_w, text="测试Ollama", command=ollama_test, bg="#3E92ED", fg="white", font=("楷体", 11)).place(
        relx=0.71, rely=0.951)
    Button(setting_w, text="云端AI Key设置", command=open_cloud_key_set, bg="green", fg="white").place(
        relx=0.81, rely=0.34)
    Button(setting_w, text="   声纹管理   ", command=open_voiceprint_manage, bg="green", fg="white").place(
        relx=0.81, rely=0.42)
    Button(setting_w, text=" VITS模型管理 ", command=lambda: os.startfile("data\\model\\TTS"), bg="green",
           fg="white").place(
        relx=0.81, rely=0.5)
    Button(setting_w, text="   更多设置   ", command=open_more_set, bg="green", fg="white").place(
        relx=0.81, rely=0.58)
    Button(setting_w, text=" 开源项目官网 ",
           command=lambda: wb.open("https://swordswind.github.io/2024/07/09/mateweb/"), bg="#3E92ED", fg="white").place(relx=0.81, rely=0.66)
    Button(setting_w, text="下载本地AI引擎",
           command=lambda: wb.open("https://swordswind.github.io/2024/03/13/engine/"), bg="#3E92ED", fg="white").place(relx=0.81, rely=0.74)
    Button(setting_w, text=" 恢复默认设置 ", command=restore_set, bg="#FF7700", fg="white").place(relx=0.81, rely=0.82)
    cancel_btn = Button(setting_w, text="取消", command=setting_w.destroy)
    cancel_btn.place(relx=0.81, rely=0.912)
    save_btn = Button(setting_w, text="保存", command=save_and_close, bg="#2A6EE9", fg="white")
    save_btn.place(relx=0.91, rely=0.912)
    Label(setting_w, text=convert_text("KuacrOi9r+S7tueUsU1ld0NvLUFJIFRlYW3ojaPoqonlh7rlk4Es5byA5rqQ5YWN6LS5LOS7heS+m+S4quS6uuWoseS5kCzkuKXnpoHnlKjkuo7llYbkuJrnlKjpgJQ="), font=("楷体", 10), fg="green").place(relx=0.0, rely=0.961)
    Label(setting_w, text=convert_text("R2l0SHVi5byA5rqQ5Zyw5Z2AOmdpdGh1Yi5jb20vc3dvcmRzd2luZC9haV92aXJ0dWFsX21hdGVfd2Vi"), font=("楷体", 10), fg="green").place(relx=0.6, rely=0.0)
    setting_w.iconbitmap("data/image/logo.ico")
    setting_w.bind("<Button-3>", show_menu_set)
    setting_w.mainloop()
