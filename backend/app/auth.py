"""
Роли и доступ (п. 3.1, 4.4 ТЗ).

guest  — без входа: каталог, подбор и демонстрационные расчёты, без сохранения;
user   — проекты: создание, редактирование, копирование, удаление, сценарии;
admin  — всё, что user, плюс управление каталогом и нормативами.

Пароли хранятся как PBKDF2-SHA256 с солью. Токен — подписанная HMAC строка с
сроком действия (без внешних зависимостей).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from app.config import settings

ITERATIONS = 120_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        ITERATIONS, base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, digest = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt),
                                   int(iters))
        return hmac.compare_digest(calc, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_token(username: str, role: str) -> str:
    payload = {"sub": username, "role": role,
               "exp": int(time.time()) + settings.token_ttl_hours * 3600}
    body = _b64(json.dumps(payload).encode())
    sig = _b64(hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_token(token: str | None) -> dict | None:
    if not token:
        return None
    try:
        body, sig = token.split(".")
        expected = _b64(hmac.new(settings.secret_key.encode(), body.encode(),
                                 hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_unb64(body))
        if payload["exp"] < time.time():
            return None
        return payload
    except (ValueError, KeyError, json.JSONDecodeError):
        return None
