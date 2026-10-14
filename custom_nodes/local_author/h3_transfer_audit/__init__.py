"""Observation-only encoder audit; no sampler, no production workflow changes."""
import copy
import hashlib
import json
import math
import re
from pathlib import Path

TRACES = {}
DEST = Path(r"<H3_PROJECT_DIR>\V28_3_MULTIREF_AUDIT_20261001\传递链实测")

def tensor_record(t):
    a = t.detach().cpu().contiguous()
    return {"shape": list(a.shape), "dtype": str(a.dtype),
            "sha256": hashlib.sha256(a.view(__import__('torch').uint8).numpy().tobytes()).hexdigest()}

class H3TransferAuditCLIP:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"clip": ("CLIP",), "audit_id": ("STRING",), "expected_prompt": ("STRING",)}}
    RETURN_TYPES = ("CLIP",)
    FUNCTION = "observe"
    CATEGORY = "H3/audit"
    def observe(self, clip, audit_id, expected_prompt):
        trace = TRACES.setdefault(audit_id, {})
        trace['expected_prompt'] = expected_prompt
        cloned = clip.clone()
        tokenize, encode = cloned.tokenize, cloned.encode_from_tokens_scheduled
        def capture(text, **kwargs):
            trace['actual_encoder_prompt'] = text
            trace['actual_prompt_sha256'] = hashlib.sha256(text.encode('utf-8')).hexdigest()
            trace['qwen_reference_items'] = [dict(type=x['type'], **tensor_record(x['data'])) for x in kwargs.get('minimax_ref_items', [])]
            result = tokenize(text, **kwargs)
            trace['tokenize_completed'] = True
            return result
        def capture_encode(tokens, *args, **kwargs):
            result = encode(tokens, *args, **kwargs)
            trace['real_encoder_completed'] = True
            return result
        cloned.tokenize = capture
        cloned.encode_from_tokens_scheduled = capture_encode
        return (cloned,)

class H3TransferAuditVAE:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"vae": ("VAE",), "audit_id": ("STRING",)}}
    RETURN_TYPES = ("VAE",)
    FUNCTION = "observe"
    CATEGORY = "H3/audit"
    def observe(self, vae, audit_id):
        trace = TRACES.setdefault(audit_id, {})
        trace['vae_reference_items'] = []
        observed = copy.copy(vae)
        encode = vae.encode
        def capture(pixels, *args, **kwargs):
            entry = tensor_record(pixels)
            result = encode(pixels, *args, **kwargs)
            entry['latent'] = tensor_record(result)
            trace['vae_reference_items'].append(entry)
            return result
        observed.encode = capture
        return (observed,)

class H3TransferAuditReceipt:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"conditioning": ("CONDITIONING",), "resolved_prompt": ("STRING",), "audit_id": ("STRING",), "manifest": ("STRING",), "width": ("INT",), "height": ("INT",)},
                "optional": {**{f"image_{i}": ("IMAGE",) for i in range(1, 10)}, "director_prompt": ("STRING",)}}
    RETURN_TYPES = ()
    OUTPUT_NODE = True
    FUNCTION = "receipt"
    CATEGORY = "H3/audit"
    def receipt(self, conditioning, resolved_prompt, audit_id, manifest, width, height, director_prompt=None, **images):
        from comfy_extras.nodes_minimax_h3 import _resize, CANVAS_MULTIPLE
        trace = TRACES[audit_id]
        meta = json.loads(manifest)
        expected = []
        for name, img in sorted(images.items(), key=lambda x: int(x[0].split('_')[-1])):
            h, w = img.shape[1:3]
            scale = min(1.0, math.sqrt(width * height / (w * h)))
            tw = max(CANVAS_MULTIPLE, round(w * scale / CANVAS_MULTIPLE) * CANVAS_MULTIPLE)
            th = max(CANVAS_MULTIPLE, round(h * scale / CANVAS_MULTIPLE) * CANVAS_MULTIPLE)
            expected.append(tensor_record(_resize(img[:1], tw, th, 'disabled')))
        qwen = trace.get('qwen_reference_items', [])
        vae = trace.get('vae_reference_items', [])
        blocks = conditioning[0][1].get('minimax_refs', [])
        trace['actual_conditioning_refs'] = [tensor_record(x['latent']) for x in blocks]
        trace['source_mapping'] = meta
        trace['resolved_external_prompt'] = resolved_prompt
        trace['director_compiled_prompt'] = director_prompt
        trace['checks'] = {
            'prompt_exact': resolved_prompt == trace.get('expected_prompt') == trace.get('actual_encoder_prompt'),
            'real_encoder_completed': trace.get('real_encoder_completed') is True,
            'source_to_qwen_order': len(expected) > 0 and [x['sha256'] for x in expected] == [x['sha256'] for x in qwen],
            'qwen_to_vae_order': [x['sha256'] for x in qwen] == [x['sha256'] for x in vae],
            'vae_to_h3_conditioning_order': [x['latent']['sha256'] for x in vae] == [x['sha256'] for x in trace['actual_conditioning_refs']],
            'hidden_prompt_empty': meta.get('hidden_prompt') == '',
        }
        if director_prompt is not None:
            trace['checks']['director_to_external_to_encoder_exact'] = director_prompt == resolved_prompt == trace.get('actual_encoder_prompt')
        trace['status'] = 'PASS' if all(trace['checks'].values()) else 'FAIL'
        DEST.mkdir(parents=True, exist_ok=True)
        name = re.sub(r'[^A-Za-z0-9_-]', '_', audit_id)
        (DEST / (name + '.json')).write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding='utf-8')
        if trace['status'] != 'PASS':
            raise RuntimeError('H3 transfer audit FAIL: ' + json.dumps(trace['checks']))
        return {'ui': {'text': [json.dumps({'status': trace['status'], 'checks': trace['checks']}, ensure_ascii=False)]}}

class H3DirectorCompileAudit:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"planner_json": ("STRING",), "plan_json": ("STRING",)}}
    RETURN_TYPES = ("STRING",)
    FUNCTION = "compile"
    CATEGORY = "H3/audit"
    def compile(self, planner_json, plan_json):
        from custom_nodes.H3_V28_Director import v28_director_core as core
        bundle = core.compile_h3_prompt(planner=json.loads(planner_json), plan=json.loads(plan_json), segment_id=1)
        return (bundle['CANONICAL_H3_PROMPT'],)

NODE_CLASS_MAPPINGS = {c.__name__: c for c in [H3TransferAuditCLIP, H3TransferAuditVAE, H3TransferAuditReceipt, H3DirectorCompileAudit]}
