from exchange.model import ExtendedSettings
from functools import lru_cache


@lru_cache()
def get_settings():
    return ExtendedSettings()


settings = get_settings()
