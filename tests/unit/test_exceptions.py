"""AppError 예외 계층 유닛 테스트 (마일스톤 1)."""

import pytest

from signal_program.exceptions import (
    AppError,
    BacktestError,
    ConfigError,
    NetworkError,
    SignalError,
    StateError,
    TelegramError,
    UpbitError,
)


def test_exception_hierarchy() -> None:
    assert issubclass(ConfigError, AppError)
    assert issubclass(NetworkError, AppError)
    assert issubclass(UpbitError, NetworkError)
    assert issubclass(TelegramError, NetworkError)
    assert issubclass(SignalError, AppError)
    assert issubclass(BacktestError, AppError)
    assert issubclass(StateError, AppError)


def test_config_error_catchable_as_app_error() -> None:
    with pytest.raises(AppError):
        raise ConfigError("설정 오류")


def test_upbit_error_catchable_as_network_error() -> None:
    with pytest.raises(NetworkError):
        raise UpbitError("업비트 연결 실패")


def test_upbit_error_catchable_as_app_error() -> None:
    with pytest.raises(AppError):
        raise UpbitError("업비트 연결 실패")
