"""애플리케이션 예외 계층."""


class AppError(Exception):
    """모든 애플리케이션 예외의 기반 클래스."""


class ConfigError(AppError):
    """설정 관련 오류 (필수값 누락, 형식 불일치 등)."""


class NetworkError(AppError):
    """네트워크 / API 통신 오류."""


class UpbitError(NetworkError):
    """업비트 API 관련 오류."""


class TelegramError(NetworkError):
    """텔레그램 API 관련 오류."""


class SignalError(AppError):
    """시그널 평가 중 발생한 오류."""


class BacktestError(AppError):
    """백테스트 실행 중 발생한 오류."""


class StateError(AppError):
    """상태 파일(cooldown.json, settings.json) 관련 오류."""
