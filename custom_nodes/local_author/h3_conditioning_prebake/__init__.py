import json
from pathlib import Path
from . import cache_codec
cache_codec.MODEL_REGISTRY={str(Path(r['path']).resolve()):r for r in json.loads(Path(__file__).with_name('model_registry.json').read_text())}
from .nodes import NODE_CLASS_MAPPINGS
WEB_DIRECTORY = './web'
from .production import register
register()
if Path(__file__).with_name('observe.enabled').exists():
 from . import observer
