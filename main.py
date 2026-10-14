from main_sub import common_chat, run_ase_rp, run_ase_agent
from live2d import run_live2d
from mmd import run_mmd
from vrm import *
from sys_init import build_live2d_js
import wake  # 唤醒互动窗口（语音唤醒 / 点击角色唤醒共用）


def refresh_preference():  # 刷新用户偏好
    while True:
        try:
            new_preference = {"语音识别模式": asr_menu.get(), "对话语言模型": llm_menu.get(),
                              "语音合成引擎": tts_menu.get(), "图像识别引擎": img_menu.get(),
                              "主动感知对话": ase_menu.get(), "运行模式切换": mode_menu.get()}
            with open('data/db/preference.json', 'w', encoding='utf-8') as f:
                json.dump(new_preference, f, ensure_ascii=False, indent=4)
            with open(f'data/db/history.db', 'w', encoding='utf-8') as f:
                f.write(output_box.get(1.0, "end").strip() + "\n")
        except:
            print("用户偏好保存错误")
        time.sleep(0.1)


def text_chat(event=None):  # 打字发送
    def text_chat_th():
        stop_tts()
        msg = input_box.get("1.0", "end").strip()
        if msg == "":
            messagebox.showinfo("提示", "请输入内容后再发送")
            return
        input_box.delete("1.0", "end")
        common_chat(msg)

    Thread(target=text_chat_th).start()


# ==================== 角色名唤醒：喊名字 / 点角色 才进入语音交互 ====================
# 唤醒模式：平时只"听名字"，听到任一角色名(南小橙/小橙/程小鹭/小鹭)或点击屏幕上的角色才进入互动，
# 喊谁的名字(点谁)就切换成谁(人设/音色/动嘴角色)；唤醒后 WAKE_SESSION_SECONDS 秒内没有说话，
# 就自动回到"待唤醒"状态，不再录音回应，避免把无关的话都当成交谈内容。
# 窗口状态放在 wake.py，与 live2d.py 的"点击角色唤醒"共用。
WAKE_SESSION_SECONDS = wake.WAKE_SESSION_SECONDS


def wake_window_active():  # 当前是否处于唤醒后的互动窗口中
    return wake.wake_window_active()


def extend_wake_window():  # 开始/续期互动窗口
    wake.extend_wake_window()


def handle_voice_text(say_text, allow_interrupt=False):  # 处理一次语音识别结果，返回是否触发了对话
    import llm as _llm
    if reception.enabled() and reception.intro_playing():
        # 固定讲解期间不接受访客语音打断；工作人员可使用停止播放快捷键。
        return False
    mode = asr_menu.get()
    if mode == "实时语音识别":
        if allow_interrupt:
            stop_tts()
        common_chat(say_text)
        return True
    if mode == "角色名唤醒":
        if reception.enabled():
            pending = reception.pending_role()
            normalized = _llm.normalize_role_names(say_text)
            if pending:
                if any(word in normalized for word in ("是", "好的", "确认", "切换", "可以")):
                    target = reception.confirm_role_switch(True)
                    if target:
                        roles.switch_role(target)
                        notice(f"已切换到「{target}」")
                        extend_wake_window()
                        return True
                if any(word in normalized for word in ("不", "否", "取消", "不用")):
                    reception.confirm_role_switch(False)
                    notice("已取消角色切换")
                    extend_wake_window()
                    return True
                return False
            target = _llm.role_name_in_message(normalized)
            current = roles.current_role_name()
            if target and target != current:
                reception.request_role_switch(target)
                extend_wake_window()
                notice(f"检测到「{target}」，请回答“确认”或“取消”")
                Thread(target=get_tts_play, args=(f"要切换到{target}吗？请回答确认或取消",), daemon=True).start()
                return True
        woke_name = _llm.detect_wake(say_text)  # 喊到角色名 → 切换角色并唤醒
        if woke_name:
            extend_wake_window()
            try:
                notice(f"已唤醒「{woke_name}」，{WAKE_SESSION_SECONDS}秒内可继续对话")
            except Exception:
                pass
            content = _llm.strip_wake_words(say_text)  # 去掉名字，取出真正要说的话
            if len(content) > 1:
                if allow_interrupt:
                    stop_tts()
                common_chat(content)
            else:
                # 只喊了名字：回一句表示已经听到(同时这也是"已唤醒"的语音反馈)
                Thread(target=get_tts_play, args=(f"我在呢，{username}～",)).start()
            return True
        if wake_window_active():  # 唤醒后的互动窗口内 → 正常对话，并续期窗口(按"没有说话的时长"计)
            extend_wake_window()
            if allow_interrupt:
                stop_tts()
            common_chat(say_text)
            return True
        return False  # 未唤醒且不在窗口内 → 忽略，不回应
    if mode == "自定义唤醒词":
        if wake_word and wake_word in say_text:
            if len(say_text) > 2:
                say_text = say_text.replace(wake_word + "，", "").replace(wake_word, "")
            if allow_interrupt:
                stop_tts()
            common_chat(say_text)
            return True
    return False


