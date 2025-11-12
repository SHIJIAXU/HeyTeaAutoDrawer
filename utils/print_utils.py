# utils/print_utils.py
# -*- coding: utf-8 -*-
"""
统一打印输出工具模块（兼容 GUI）

这个模块保留了原有的打印 API（print_info, print_error 等），
并在内部路由输出：始终向控制台打印，同时可选地把相同文本转发
给一个已注册的 GUI 回调（回调接收单条字符串）。

设计原则：向后兼容、容错（GUI 回调抛错不会影响控制台行为）、简单易用。
"""

from typing import Callable, Optional

_gui_callback: Optional[Callable[[str], None]] = None


def register_gui_logger(func: Optional[Callable[[str], None]]):
    """Register or unregister a GUI callback.

    Pass a callable that accepts a single string argument to receive messages.
    Pass None to unregister.
    """
    global _gui_callback
    _gui_callback = func


def _emit(text: str, end: str = "\n") -> None:
    """Emit message to console and to GUI callback if registered.

    The GUI callback may be called from any thread; GUI side should schedule
    UI updates via `after` if needed.
    """
    try:
        print(text, end=end, flush=True)
    except Exception:
        # Keep console printing best-effort; swallow errors
        pass

    if _gui_callback:
        try:
            _gui_callback(text)
        except Exception:
            # GUI callback errors must not break program flow
            pass


def print_title(text: str) -> None:
    """打印标题"""
    _emit("\n" + "=" * 60)
    _emit(text)
    _emit("=" * 60)


def print_info(text: str) -> None:
    """打印信息"""
    _emit(f"ℹ️  {text}")


def print_success(text: str) -> None:
    """打印成功信息"""
    _emit(f"✅ {text}")


def print_warning(text: str) -> None:
    """打印警告信息"""
    _emit(f"⚠️  {text}")


def print_error(text: str) -> None:
    """打印错误信息"""
    _emit(f"❌ {text}")


def print_step(text: str) -> None:
    """打印步骤信息"""
    _emit(f"→ {text}")


def print_progress(current: int, total: int, text: str = "") -> None:
    """打印进度信息"""
    if text:
        _emit(f"进度: {current}/{total} {text}")
    else:
        _emit(f"进度: {current}/{total}")


def print_section(text: str) -> None:
    """打印分割线"""
    _emit("-" * 60)
    _emit(text)


def print_countdown(seconds: int) -> None:
    """打印倒计时"""
    import time

    for i in range(seconds, 0, -1):
        # send carriage-return-style updates to console; GUI will receive the text
        # and should handle presentation. We forward the text as-is.
        _emit(f"  {i}...", end="\r")
        time.sleep(1)
    _emit("  开始！  ")
    
