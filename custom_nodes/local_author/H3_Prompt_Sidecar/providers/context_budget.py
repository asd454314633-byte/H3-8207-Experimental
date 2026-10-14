"""Exact final-chat token budgeting. Never mutate or truncate messages."""
from .base import ProviderError


class ContextBudgetGuard:
    def __init__(self, provider):
        self.provider = provider

    def check(self, payload, timeout=30):
        provider = self.provider
        props = provider._http('/props', timeout=timeout)
        ctx = props.get('default_generation_settings', {}).get('n_ctx') or props.get('n_ctx')
        if not isinstance(ctx, int) or ctx <= 0:
            raise ProviderError('PLANNER_CONTEXT_BUDGET_UNAVAILABLE: actual n_ctx missing')
        source = 'input_tokens'
        try:
            result = provider._http('/v1/chat/completions/input_tokens', payload, timeout=timeout)
            tokens = result['input_tokens']
        except ProviderError as exc:
            # Only an absent endpoint is compatible fallback, never timeout/500.
            if not any(f'SIDECAR_PROVIDER_HTTP: {code}' in str(exc) for code in (404, 405)):
                raise
            template = provider._http('/apply-template', payload, timeout=timeout)
            result = provider._http('/tokenize', {'content':template['prompt'], 'add_special':True,
                                                'parse_special':True}, timeout=timeout)
            tokens = len(result['tokens']);source = 'apply-template+tokenize'
        if type(tokens) is not int or tokens < 0:
            raise ProviderError('PLANNER_CONTEXT_BUDGET_UNAVAILABLE: invalid exact token count')
        margin = max(256, int(provider.config.get('context_safety_margin', 256)))
        requested = int(payload['max_tokens'])
        available = ctx-tokens-margin
        minimum = int(provider.config.get('planner_min_output', 3500))
        # Short deliberate planning requests keep their requested quality floor.
        floor = min(minimum, requested)
        budget = {'n_ctx':ctx,'real_input_tokens':tokens,'safety_margin':margin,
                  'requested_output':requested,'available_output':available,'source':source,
                  'minimum_output':floor,'adjusted':False}
        if requested > available:
            if available < floor:
                raise ProviderError('PLANNER_CONTEXT_BUDGET_EXCEEDED: '+str(budget))
            payload['max_tokens'] = available
            budget['adjusted'] = True
        budget['effective_output'] = payload['max_tokens']
        return budget