def sense_voice_th():  # 语音识别(普通模式：说完再回应)
    from asr import recognize_audio, record_audio
    asr_error_reported = False
    while True:
        try:
            if asr_menu.get() == "关闭语音识别":
                time.sleep(0.3)
                continue
            # 它说话期间由 asr 内部丢弃麦克风数据(防自录)，这里照常调用以便持续清空录音缓冲
            say_text = recognize_audio(record_audio())
            if len(say_text) > 1:
                handle_voice_text(say_text, allow_interrupt=False)
            asr_error_reported = False
        except Exception as e:
            if not asr_error_reported:
                print(f"[ASR错误] {e}")
                try: notice(f"语音识别异常: {str(e)[:40]}")
                except: pass
                asr_error_reported = True
            time.sleep(1)


def sense_voice_th_break():  # 语音识别(实时语音打断模式)
    from asr import recognize_audio, record_audio
    asr_error_reported = False
    while True:
        try:
            if asr_menu.get() == "关闭语音识别":
                time.sleep(0.3)
                continue
            say_text = recognize_audio(record_audio())
            if len(say_text) > 1:
                handle_voice_text(say_text, allow_interrupt=True)
            asr_error_reported = False
        except Exception as e:
            if not asr_error_reported:
                print(f"[ASR错误] {e}")
                try: notice(f"语音识别异常: {str(e)[:40]}")
                except: pass
                asr_error_reported = True
            time.sleep(1)


# open_source_project_address:https://github.com/swordswind/ai_virtual_mate_web
def switch_voice(event=None):  # 切换语音模式(快捷键开/关语音交互)
    if asr_menu.get() == "关闭语音识别":
        voice_var.set("角色名唤醒")
    else:
        voice_var.set("关闭语音识别")


# ==================== 大屏模式检测 ====================
# MATEWEB_KIOSK=1     → 网页全屏模式（自动打开浏览器全屏访问聊天页，跨设备通用）
# MATEWEB_FULLSCREEN=1 → 桌面全屏模式（tkinter 主窗口全屏，Windows 大屏直接跑）
_kiosk_mode = os.environ.get("MATEWEB_KIOSK", "0") == "1"
_fullscreen_mode = os.environ.get("MATEWEB_FULLSCREEN", "0") == "1"
if _kiosk_mode:
    print("[大屏] 已启用网页全屏模式")
if _fullscreen_mode:
    print("[大屏] 已启用桌面全屏模式")

if chat_web_switch == "开启" or _kiosk_mode:
    Thread(target=run_chatweb).start()
if reception.enabled():
    roles.switch_role(reception.CONFIG["default_role"])
if voice_break == "开启" or reception.enabled():
    Thread(target=sense_voice_th_break).start()
