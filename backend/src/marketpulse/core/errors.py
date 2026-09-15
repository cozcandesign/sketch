"""Proje geneli hata sınıfları."""


class MarketPulseError(Exception):
    """Tüm proje hatalarının tabanı."""


class ConfigError(MarketPulseError):
    """Eksik veya geçersiz konfigürasyon. Mesaj, kullanıcının ne yapması gerektiğini söyler."""


class StorageError(MarketPulseError):
    """Depolama katmanı hatası."""


class EngineAlreadyRunningError(MarketPulseError):
    """Taze bir heartbeat var: ikinci engine örneği başlatılmaz."""
