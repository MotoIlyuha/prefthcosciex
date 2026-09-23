"""API errors: a stable machine code plus a Russian message the client can show."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException


class ApiError(HTTPException):
    def __init__(self, status: int, code: str, message: str, **extra: Any) -> None:
        super().__init__(status_code=status, detail={"code": code, "message": message, **extra})
        self.code = code


def not_found(what: str = "объект") -> ApiError:
    return ApiError(404, "not_found", f"Не найдено: {what}")


def forbidden(message: str = "Недостаточно прав") -> ApiError:
    return ApiError(403, "forbidden", message)


def conflict(code: str, message: str, **extra: Any) -> ApiError:
    return ApiError(409, code, message, **extra)


def insufficient_funds(price: int, balance: int) -> ApiError:
    return ApiError(
        402, "insufficient_funds", f"Нужно {price} 🪙, на счёте {balance} 🪙", price=price
    )