else:
    Thread(target=sense_voice_th).start()
Thread(target=run_live2d).start()
build_live2d_js()  # 大屏双角色：启动时生成双角色 live2d.js（左=南小橙，右=程小鹭）
if not reception.enabled():
    Thread(target=run_mmd).start()
    Thread(target=run_vrm).start()
Thread(target=refresh_preference).start()
if not reception.enabled():
    Thread(target=run_ase_rp).start()
    Thread(target=run_ase_agent).start()
if reception.enabled():
    Thread(target=reception_watchdog, daemon=True).start()
input_box.bind('<Return>', text_chat)
kb.add_hotkey('alt+g', stop_tts)
try:
    kb.add_hotkey(f'alt+{voice_key}', switch_voice)
except:
    print("语音模式切换按键设置错误")
wydh_icon = Image.open("data/image/ui/wydh.png")
wydh_icon = wydh_icon.resize((int(100 * scaling_factor), int(23 * scaling_factor)), Image.Resampling.LANCZOS)
wydh_icon = ImageTk.PhotoImage(wydh_icon)
Button(root, image=wydh_icon, command=open_chatweb, borderwidth=0, highlightthickness=0).place(relx=0.18, rely=0.02)
vrmjs_icon = Image.open("data/image/ui/vrmjs.png")
vrmjs_icon = vrmjs_icon.resize((int(100 * scaling_factor), int(23 * scaling_factor)), Image.Resampling.LANCZOS)
vrmjs_icon = ImageTk.PhotoImage(vrmjs_icon)
Button(root, image=vrmjs_icon, command=lambda: wb.open(f"http://127.0.0.1:{vrm_port}"), borderwidth=0,
       highlightthickness=0).place(relx=0.27, rely=0.02)
mmdjs_icon = Image.open("data/image/ui/mmdjs.png")
mmdjs_icon = mmdjs_icon.resize((int(100 * scaling_factor), int(23 * scaling_factor)), Image.Resampling.LANCZOS)
mmdjs_icon = ImageTk.PhotoImage(mmdjs_icon)
Button(root, image=mmdjs_icon, command=lambda: wb.open(f"http://127.0.0.1:{mmd_port}"), borderwidth=0,
       highlightthickness=0).place(relx=0.36, rely=0.02)
mmddz_icon = Image.open("data/image/ui/mmddz.png")
mmddz_icon = mmddz_icon.resize((int(100 * scaling_factor), int(23 * scaling_factor)), Image.Resampling.LANCZOS)
mmddz_icon = ImageTk.PhotoImage(mmddz_icon)
Button(root, image=mmddz_icon, command=open_vmd_music, borderwidth=0, highlightthickness=0).place(relx=0.45, rely=0.02)
live2djs_icon = Image.open("data/image/ui/live2djs.png")
live2djs_icon = live2djs_icon.resize((int(100 * scaling_factor), int(23 * scaling_factor)), Image.Resampling.LANCZOS)
live2djs_icon = ImageTk.PhotoImage(live2djs_icon)
Button(root, image=live2djs_icon, command=lambda: wb.open(f"http://127.0.0.1:{live2d_port}"), borderwidth=0,
       highlightthickness=0).place(relx=0.54, rely=0.02)
