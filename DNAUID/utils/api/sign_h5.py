from __future__ import annotations

import time
import secrets
from typing import Any

from .sign_utils import rand_str, xor_encode, rsa_encrypt, sign_shuffled


def _swap(text: str, first: int, second: int) -> str:
    if first < 0 or second < 0 or first >= len(text) or second >= len(text):
        return text
    chars = list(text)
    chars[first], chars[second] = chars[second], chars[first]
    return "".join(chars)


def _generate_h5_raw_sa(timestamp_ms: int | None = None) -> str:
    if timestamp_ms is None:
        timestamp_ms = int(time.time() * 1000)

    timestamp = str(timestamp_ms)
    chars = [secrets.choice("0123456789") for _ in range(30)]
    timestamp_positions = (
        *range(3, 8),
        *range(18, 24),
        *range(27, 29),
    )
    for timestamp_index, position in enumerate(timestamp_positions):
        chars[position] = timestamp[timestamp_index]
    return "".join(chars)


def _build_h5_sa_header(raw_sa: str) -> str:
    sa = raw_sa
    for first, second in ((5, 19), (11, 22), (17, 28)):
        sa = _swap(sa, first, second)
    return sa


def generate_headers_h5(
    headers: dict[str, str],
    payload: dict[str, Any],
    rsa_public_key: str,
) -> tuple[dict[str, str], dict[str, Any]]:
    random_key = rand_str(16)
    raw_sa = _generate_h5_raw_sa()
    sa = _build_h5_sa_header(raw_sa)

    sign_params = {key: str(value) for key, value in payload.items()}
    token = headers.get("token")
    if token is not None:
        sign_params["token"] = token
    sign_params["sa"] = raw_sa

    encoded_signature = xor_encode(
        sign_shuffled(sign_params, random_key),
        random_key,
    )
    tn = f"{rsa_encrypt(random_key, rsa_public_key)},{encoded_signature}"
    headers.update({"sa": sa, "tn": tn})
    return headers, payload
