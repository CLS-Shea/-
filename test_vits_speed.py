"""实测 VITS 合成不同长度文本的耗时，评估首响延迟瓶颈"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import sherpa_onnx
import numpy as np

# 直接用 tts.py 的配置逻辑加载 VITS
from tts import vits_tts_config
vits_tts = sherpa_onnx.OfflineTts(vits_tts_config)
print("VITS 模型加载完成，开始测速\n")

cases = [
    "你好呀",
    "今天天气怎么样呀？",
    "好的，我这就帮您查一下今天的天气情况，请稍等。",
    "明天会下雨吗？如果下雨的话，出门记得带伞哦。好的，我这就帮您查一下今天的天气情况，请稍等。",
]
for text in cases:
    t0 = time.time()
    audio = vits_tts.generate(text, sid=0, speed=1.0)
    dt = time.time() - t0
    dur = len(audio.samples) / audio.sample_rate
    print(f"文本({len(text)}字): 合成耗时 {dt:.2f}s | 音频时长 {dur:.2f}s | 实时率 {dur/dt:.2f}x")