l2dzc_icon = Image.open("data/image/ui/l2dzc.png")
l2dzc_icon = l2dzc_icon.resize((int(100 * scaling_factor), int(23 * scaling_factor)), Image.Resampling.LANCZOS)
l2dzc_icon = ImageTk.PhotoImage(l2dzc_icon)
Button(root, image=l2dzc_icon, command=open_pet, borderwidth=0, highlightthickness=0).place(relx=0.63, rely=0.02)
zygl_icon = Image.open("data/image/ui/zygl.png")
zygl_icon = zygl_icon.resize((int(100 * scaling_factor), int(23 * scaling_factor)), Image.Resampling.LANCZOS)
zygl_icon = ImageTk.PhotoImage(zygl_icon)
Button(root, image=zygl_icon, command=open_change_w, borderwidth=0, highlightthickness=0).place(relx=0.72, rely=0.02)
rjsz_icon = Image.open("data/image/ui/rjsz.png")
rjsz_icon = rjsz_icon.resize((int(100 * scaling_factor), int(23 * scaling_factor)), Image.Resampling.LANCZOS)
rjsz_icon = ImageTk.PhotoImage(rjsz_icon)
Button(root, image=rjsz_icon, command=open_setting_w, borderwidth=0, highlightthickness=0).place(relx=0.81, rely=0.02)
tzbf_icon = Image.open("data/image/ui/tzbf.png")
tzbf_icon = tzbf_icon.resize((int(100 * scaling_factor), int(23 * scaling_factor)), Image.Resampling.LANCZOS)
tzbf_icon = ImageTk.PhotoImage(tzbf_icon)
Button(root, image=tzbf_icon, command=stop_tts, borderwidth=0, highlightthickness=0).place(relx=0.9, rely=0.02)
upphoto_icon = Image.open("data/image/ui/upphoto.png")
upphoto_icon = upphoto_icon.resize((int(25 * scaling_factor), int(25 * scaling_factor)), Image.Resampling.LANCZOS)
upphoto_icon = ImageTk.PhotoImage(upphoto_icon)
Button(root, image=upphoto_icon, command=up_photo, borderwidth=0, highlightthickness=0).place(relx=0.97, rely=0.825)
export_icon = Image.open("data/image/ui/export.png")
export_icon = export_icon.resize((int(25 * scaling_factor), int(25 * scaling_factor)), Image.Resampling.LANCZOS)
export_icon = ImageTk.PhotoImage(export_icon)
Button(root, image=export_icon, command=export_chat, borderwidth=0, highlightthickness=0).place(relx=0.97, rely=0.865)
add_icon = Image.open("data/image/ui/add.png")
add_icon = add_icon.resize((int(25 * scaling_factor), int(25 * scaling_factor)), Image.Resampling.LANCZOS)
add_icon = ImageTk.PhotoImage(add_icon)
Button(root, image=add_icon, command=clear_chat, borderwidth=0, highlightthickness=0).place(relx=0.97, rely=0.905)
send_icon = Image.open("data/image/ui/send.png")
send_icon = send_icon.resize((int(25 * scaling_factor), int(25 * scaling_factor)), Image.Resampling.LANCZOS)
send_icon = ImageTk.PhotoImage(send_icon)
Button(root, image=send_icon, command=text_chat, borderwidth=0, highlightthickness=0).place(relx=0.97, rely=0.945)
Button(root, text="📱手机网页访问", command=open_web_tips, borderwidth=0, highlightthickness=0).place(relx=0.02,
                                                                                                     rely=0.13)
# ==================== 大屏模式自动处理 ====================
if _fullscreen_mode:
    try:
        root.attributes("-fullscreen", True)  # 桌面窗口全屏
        print("[大屏] 桌面窗口已切换为全屏")
    except Exception as e:
        print(f"[大屏] 全屏设置失败: {e}")
elif _kiosk_mode:
    def _open_kiosk_browser():  # 等待 web 服务就绪后自动打开浏览器全屏访问聊天页
        time.sleep(4)
        try:
            import sys as _sys
            import subprocess as _sp
            _sp.Popen([_sys.executable, "launch_kiosk.py", f"http://127.0.0.1:{chatweb_port}"])
        except Exception as e:
            print(f"[大屏] 自动打开浏览器失败: {e}")
    Thread(target=_open_kiosk_browser, daemon=True).start()

root.protocol("WM_DELETE_WINDOW", on_closing)
root.mainloop()
os.kill(os.getpid(), 15)
