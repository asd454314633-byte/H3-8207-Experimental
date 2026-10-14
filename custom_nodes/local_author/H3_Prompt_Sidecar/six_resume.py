"""Six-panel transport bookkeeping. Native latent storage/algorithms stay unchanged."""
import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path

PROVIDER = "CORE_NATIVE_MASKED_AV"
FILE_STATE_LOCK = threading.RLock()


def project_dir(root, project):
    if not project or len(project) > 64 or any(not (c.isalnum() or c in "-_") for c in project):
        raise ValueError("存档项目只能使用字母、数字、中文、横线和下划线（最多64字符）")
    return Path(root) / "h3_continuation" / project


def read_json(path, default):
    with FILE_STATE_LOCK:return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def write_json_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        with temporary.open("wb") as handle:
            handle.write(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def reconcile_pending(server, root, project, index):
    recover = getattr(server, "h3_prebake_recover", None)
    if recover and recover(project, index):
        return
    directory = project_dir(root, project)
    path = directory / "six_acceptance.json"
    with FILE_STATE_LOCK:
        receipts = read_json(path, {})
        receipt = receipts.get(str(index), {})
    group_id = receipt.get("group_id")
    if receipt.get("status") != "PENDING" or not group_id:
        return
    controller = getattr(server, "h3_native_merge_control", None)
    state = controller.read(project).get("_native_merge", {}) if controller else {}
    group = state.get("groups", {}).get(group_id, {})
    prompt_id = group.get("prompt_ids", {}).get(str(index))
    if not prompt_id:
        return
    # PreBake owns a second, group-scoped ledger. Delegate its refresh recovery
    # to the same validator/committer used after live completion; never mint a
    # SUCCESS receipt from this UI transport layer alone.
    if group_id:
        reconcile = getattr(server, "h3_prebake_acceptance_reconcile", None)
        if not reconcile:
            return
        prebake_path = directory / ("prebake_" + group_id + ".json")
        prebake = read_json(prebake_path, {})
        segment = prebake.get("segments", {}).get(str(index), {})
        if prebake.get("group_id") != group_id or segment.get("group_id") != group_id:
            return
        reconcile({"context": {"project_id": project, "group_id": group_id},
                   "index": index, "prompt_id": prompt_id,
                   "cache_key": segment.get("cache_key")})
        return
    history = server.prompt_queue.get_history(prompt_id=prompt_id).get(prompt_id)
    if not history or history["status"].get("status_str") != "success" or history["status"].get("completed") is not True:
        return
    output_graph = history["prompt"][2]
    saves = [n for n in output_graph.values() if n["class_type"] == "H3ContinuationSave" and n["inputs"].get("enabled") is True]
    videos = [(node_id, n) for node_id, n in output_graph.items() if n["class_type"] == "SaveVideo"]
    if len(saves) != 1 or len(videos) != 1 or saves[0]["inputs"].get("project_id") != project or int(saves[0]["inputs"].get("segment_index", -1)) != index:
        return
    saved_video = history.get("outputs", {}).get(videos[0][0], {})
    files = [entry for key in ("images", "videos") for entry in saved_video.get(key, [])
             if Path(entry.get("filename", "")).suffix.lower() in (".mp4", ".webm", ".mov", ".mkv")]
    if len(files) != 1 or files[0].get("type") != "output":
        return
    video_path = (Path(root) / files[0].get("subfolder", "") / files[0]["filename"]).resolve()
    if not video_path.is_relative_to(Path(root).resolve()) or not video_path.is_file():
        return
    inspected = inspect_segment(root, project, index, require_accepted=False, expected_prompt_id=prompt_id)
    latent_path = Path(inspected["path"])
    with FILE_STATE_LOCK:
        latest = read_json(path, {})
        pending = latest.get(str(index), {})
        if pending.get("status") != "PENDING" or pending.get("group_id") != group_id:
            return
        latest[str(index)] = {"status": "SUCCESS", "prompt_id": prompt_id, "group_id": group_id,
                              "latent_path": str(latent_path),
                              "latent_sha256": hashlib.sha256(latent_path.read_bytes()).hexdigest().upper(),
                              "accepted_at_epoch": time.time(), "reconciled_from_history": True}
        write_json_atomic(path, latest)


def inspect_segment(root, project, index, require_accepted=True, expected_prompt_id=None):
    from safetensors import safe_open
    directory = project_dir(root, project)
    ledger = read_json(directory / "index.json", {})
    entry = next((s for s in ledger.get("segments", []) if int(s["segment_index"]) == index), None)
    path = directory / ("seg_%05d.safetensors" % index)
    receipts = read_json(directory / "six_acceptance.json", {})
    receipt = receipts.get(str(index))
    # Bound PreBake stories retain their acceptance authority even when the
    # unchanged Native Merge controller requests a header-only inspection.
    versions = read_json(Path(root) / 'h3_continuation' / '_prebake_executions.json', {})
    for b in read_json(Path(root) / 'h3_continuation' / '_prebake_stories.json', {}).values():
        versions[b['execution_version']] = b
    bindings = [b for b in versions.values() if b.get('project_id') == project]
    if bindings:
        if len(bindings) != 1:
            raise ValueError('Ambiguous bound PreBake project')
        binding = bindings[0]
        prebake = read_json(directory / ('prebake_' + binding['group_id'] + '.json'), {})
        accepted = prebake.get('segments', {}).get(str(index), {})
        if not receipt or receipt.get('status') != 'SUCCESS' or accepted.get('video_status') != 'SUCCESS':
            raise ValueError('Bound PreBake segment has no verified SUCCESS receipt')
        group = receipts.get('_native_merge', {}).get('groups', {}).get(binding['group_id'], {})
        legacy = (not accepted.get('attempt') and prebake.get('group_id') == binding['group_id']
                  and receipt.get('prompt_id') is not None
                  and group.get('prompt_ids', {}).get(str(index)) == receipt.get('prompt_id') == accepted.get('prompt_id'))
        fields = ('prompt_id', 'latent_sha256') if legacy else ('group_id', 'prompt_id', 'revision', 'cache_key', 'latent_sha256')
        if any(receipt.get(k) is None or receipt.get(k) != accepted.get(k) for k in fields) or receipt.get('group_id', binding['group_id'] if legacy else None) != binding['group_id']:
            raise ValueError('Bound PreBake receipt/ledger identity mismatch')
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest().upper() != receipt['latent_sha256']:
            raise ValueError('Bound PreBake latent SHA256 mismatch')
        if not require_accepted and expected_prompt_id is None:
            if group.get('prompt_ids', {}).get(str(index)) != receipt['prompt_id']:
                raise ValueError('Native Merge exact prompt_id differs from accepted PreBake attempt')
        if expected_prompt_id is not None and expected_prompt_id != receipt['prompt_id']:
            raise ValueError('Requested prompt_id differs from accepted PreBake attempt')
        expected_prompt_id = receipt['prompt_id']
    # Preserve the public package's generic Native receipt safeguards as well
    # as the version-specific PreBake authority above.
    if require_accepted and (not receipt or receipt.get("status") != "SUCCESS" or not receipt.get("prompt_id") or not receipt.get("latent_sha256")):
        raise ValueError("第%d段尚未实际SUCCESS，不能作为连续续跑状态" % (index + 1))
    if not entry or not path.is_file():
        raise ValueError("缺少第%d段已接受状态" % (index + 1))
    if ledger.get("provider") != PROVIDER or entry.get("provider") != PROVIDER:
        raise ValueError("存档不是CORE_NATIVE_MASKED_AV")
    expected_prompt_id = expected_prompt_id or (receipt.get("prompt_id") if require_accepted else None)
    if require_accepted and hashlib.sha256(path.read_bytes()).hexdigest().upper() != receipt["latent_sha256"].upper():
        raise ValueError("latent内容与已接受回执不一致")
    if expected_prompt_id and (not bindings or entry.get('prompt_id') is not None) and entry.get('prompt_id') != expected_prompt_id:
        raise ValueError("Native索引与实际SUCCESS prompt_id不一致")
    # Read tensor headers only, without loading a model or tensor into GPU memory.
    with safe_open(str(path), framework="pt", device="cpu") as handle:
        meta = handle.metadata()
        video = handle.get_slice("video").get_shape()
        audio = handle.get_slice("audio").get_shape()
        if meta.get("provider") != PROVIDER or int(meta.get("segment_index", -1)) != index:
            raise ValueError("latent元数据与段号/Provider不一致")
        if expected_prompt_id is not None and meta.get("prompt_id") != expected_prompt_id:
            raise ValueError("latent元数据与实际SUCCESS prompt_id不一致")
        if len(video) != 5 or video[2] < 12 or len(audio) < 3 or audio[-1] < 65:
            raise ValueError("latent不满足39帧/65步前缀条件")
    return {"segment_index": index, "path": str(path), "provider": PROVIDER,
            "video_shape": video, "audio_shape": audio, "accepted": bool(require_accepted or bindings), "prompt_id": expected_prompt_id}


def register_routes():
    import asyncio
    import folder_paths
    from aiohttp import web
    from server import PromptServer
    server = PromptServer.instance
    server.h3_acceptance_state_lock = FILE_STATE_LOCK

    @server.routes.get("/h3/six/store")
    async def status(request):
        try:
            root = folder_paths.get_output_directory()
            project = request.query.get("project_id", "")
            index = int(request.query.get("segment_index", -1))
            if not 0 <= index <= 5:
                raise ValueError("无效段号")
            reconcile_pending(server, root, project, index)
            return web.json_response(inspect_segment(root, project, index))
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=409)

    # Isolated post-generation controller; no Continuation tensor/acceptance changes.
    from .native_merge_control import register as register_native_merge
    server.h3_native_merge_control = register_native_merge(server)

    @server.routes.post("/h3/six/acceptance")
    async def acceptance(request):
        try:
            data = await request.json()
            project, index = data["project_id"], int(data["segment_index"])
            group_id = data.get("group_id")
            if group_id is not None and (not group_id or len(group_id) > 160 or any(not (c.isalnum() or c in "-_") for c in group_id)):
                raise ValueError("无效PreBake group_id")
            if not 0 <= index <= 5:
                raise ValueError("无效段号")
            directory = project_dir(folder_paths.get_output_directory(), project)
            path = directory / "six_acceptance.json"
            with FILE_STATE_LOCK:
                receipts = read_json(path, {})
            phase = data["status"]
            prebake = read_json(directory / ("prebake_" + group_id + ".json"), {}) if group_id else {}
            if prebake.get("execution"):
                if phase != "PENDING":
                    raise ValueError("Bound PreBake SUCCESS must use exact history reconciliation")
                pending_writer = getattr(server, "h3_prebake_pending", None)
                if not pending_writer:
                    raise ValueError("PreBake lifecycle handler unavailable")
                return web.json_response(pending_writer(project, index, group_id))
            if phase == "SUCCESS":
                prompt_id = data["prompt_id"]
                pending = receipts.get(str(index), {})
                if group_id is not None and pending.get("group_id") != group_id:
                    raise ValueError("PreBake group changed while the prompt was running")
                # Core emits websocket SUCCESS just before it commits history.
                history = None
                for _ in range(40):
                    history = server.prompt_queue.get_history(prompt_id=prompt_id).get(prompt_id)
                    if history:
                        break
                    await asyncio.sleep(0.05)
                if not history or history["status"].get("status_str") != "success" or history["status"].get("completed") is not True or any(event == "execution_error" for event, _ in history["status"].get("messages", [])):
                    raise ValueError("未找到该任务的实际SUCCESS，拒绝接受latent")
                output = history["prompt"][2]
                saves = [n for n in output.values() if n["class_type"] == "H3ContinuationSave"]
                if len(saves) != 1 or saves[0]["inputs"].get("project_id") != project or saves[0]["inputs"].get("segment_index") != index or saves[0]["inputs"].get("enabled") is not True:
                    raise ValueError("任务的Native存档项目/段号不一致")
                video_nodes = [(node_id, node) for node_id, node in output.items() if node["class_type"] == "SaveVideo"]
                if len(video_nodes) != 1:
                    raise ValueError("任务没有唯一的SaveVideo输出")
                video_result = history.get("outputs", {}).get(video_nodes[0][0], {})
                video_files = [entry for key in ("images", "videos") for entry in video_result.get(key, [])
                               if Path(entry.get("filename", "")).suffix.lower() in (".mp4", ".webm", ".mov", ".mkv")]
                if len(video_files) != 1 or video_files[0].get("type") != "output":
                    raise ValueError("任务没有唯一的真实视频输出文件")
                video_path = (Path(folder_paths.get_output_directory()) / video_files[0].get("subfolder", "") / video_files[0]["filename"]).resolve()
                if not video_path.is_relative_to(Path(folder_paths.get_output_directory()).resolve()) or not video_path.is_file():
                    raise ValueError("真实视频输出文件缺失或超出output目录")
                # PENDING is bypassed only here, after checking actual SUCCESS.
                inspected = inspect_segment(folder_paths.get_output_directory(), project, index, require_accepted=False, expected_prompt_id=prompt_id)
                latent_path = Path(inspected["path"])
                latent_sha256 = hashlib.sha256(latent_path.read_bytes()).hexdigest().upper()
                receipts[str(index)] = {"status": "SUCCESS", "prompt_id": prompt_id, "group_id": group_id,
                                        "latent_path": str(latent_path), "latent_sha256": latent_sha256,
                                        "accepted_at_epoch": time.time()}
            elif phase == "PENDING":
                # A later error, cancellation or browser disconnect leaves this
                # segment unaccepted even if Save ran before the video failed.
                receipts[str(index)] = {"status": "PENDING", "group_id": group_id,
                                        "submitted_at_epoch": time.time()}
            else:
                raise ValueError("无效接受状态")
            with FILE_STATE_LOCK:
                latest = read_json(path, {})
                if phase == "SUCCESS":
                    pending = latest.get(str(index), {})
                    if pending.get("group_id") != group_id or (pending.get("prompt_id") and pending.get("prompt_id") != prompt_id):
                        raise ValueError("PreBake group/prompt changed before SUCCESS receipt commit")
                latest[str(index)] = receipts[str(index)]
                write_json_atomic(path, latest)
            return web.json_response({"status": phase, "segment_index": index})
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=409)
