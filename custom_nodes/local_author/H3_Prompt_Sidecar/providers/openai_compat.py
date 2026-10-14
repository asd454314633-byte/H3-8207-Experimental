"""OpenAI-compatible HTTP provider for free external pools (OmniRoute / OpenRouter).

Config keys (from sidecar.ini [model.<key>]):
  provider      = openai_compat
  base_url      = e.g. http://127.0.0.1:20128/v1  or  https://openrouter.ai/api/v1
  model         = upstream model id (e.g. ddgw/gpt-5.6-luna)
  api_key_env   = optional env var name; value is never stored in config files
  reasoning_effort = optional (e.g. low) forwarded when supported
  temperature / top_p = optional overrides handled by the registry

Fallback policy: transport-level failures raise FallbackableError so a chain
(AUTO) may move to the next model.  Contract-level failures (4xx other than
429/402/404) are plain ProviderError and must never trigger fallback.
A single clean retry drops response_format when the endpoint rejects schemas.
"""
import json
import os
import time
import urllib.error
import urllib.request

from .base import FallbackableError, ModelProvider, ModelResponse, ProviderError

_FALLBACKABLE_HTTP = {429, 402, 404, 500, 502, 503, 504}


def _strip_think(text):
    if "<think>" in text:
        import re
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    return text


class OpenAICompatProvider(ModelProvider):
    name = 'openai_compat'

    def __init__(self, config):
        self.config = dict(config)
        self.base_url = str(config['base_url']).rstrip('/')
        self.model = str(config['model'])
        self.api_key = os.environ.get(str(config.get('api_key_env', '') or ''), '')
        self.reasoning_effort = str(config['reasoning_effort']) if config.get('reasoning_effort') else None
        self.label = config.get('label', self.model)

    def _headers(self):
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['Authorization'] = 'Bearer ' + self.api_key
        return headers

    def _post(self, payload, timeout):
        request = urllib.request.Request(self.base_url + '/chat/completions',
                                         data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                                         headers=self._headers(), method='POST')
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=max(1.0, timeout)) as response:
                body = json.loads(response.read().decode('utf-8', 'replace'))
                headers = {k.lower(): v for k, v in response.headers.items()}
                return response.status, body, headers, round((time.monotonic() - started) * 1000)
        except urllib.error.HTTPError as exc:
            detail = ''
            try:
                detail = exc.read().decode('utf-8', 'replace')[:500]
            except Exception:
                pass
            if exc.code in _FALLBACKABLE_HTTP:
                raise FallbackableError(f'HTTP_{exc.code}: {detail}') from exc
            raise ProviderError(f'HTTP_{exc.code}: {detail}') from exc
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            # Timeout before any valid response, endpoint down, or malformed body.
            raise FallbackableError(f'TRANSPORT: {type(exc).__name__}: {exc}') from exc

    def generate(self, request):
        payload = {'model': self.model, 'messages': request.messages,
                   'max_tokens': int(request.max_tokens), 'temperature': float(request.temperature),
                   'top_p': float(request.top_p)}
        if request.stop:
            payload['stop'] = list(request.stop)
        if self.reasoning_effort:
            payload['reasoning_effort'] = self.reasoning_effort
        if request.structured_output:
            payload['response_format'] = {'type': 'json_schema',
                                          'json_schema': {'name': 'output', 'strict': False,
                                                          'schema': request.structured_output}}
        schema_dropped = False
        try:
            status, body, headers, latency_ms = self._post(payload, request.timeout)
        except ProviderError as exc:
            # One clean retry without the schema when THIS endpoint rejects
            # response_format. Same model, no valid response yet, never a model
            # switch; the decision is logged as schema_dropped.
            if not (request.structured_output and 'HTTP_400' in str(exc)
                    and any(marker in str(exc).lower() for marker in ('response_format', 'json_schema', 'schema'))):
                raise
            payload.pop('response_format', None)
            schema_dropped = True
            status, body, headers, latency_ms = self._post(payload, request.timeout)
        if status == 200 and 'choices' not in body:
            raise ProviderError('UPSTREAM_MALFORMED: response has no choices')
        if 'error' in body:
            raise ProviderError('UPSTREAM_ERROR: ' + json.dumps(body['error'], ensure_ascii=False)[:400])
        message = body['choices'][0].get('message') or {}
        content = message.get('content')
        if not content and message.get('reasoning'):
            # Reasoning burned the entire budget with no visible text.
            raise FallbackableError('REASONING_ATE_BUDGET: no visible content')
        content = _strip_think(content or '')
        if not content.strip():
            raise FallbackableError('EMPTY_CONTENT')
        usage = body.get('usage') or {}
        cost = usage.get('cost')
        if cost is None and headers.get('x-omniroute-response-cost') is not None:
            try:
                cost = float(headers['x-omniroute-response-cost'])
            except ValueError:
                cost = None
        metadata = {'requested_model': self.model,
                    'http_status': status,
                    'omniroute_headers': {k: v for k, v in headers.items() if k.startswith('x-omniroute-')} or None}
        if schema_dropped:
            metadata['schema_dropped'] = True
        return ModelResponse(text=content, finish_reason=body['choices'][0].get('finish_reason'),
                             prompt_tokens=usage.get('prompt_tokens'), completion_tokens=usage.get('completion_tokens'),
                             total_tokens=usage.get('total_tokens'), latency_ms=latency_ms,
                             provider=self.name, model=body.get('model') or self.model,
                             raw_metadata=metadata)

    def health(self):
        try:
            request = urllib.request.Request(self.base_url + '/models', headers=self._headers())
            with urllib.request.urlopen(request, timeout=8) as response:
                return response.status == 200
        except Exception:
            return False

    def capabilities(self):
        return {'provider': self.name, 'model': self.model, 'label': self.label, 'transport': 'openai_compat'}


def create(config):
    return OpenAICompatProvider(config)
