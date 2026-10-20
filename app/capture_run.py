#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键抓包校准：frida 抓真机 upload 明文，自动存 data/upload_sample.json。

用法（按顺序）：
  1. 手机开 USB 调试，连电脑
  2. 手机运行 frida-server（root）
  3. 电脑运行本脚本：
       python capture_run.py
  4. 脚本会自动启动乐健 App。在 App 里自由跑 200~400 米（约 1~2 分钟），
     到点后结束并让它正常上传。
  5. 看到 [saved] 即校准完成，回到 HappyFuck 界面直接刷。
"""
import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'data', 'upload_sample.json')
JS = os.path.join(HERE, 'capture_upload.js')

try:
    import frida
except ImportError:
    sys.exit('需要 frida: python -m pip install frida')

got = threading.Event()
plain_box = {}


def on_message(msg, data):
    if msg.get('type') == 'send':
        p = msg.get('payload') or {}
        tag = p.get('tag')
        if tag == 'KERNEL-PLAIN':
            plain_box['plain'] = p.get('text')
            print('\n[sample] 抓到上传明文 (%d 字节)' % len(p.get('text') or ''))
            got.set()
        elif tag == 'KERNEL-KEY':
            plain_box['key'] = p.get('text')
            print('[key] kernel 密钥样本:', (p.get('text') or '')[:24])
        else:
            print('[%s] %s' % (tag, str(p.get('text'))[:150]))
    elif msg.get('type') == 'error':
        print('[js-error]', msg.get('description'))


def main():
    if os.path.exists(OUT):
        print('[!] 已存在 %s' % OUT)
        print('    重新抓会覆盖。继续? (y/N)')
        if input().strip().lower() != 'y':
            return

    dev = frida.get_usb_device(timeout=8)
    print('[dev]', dev.name)
    session = dev.spawn(['com.ledreamer.zz'])
    pid = session
    script_dev = dev.attach(pid)
    with open(JS, encoding='utf-8') as f:
        code = f.read()
    # 把 dump() 改造成 send 到 python
    code = code.replace(
        "function dump(tag, obj) {",
        "function dump(tag, obj) {\n"
        "    try { if (typeof obj==='string' && (tag==='KERNEL-PLAIN'||tag==='KERNEL-KEY')) { send({tag:tag,text:obj}); return; } } catch(e){}")
    script = script_dev.create_script(code)
    script.on('message', on_message)
    script.load()
    dev.resume(pid)
    print('[run] App 已启动。请自由跑 200~400 米并结束上传…')
    print('    （等最长 6 分钟）')

    if not got.wait(360):
        print('[x] 超时没抓到。确认这次跑步真的点了"结束并上传"。')
        return

    text = plain_box.get('plain')
    try:
        obj = json.loads(text)
    except Exception as e:
        print('[x] 明文解析失败:', e)
        with open(OUT + '.raw.txt', 'w', encoding='utf-8') as f:
            f.write(text)
        print('    原始文本存到', OUT + '.raw.txt')
        return

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    print('[saved]', OUT)
    print('  字段数:', len(obj))
    print('  routineLine:', len(obj.get('routineLine') or []), '点')
    print('  signDigital 长度:', len(str(obj.get('signDigital') or '')))
    print('  现在回 HappyFuck 界面，上传即可用真实结构。')


if __name__ == '__main__':
    main()
