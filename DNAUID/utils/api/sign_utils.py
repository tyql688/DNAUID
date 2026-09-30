import base64
import random
import hashlib
from typing import Any

from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA


def rand_str(length: int) -> str:
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(random.choice(chars) for _ in range(length))


def rand_digit_str(length: int) -> str:
    """1.3.0 版本的随机串：仅数字，字符集与 Java 端 p63.b() 一致"""
    chars = "01234567890123456789012345678901234567890123456789010123456789"
    return "".join(random.choice(chars) for _ in range(length))


def rsa_encrypt(data: str, public_key_base64: str) -> str:
    """RSA/ECB/PKCS1Padding 加密，支持分段（每段最多 117 字节）"""
    try:
        key = RSA.importKey(base64.b64decode(public_key_base64))
        cipher = PKCS1_v1_5.new(key)
        raw = data.encode("utf-8")
        max_block = 117
        result = b""
        offset = 0
        while offset < len(raw):
            block = raw[offset : offset + max_block]
            result += cipher.encrypt(block)
            offset += max_block
        return base64.b64encode(result).decode("utf-8")
    except Exception as e:
        raise RuntimeError(f"RSA Encrypt Error: {e}") from e


def xor_encode(text: str, key: str) -> str:
    """自定义 XOR 编码（字节值相加，非异或）"""
    tb = text.encode("utf-8")
    kb = key.encode("utf-8")
    return "".join(f"@{(tb[i] & 255) + (kb[i % len(kb)] & 255)}" for i in range(len(tb)))


def shuffle_md5(md5_hex: str) -> str:
    """MD5 结果位置混淆: 1↔13, 5↔17, 7↔23"""
    if len(md5_hex) <= 23:
        return md5_hex
    chars = list(md5_hex)
    for i, j in [(1, 13), (5, 17), (7, 23)]:
        chars[i], chars[j] = chars[j], chars[i]
    return "".join(chars)


def sign_shuffled(params: dict[str, Any], app_key: str) -> str:
    """按 key 排序拼接参数 → MD5 → shuffle"""
    pairs = [f"{k}={params[k]}" for k in sorted(params) if params[k] is not None and str(params[k]) != ""]
    pairs.append(app_key)
    md5_hash = hashlib.md5("&".join(pairs).encode("utf-8")).hexdigest().upper()
    return shuffle_md5(md5_hash)
