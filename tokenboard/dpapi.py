"""Windows DPAPI：把 API Key 用当前 Windows 账户加密后再存进数据库。

为什么不能明文存：
- TokenBoard 的库在 %LOCALAPPDATA%，**同机任何进程都能读**。
- DPAPI（CryptProtectData）用当前登录账户的凭据做密钥，
  别的账户、别的程序即使拿到密文也解不开。
- 再叠一层 entropy（应用自定义字节串）：同一个账户下的别的程序
  拿着这段密文也解不开——entropy 不是从系统密钥里取的，
  只有知道这段字节串的程序才能还原。

非 Windows 平台退化成 base64 明文（带标记前缀），功能不中断，
但安全性下降——本项目本来就只跑 Windows。
"""
from __future__ import annotations

import base64
import ctypes
import os
import sys
from ctypes import wintypes

# 应用级 entropy：换应用/换版本就解不开旧密文，密文泄露也难复用
_ENTROPY = b"TokenBoard::opencode::v1"

CRYPTPROTECT_UI_FORBIDDEN = 0x01
CRYPTPROTECT_LOCAL_MACHINE = 0x04

_PLAIN_PREFIX = "plain:"


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> tuple[_DATA_BLOB, ctypes.Array]:
    buf = ctypes.create_string_buffer(data, len(data))
    return _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


if os.name == "nt":
    _crypt32 = ctypes.WinDLL("Crypt32.dll", use_last_error=True)
    _kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)

    _crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB), wintypes.LPCWSTR,
        ctypes.POINTER(_DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(_DATA_BLOB)]
    _crypt32.CryptProtectData.restype = wintypes.BOOL
    _crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB), ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(_DATA_BLOB)]
    _crypt32.CryptUnprotectData.restype = wintypes.BOOL
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p


def available() -> bool:
    return os.name == "nt"


def protect(plain: str) -> str:
    """加密成可安全落库的字符串（base64）。"""
    if plain is None:
        plain = ""
    if not plain:
        return ""
    raw = plain.encode("utf-8")
    if not available():
        return _PLAIN_PREFIX + base64.b64encode(raw).decode("ascii")

    in_blob, in_buf = _blob(raw)
    ent_blob, ent_buf = _blob(_ENTROPY)
    out_blob = _DATA_BLOB()
    ok = _crypt32.CryptProtectData(
        ctypes.byref(in_blob), "TokenBoard", ctypes.byref(ent_blob),
        None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out_blob))
    if not ok:
        raise OSError(f"CryptProtectData 失败: {ctypes.get_last_error()}")
    try:
        data = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return base64.b64encode(data).decode("ascii")
    finally:
        _kernel32.LocalFree(out_blob.pbData)


def unprotect(token: str) -> str:
    """解密；失败时抛异常（调用方决定是提示还是跳过）。"""
    if not token:
        return ""
    if token.startswith(_PLAIN_PREFIX):
        return base64.b64decode(token[len(_PLAIN_PREFIX):].encode("ascii")).decode("utf-8")
    if not available():
        raise OSError("当前系统不支持 DPAPI")

    raw = base64.b64decode(token.encode("ascii"))
    in_blob, in_buf = _blob(raw)
    ent_blob, ent_buf = _blob(_ENTROPY)
    out_blob = _DATA_BLOB()
    ok = _crypt32.CryptUnprotectData(
        ctypes.byref(in_blob), None, ctypes.byref(ent_blob),
        None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out_blob))
    if not ok:
        raise OSError(f"CryptUnprotectData 失败: {ctypes.get_last_error()}")
    try:
        data = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return data.decode("utf-8")
    finally:
        _kernel32.LocalFree(out_blob.pbData)


def mask(key: str, keep: int = 4) -> str:
    """给界面用的掩码：sk-abcd********wxyz。"""
    if not key:
        return ""
    if len(key) <= keep * 2:
        return "*" * len(key)
    return f"{key[:keep]}{'*' * 6}{key[-keep:]}"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t = protect("sk-test-1234567890")
    print("密文:", t[:40], "...")
    print("还原:", unprotect(t))
    print("掩码:", mask("sk-test-1234567890"))
