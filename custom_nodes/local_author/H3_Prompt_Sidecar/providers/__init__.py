import configparser
import importlib
from pathlib import Path
from .base import ModelRequest, ModelResponse, ModelProvider, ProviderError

def create_provider(config_path: Path) -> ModelProvider:
    import os
    config_path = Path(os.environ.get('H3_SIDECAR_CONFIG', str(config_path)))
    config = configparser.ConfigParser(interpolation=None)
    if not config.read(config_path, encoding="utf-8"):
        raise ProviderError(f"SIDECAR_CONFIG_MISSING: {config_path}")
    if config.has_section('director'):
        from .registry import RegisteredProvider
        return RegisteredProvider(config_path)
    name = config["sidecar"]["model_provider"]
    # Only local_llamacpp is shipped. Future modules export create(config).
    if not name.isidentifier():
        raise ProviderError("SIDECAR_PROVIDER_INVALID")
    module = importlib.import_module(f"{__name__}.{name}")
    section = config[name]
    if name == "local_llamacpp":
        return module.LocalLlamaCppProvider(section)
    return module.create(section)
