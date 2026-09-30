import time
from typing import Any

from .sign_utils import rand_str, xor_encode, rsa_encrypt, sign_shuffled, rand_digit_str


def _swap(text: str, i: int, j: int) -> str:
    if i < 0 or j < 0 or i >= len(text) or j >= len(text):
        return text
    chars = list(text)
    chars[i], chars[j] = chars[j], chars[i]
    return "".join(chars)


def _build_sa_header(raw_sa: str, timestamp: int | None = None) -> str:
    """
    1.3.0 sa header 构建 (libalgorithmlib.so cppCoreAlgorithm 的 Python 等价):
    1. 对 raw_sa(30 位纯数字随机串) 做 4 次位置交换: (1,17)(9,20)(15,16)(22,27)
    2. 在位置 8、16 各插入 5 位时间戳，在位置 22 插入 3 位时间戳
    最终长度 30 + 5 + 5 + 3 = 43
    """
    if timestamp is None:
        timestamp = int(time.time() * 1000)

    sa = raw_sa
    for i, j in [(1, 17), (9, 20), (15, 16), (22, 27)]:
        sa = _swap(sa, i, j)

    ts = str(timestamp)
    if len(sa) != 30 or len(ts) < 13:
        return sa

    time_idx = 0
    out = []
    for i in range(len(sa)):
        if i == 8 or i == 16:
            out.append(ts[time_idx : time_idx + 5])
            time_idx += 5
        elif i == 22:
            out.append(ts[time_idx : time_idx + 3])
            time_idx += 3
        out.append(sa[i])

    return "".join(out)


def generate_headers_130(
    headers: dict[str, str],
    payload: dict[str, Any],
    rsa_public_key: str,
) -> tuple[dict[str, str], dict[str, Any]]:
    """为 1.3.0 版本生成签名 headers (tn + sa，无 rk)"""
    rk: str = rand_str(16)
    raw_sa = rand_digit_str(30)
    sa = _build_sa_header(raw_sa)

    sign_params = {k: str(v) for k, v in payload.items()}
    if headers.get("token"):
        sign_params["token"] = headers["token"]
    sign_params["sa"] = raw_sa

    sign_encoded = xor_encode(sign_shuffled(sign_params, rk), rk)
    tn = f"{rsa_encrypt(rk, rsa_public_key)},{sign_encoded}"

    headers.update({"sa": sa, "tn": tn})
    return headers, payload
