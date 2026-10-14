# -*- coding: utf-8 -*-
"""生成《电视访问地址.txt》：运行后在本目录生成该文件，供电视浏览器照着输入。"""
import socket


def get_local_ips():
    """返回本机局域网 IPv4 地址，家庭常用网段(192.168/10.x)排最前。"""
    ips = []
    try:
        hostname = socket.gethostname()
        seen = set()
        for info in socket.getaddrinfo(hostname, None):
            ip = info[4][0]
            if ip in seen or not ip or ip.startswith('127.') or ':' in ip:
                continue
            seen.add(ip)
            if ip.startswith('192.168.'):
                pri = 0      # 最常用家庭网段
            elif ip.startswith('10.'):
                pri = 1
            elif ip.startswith('172.') and 16 <= int(ip.split('.')[1]) <= 31:
                pri = 2      # 可能是虚拟网卡，放后面
            else:
                pri = 3
            ips.append((pri, ip))
    except Exception:
        pass
    ips.sort()
    return [ip for _, ip in ips]


def main():
    port_live2d = 5261  # 角色页(双角色)
    port_chat = 5260    # 聊天页(打字对话)
    ips = get_local_ips()
    lines = []
    lines.append("==============================================")
    lines.append("  枫云AI虚拟伙伴 - 电视访问地址")
    lines.append("==============================================")
    lines.append("")
    lines.append("在电视的『浏览器』App 里输入下面的地址：")
    lines.append("")
    if ips:
        for i, ip in enumerate(ips):
            tag = "  ← 一般用这个" if i == 0 and len(ips) > 1 else ""
            lines.append(f"  两个角色页面:  http://{ip}:{port_live2d}{tag}")
            lines.append(f"  打字聊天页面:  http://{ip}:{port_chat}")
            lines.append("")
        if len(ips) > 1:
            lines.append("提示：通常选 192.168 或 10 开头的那一行")
    else:
        lines.append("  (未检测到本机IP，请在电脑命令提示符输入 ipconfig 查看)")
        lines.append("")
    lines.append("提示：电脑和电视必须连接『同一个 WiFi/路由器』")
    lines.append("==============================================")
    content = "\n".join(lines)
    with open("电视访问地址.txt", "w", encoding="utf-8-sig") as f:
        f.write(content)
    print("[电视适配] 已生成《电视访问地址.txt》到本目录，请在电视浏览器输入其中地址。")


if __name__ == "__main__":
    main()
