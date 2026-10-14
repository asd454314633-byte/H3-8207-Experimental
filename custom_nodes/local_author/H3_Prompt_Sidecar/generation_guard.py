"""Detect repeated completed dialogue/paragraph cycles in cumulative streamed JSON."""
import re
from h3_sidecar_model_providers.base import GenerationLoopError

def _cycle(units):
    for width in range(1,min(8,len(units)//3)+1):
        tail=units[-width:]
        if tail==units[-2*width:-width]==units[-3*width:-2*width]:return True
    return False

def check_repetition(text):
    # Compare inside each bilingual field, never across EN and ZH.
    fields=re.split(r'"(?:english_prompt|chinese_prompt|state_delta)"\s*:',text)[1:]
    for field in fields[:2]:
        content=field.replace(r"\n","\n").replace(r'\"','"')
        lines=re.findall(r"<d>\s*(?:\[[^\]]*\]\s*)?(.*?)</d>",content,re.S)
        units=[re.sub(r"\s+"," ",line).strip().casefold() for line in lines]
        if _cycle(units):raise GenerationLoopError("SIDECAR_GENERATION_LOOP: 连续对白循环，流式请求已中止",text)
        paragraphs=[re.sub(r"\s+"," ",p).strip().casefold() for p in content.split("\n\n")[:-1] if len(p.strip())>=80]
        if _cycle(paragraphs):raise GenerationLoopError("SIDECAR_GENERATION_LOOP: 连续段落循环，流式请求已中止",text)
