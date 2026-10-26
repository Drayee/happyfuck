#!/usr/bin/env python3
"""Reproduce the Legym (com.ledreamer.zz) request/response envelope offline.

Envelope (from SecurityRequestBodyConverter / SecurityResponseBodyConverter):
    request : {"t": <ms timestamp>, "pyd": base64(AES-128-ECB-PKCS5(json, key))}
    key     : NativeLib.getDyKey(str(t))  ->  "<n><getNetSalt()>"  where
              n = abs(atoi(t[2:5]) - atoi(t[4:8])) << (t[-1] - '0')
    response: same shape, key = getDyKey(str(t))

Verified against libsecurity.so (arm64-v8a) with Unicorn emulation; see
tools/emu_key.py for the key-derivation oracle.
"""
import base64
import sys

NET_SALT = '402881ea7c39c5d5017c39d143a8062b'   # getNetSalt() @0x2d04 (.rodata 0xaa60)


def get_dy_key(ts: str) -> str:
    """Mirror of getDynamicKey @0x2b90 + getNetSalt @0x2d04."""
    if len(ts) < 8:
        raise ValueError('timestamp must be a 13-digit ms string')
    a = int(ts[2:5] or '0')          # strncpy(buf, ts+2, 3)
    b = int(ts[4:8] or '0')          # strncpy(buf, ts+4, 4)
    shift = int(ts[-1])              # last digit
    diff = abs(a - b)
    n = (diff << shift) & 0xFFFFFFFF
    return '%d%s' % (n, NET_SALT)


def aes_ecb_pkcs5_encrypt(plain: str, key: str) -> str:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad
    k = key.encode('utf-8')[:16]
    k = k + b'\x00' * (16 - len(k)) if len(k) < 16 else k
    c = AES.new(k, AES.MODE_ECB)
    return base64.b64encode(c.encrypt(pad(plain.encode('utf-8'), 16))).decode()


def aes_ecb_pkcs5_decrypt(b64: str, key: str) -> str:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
    k = key.encode('utf-8')[:16]
    k = k + b'\x00' * (16 - len(k)) if len(k) < 16 else k
    c = AES.new(k, AES.MODE_ECB)
    return unpad(c.decrypt(base64.b64decode(b64)), 16).decode('utf-8', 'replace')


def wrap_request(json_body: str, ts_ms: int) -> dict:
    key = get_dy_key(str(ts_ms))
    return {'t': ts_ms, 'pyd': aes_ecb_pkcs5_encrypt(json_body, key)}


def unwrap_response(payload: dict) -> str:
    key = get_dy_key(str(payload['t']))
    return aes_ecb_pkcs5_decrypt(payload['pyd'], key)
