import time
import base64


def decrypt_dnum(d_num_encoded: str) -> str | None:
    if not d_num_encoded:
        return None

    try:
        decoded_bytes = base64.b64decode(d_num_encoded)
        decoded_str = decoded_bytes.decode("utf-8")

        if len(decoded_str) < 27:
            return None

        part1 = decoded_str[6:12]
        part2 = decoded_str[21:28]

        return part1 + part2

    except Exception:
        return None


def check_decrypt_dnum(d_num_encoded: str) -> int:
    """
    检查 dnum 是否过期
    空值或者错误返回 -1
    如果过期返回 0
    如果未过期返回时间戳
    """
    if not d_num_encoded:
        return -1
    ts = decrypt_dnum(d_num_encoded)
    if not ts:
        return -1
    try:
        ts_int = int(ts)
        if ts_int / 1000 < time.time():
            return 0
    except Exception:
        return -1
    return ts_int
