import base64
import hashlib
import secrets
import time
import uuid
from typing import Any, Dict


def rsa_encrypt(text: str, public_key_b64: str) -> str:
    try:
        from Crypto.Cipher import PKCS1_v1_5
        from Crypto.PublicKey import RSA
    except Exception:
        raise RuntimeError(
            "[DNA] 缺少依赖: 需要 pycryptodome 执行 RSA 加密。请安装: uv add pycryptodome"
        )

    try:
        # 将一行 base64 公钥转 PEM（PKCS#8 公钥）
        lines = [
            public_key_b64[i : i + 64]
            for i in range(0, len(public_key_b64), 64)
        ]
        pem = (
            "-----BEGIN PUBLIC KEY-----\n"
            + "\n".join(lines)
            + "\n-----END PUBLIC KEY-----"
        )
        rsa_key = RSA.import_key(pem)
        cipher = PKCS1_v1_5.new(rsa_key)
        enc_bytes = cipher.encrypt(text.encode("utf-8"))
        return base64.b64encode(enc_bytes).decode("utf-8")
    except Exception as e:
        raise RuntimeError(f"[DNA] RSA 加密失败: {e}")


def get_timestamp() -> int:
    return int(time.time() * 1000)


def get_dev_code() -> str:
    return str(uuid.uuid4()).upper()


def rand_str(length: int = 16) -> str:
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(secrets.choice(chars) for _ in range(length))


def md5_upper(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest().upper()


def signature_hash(text: str) -> str:
    def swap_positions(text: str, positions: list[int]) -> str:
        chars = list(text)
        for i in range(1, len(positions), 2):
            p1 = positions[i - 1]
            p2 = positions[i]
            if 0 <= p1 < len(chars) and 0 <= p2 < len(chars):
                chars[p1], chars[p2] = chars[p2], chars[p1]
        return "".join(chars)

    return swap_positions(md5_upper(text), [1, 13, 5, 17, 7, 23])


def sign_fI(data: Dict[str, Any], secret: str) -> str:
    pairs = []
    for k in sorted(data.keys()):
        v = data[k]
        if v is not None and v != "":
            pairs.append(f"{k}={v}")
    qs = "&".join(pairs)
    return signature_hash(f"{qs}&{secret}")


def xor_encode(text: str, key: str) -> str:
    tb = list(text.encode("utf-8"))
    kb = list(key.encode("utf-8"))
    out = []
    for i, b in enumerate(tb):
        e = (b & 255) + (kb[i % len(kb)] & 255)
        out.append(f"@{e}")
    return "".join(out)


def build_signature(data: Dict[str, Any]) -> Dict[str, Any]:
    ts = int(time.time() * 1000)
    sign_data = {**data, "timestamp": ts, "token": None}
    sec = rand_str(16)
    sig = sign_fI(sign_data, sec)
    enc = xor_encode(sig, sec)
    return {"s": enc, "t": ts, "k": sec}
