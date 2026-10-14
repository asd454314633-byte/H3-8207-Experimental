"""Read current submitted workflow materials; no H3 mutations or model knowledge."""
import hashlib,json,re
from pathlib import Path

def _fingerprint(filename):
    import folder_paths
    path=Path(folder_paths.get_annotated_filepath(filename))
    if not path.is_file():raise ValueError(f"SIDECAR_ASSET_MISSING: {filename}")
    sha=hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):sha.update(block)
    return sha.hexdigest()

def build_context(prompt, extra_pnginfo, reference_roles, scene_settings, delta):
    roles=(reference_roles or "").strip()
    if not roles:
        roles="\n".join(line for line in delta.splitlines() if re.search(r"图[一二三四五六七八九十0-9]|<(?:Picture|Audio|Subject|Video)\s*\d+>",line,re.I))
    # Normalize Chinese picture labels into canonical declared resource tags.
    numeral={"一":"1","二":"2","三":"3","四":"4","五":"5","六":"6","七":"7","八":"8","九":"9"}
    roles=re.sub(r"图([一二三四五六七八九]|[0-9]+)",lambda m:"<Picture "+numeral.get(m.group(1),m.group(1))+">",roles)
    if not roles:raise ValueError("SIDECAR_CONTEXT_REQUIRED: 请填写当前参考职责；不读取旧global_settings")
    found={}
    # API graph: actual submitted loader inputs.
    for nid,item in (prompt or {}).items():
        cls=item.get("class_type", "")
        if not re.search(r"load.*(image|audio|video)|(image|audio|video).*load",cls,re.I):continue
        for key,value in item.get("inputs",{}).items():
            if isinstance(value,str) and re.search(r"\.(png|jpg|jpeg|webp|bmp|wav|mp3|flac|mp4|mov|ogg)(?:\s*\[[^]]+\])?$",value,re.I):
                found[str(nid)]={"source_node":str(nid),"source_type":cls,"filename":value,"sha256":_fingerprint(value)}
    # Compile-only submission omits downstream H3 dependencies; full workflow metadata preserves its materials.
    workflow=(extra_pnginfo or {}).get("workflow") or {}
    for item in workflow.get("nodes",[]):
        cls=item.get("type", ""); nid=str(item.get("id"))
        if not re.search(r"load.*(image|audio|video)|(image|audio|video).*load",cls,re.I):continue
        vals=item.get("widgets_values_named") or item.get("widgets_values") or []
        vals=vals.values() if isinstance(vals,dict) else vals
        for value in vals:
            if isinstance(value,str) and re.search(r"\.(png|jpg|jpeg|webp|bmp|wav|mp3|flac|mp4|mov|ogg)(?:\s*\[[^]]+\])?$",value,re.I):
                if nid not in found:found[nid]={"source_node":nid,"source_type":cls,"filename":value,"sha256":_fingerprint(value)}
                break
    if not found:raise ValueError("SIDECAR_CONTEXT_REQUIRED: 当前工作流没有可核对的素材")
    # Explicit role text binds Picture/Audio/Subject duties; loader digest changes also cut continuity.
    return {"assets":[found[k] for k in sorted(found,key=lambda s:(not s.isdigit(),int(s) if s.isdigit() else s))],
            "reference_roles":roles,"scene_settings":(scene_settings or "").strip()}
