"""Verify the Telegram user opening the Mini App."""
import hmac
import json
import time
from urllib.parse import parse_qsl

MAX_AUTH_AGE = 24 * 60 * 60


def telegram_user_id(init_data: str, bot_token: str) -> int | None:
    try:
        pairs = parse_qsl(init_data, strict_parsing=True, max_num_fields=30)
        fields = dict(pairs)
        if len(fields) != len(pairs):
            return None
        signature = fields.pop("hash").encode()
        check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
        secret = hmac.digest(b"WebAppData", bot_token.encode(), "sha256")
        expected = hmac.digest(secret, check_string.encode(), "sha256").hex().encode()
        if not hmac.compare_digest(expected, signature):
            return None
        issued_at = int(fields["auth_date"])
        now = time.time()
        if not now - MAX_AUTH_AGE <= issued_at <= now + 60:
            return None
        user = json.loads(fields["user"])
    except (KeyError, ValueError):
        return None

    user_id = user.get("id") if isinstance(user, dict) else None
    if type(user_id) is int and 0 < user_id < 2**52:
        return user_id
    return None
