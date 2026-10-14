"""The only implemented provider; owns all llama.cpp-specific behavior."""
import json, socket, time, urllib.request, urllib.error
from .context_budget import ContextBudgetGuard
from pathlib import Path
from .base import ModelProvider, ModelRequest, ModelResponse, ProviderError

class LocalLlamaCppProvider(ModelProvider):
    name = "local_llamacpp"

    def __init__(self, config):
        self.config = config
        self.base_url = config["base_url"].rstrip("/")
        self.model = config["alias"]
        self.context = int(config["ctx"])
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _http(self, path, payload=None, timeout=2):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.base_url + path, data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:600]
            raise ProviderError(f"SIDECAR_PROVIDER_HTTP: {exc.code} {detail}") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise ProviderError("SIDECAR_TIMEOUT: local provider request timed out") from exc
        except urllib.error.URLError as exc:
            code = "SIDECAR_TIMEOUT" if isinstance(exc.reason, (TimeoutError, socket.timeout)) else "SIDECAR_UNAVAILABLE"
            raise ProviderError(f"{code}: {exc.reason}") from exc
        except (ValueError, UnicodeError) as exc:
            raise ProviderError("SIDECAR_PROVIDER_RESPONSE: invalid JSON response") from exc

    def health(self):
        try:
            return self._http("/health").get("status") == "ok"
        except ProviderError:
            return False

    def capabilities(self):
        return {"provider": self.name, "model": self.model, "context_tokens": self.context,
                "structured_output": True, "reasoning": self.config.get('reasoning', 'OFF').upper() != 'OFF', "vision": False}

    def generate(self, request):
        started = time.monotonic()
        deadline = started + request.timeout
        def remaining():
            value = deadline - time.monotonic()
            if value <= 0:
                raise ProviderError("SIDECAR_TIMEOUT: provider deadline exceeded")
            return value
        messages = list(request.messages)
        if request.system:
            messages.insert(0, {"role": "system", "content": request.system})
        payload = {"model": self.model, "messages": messages, "max_tokens": request.max_tokens,
                   "temperature": request.temperature, "top_p": request.top_p,
                   "seed": int(self.config["seed"]), "cache_prompt": True,
                   "chat_template_kwargs": json.loads(self.config.get('chat_template_kwargs', '{"enable_thinking": false}')),
                   "repeat_penalty": 1.1, "repeat_last_n": 256,
                   "dry_multiplier": 0.8, "dry_base": 1.75, "dry_allowed_length": 4,
                   "dry_penalty_last_n": 1024}
        if request.stop:
            payload["stop"] = request.stop
        if request.structured_output:
            payload["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "h3_prompt", "strict": True, "schema": request.structured_output}}
        budget = ContextBudgetGuard(self).check(payload, timeout=min(30, remaining()))
        output = self._stream(payload, remaining, request.on_text)
        remaining()
        try:
            choice = output["choices"][0]
            text = choice["message"]["content"] or ""
            usage = output.get("usage") or {}
            if not text.strip():
                raise ValueError("empty content")
            return ModelResponse(text=text, finish_reason=choice.get("finish_reason"),
                prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"), latency_ms=round((time.monotonic()-started)*1000),
                provider=self.name, model=output.get("model", self.model),
                raw_metadata={"context_budget": budget, "id": output.get("id"), "timings": output.get("timings"), "usage": usage})
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError(f"SIDECAR_PROVIDER_RESPONSE: {exc}") from exc

    def _stream(self, payload, remaining, on_text):
        payload = dict(payload, stream=True, stream_options={"include_usage": True})
        req = urllib.request.Request(self.base_url + "/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"), headers={"Content-Type":"application/json"})
        text=""; usage={}; finish=None; timings=None; model=self.model; response_id=None
        try:
            # Closing this HTTP stream also cancels generation on the local server.
            with self.opener.open(req,timeout=remaining()) as response:
                for raw in response:
                    remaining()
                    line=raw.decode("utf-8").strip()
                    if not line.startswith("data:"):continue
                    blob=line[5:].strip()
                    if blob=="[DONE]":break
                    item=json.loads(blob)
                    if item.get("error"):raise ProviderError(f"SIDECAR_PROVIDER_RESPONSE: {item['error']}")
                    response_id=item.get("id",response_id); model=item.get("model",model)
                    usage=item.get("usage") or usage; timings=item.get("timings") or timings
                    for choice in item.get("choices",[]):
                        text+=choice.get("delta",{}).get("content") or ""
                        if on_text:on_text(text)
                        finish=choice.get("finish_reason") or finish
            return {"id":response_id,"model":model,"usage":usage,"timings":timings,
                    "choices":[{"message":{"content":text},"finish_reason":finish}]}
        except urllib.error.HTTPError as exc:
            raise ProviderError(f"SIDECAR_PROVIDER_HTTP: {exc.code} {exc.read().decode('utf-8','replace')[:300]}") from exc
        except (TimeoutError,socket.timeout) as exc:
            raise ProviderError("SIDECAR_TIMEOUT: streaming request timed out") from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"SIDECAR_UNAVAILABLE: {exc.reason}") from exc
        except (ValueError,UnicodeError) as exc:
            raise ProviderError("SIDECAR_PROVIDER_RESPONSE: invalid stream JSON") from exc

    def launch_command(self):
        c = self.config
        command = [str(Path(c["runtime"]) / "llama-server.exe"), "--model", c["model"],
                "--alias", self.model, "--host", "127.0.0.1", "--port", c["port"],
                "-ngl", c["gpu_layers"], "--n-cpu-ffn", c["n_cpu_ffn"],
                "-c", c["ctx"], "-np", c["parallel"], "-t", c["threads"],
                "-fa", "on", "-ctk", c["kv_k"], "-ctv", c["kv_v"],
                "--seed", c["seed"], "--reasoning", c.get('reasoning', 'off').lower(), "--no-mmproj",
                "--sleep-idle-seconds", "-1", "--cache-prompt", "--spec-type", "none"]
        if c.get('chat_template'):
            command += ['--chat-template', c['chat_template']]
        return command

