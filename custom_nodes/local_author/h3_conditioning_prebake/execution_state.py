"""Story drafts and immutable execution branches; never infer a predecessor from filenames."""
import copy
import os
import shutil
import time
import uuid
from safetensors import SafetensorError
from . import production as p


def registry_path():
    return p.story_registry().with_name('_prebake_executions.json')


def bindings():
    versions = p.read_state(registry_path()) or {}
    for binding in (p.read_state(p.story_registry()) or {}).values():
        versions[binding['execution_version']] = binding
    return list(versions.values())


def remember(binding):
    versions = p.read_state(registry_path()) or {}
    versions[binding['execution_version']] = copy.deepcopy(binding)
    p.atomic_json(registry_path(), versions)


def select(binding):
    remember(binding)
    path = p.story_registry().with_name('_prebake_current.json')
    pointers = p.read_state(path) or {}
    pointers[binding['story_id']] = binding['execution_version']
    p.atomic_json(path, pointers)


def selected_story(sid):
    pointers = p.read_state(p.story_registry().with_name('_prebake_current.json')) or {}
    version = pointers.get(sid)
    if version:
        binding = (p.read_state(registry_path()) or {}).get(version)
        if not binding or binding['story_id'] != sid:
            raise ValueError('Story execution pointer is inconsistent')
        data = p.read_state(p.ledger_path(binding))
        if not data or any(data.get('execution', {}).get(k) != binding[k] for k in ('story_id','project_id','group_id','execution_version')):
            raise ValueError('Selected execution ledger is inconsistent')
        return data['execution']
    return (p.read_state(p.story_registry()) or {}).get(sid)


def draft(payload, state_lock=None):
    ctx = payload['context']
    texts = payload['texts']
    if len(texts) != 6 or not all(isinstance(t, str) for t in texts):
        raise ValueError('Expected six draft texts')
    with p.LOCK, state_lock or p.nullcontext():
        # A draft does not revoke or cancel an already submitted snapshot.
        binding, _ = p.bound_context(ctx)
        path = p.story_registry().with_name('_prebake_drafts.json')
        drafts = p.read_state(path) or {}
        drafts[binding['story_id']] = {'texts': list(texts), 'updated_at_epoch': time.time()}
        p.atomic_json(path, drafts)
        return {'binding': binding, 'draft_saved': True, 'invalidated_video_from': None}


def prepare(payload, state_lock=None):
    """Resolve compatibility before planning; fork only when changing existing results."""
    with p.LOCK, state_lock or p.nullcontext():
        ctx = copy.deepcopy(payload['context'])
        sid = p.token(ctx.get('story_id') or ctx['group_id'])
        submission_id = payload.get('submission_id')
        request_hash = p.codec.digest(p.codec.canonical(payload))
        submission_path = p.story_registry().with_name('_prebake_submissions.json')
        submissions = p.read_state(submission_path) or {}
        if submission_id:
            p.token(submission_id)
            prior = submissions.get(submission_id)
            if prior:
                if prior['request_sha256'] != request_hash or prior['binding']['story_id'] != sid:
                    raise ValueError('Submission identity reused with different snapshot')
                p.bound_context(prior['binding'])
                return {'binding': prior['binding'], 'changed_segments': [], 'duplicate_submission': True}
        current = selected_story(sid)
        if not current:
            current = p.story({'action': 'bind', 'story_id': sid,
                               'group_id': ctx['group_id'], 'project_id': ctx['project_id'],
                               'start_index': int(payload.get('start_index', 0)),
                               'start_mode': payload.get('start_mode', 'independent')}, state_lock)['binding']
        elif any(ctx.get(k) not in (None, current[k]) for k in ('project_id', 'group_id')):
            # Explicit historical branches are allowed; unrelated projects are not.
            matches = [b for b in bindings() if b['story_id'] == sid and
                       all(ctx.get(k) == b[k] for k in ('project_id', 'group_id', 'execution_version'))]
            if len(matches) != 1:
                raise ValueError('Requested execution does not belong to this Story')
            current = matches[0]
        ctx.update(current)
        ctx['fps'] = payload['context'].get('fps', 24)
        first = int(payload.get('start_index', current['start_index']))
        mode = payload.get('start_mode', current['start_mode'])
        if first not in range(6) or mode not in ('resume', 'independent'):
            raise ValueError('Invalid start policy')
        index = int(payload['requested_index'])
        if index not in range(6):
            raise ValueError('Invalid requested segment')
        ledger = p.read_state(p.ledger_path(current))
        texts = payload['texts']
        if len(texts) != 6:
            raise ValueError('Expected six final texts')
        changed = []
        revisions = list(current['revisions'])
        for i, text in enumerate(texts):
            # Only this segment is being submitted. Other editors are drafts;
            # their text/graph must not rewrite an accepted execution snapshot.
            if i != index:
                continue
            entry = ledger['segments'].get(str(i), {})
            digest = p.codec.digest(text.encode())
            if entry.get('final_prompt_sha256') != digest:
                revisions[i] = max(revisions[i], int(entry.get('revision', 0))) + 1
            ctx['revisions'] = revisions
            if not text.strip():
                if entry.get('final_prompt_sha256'):
                    changed.append(i)
                continue
            contract, _ = p.build_contract(payload['graph'], text, i, ctx)
            key = p.codec.verified_contract(p.json.dumps(contract))[1] if contract else p.fallback_conditioning_key(payload['graph'], text, i, ctx)
            if entry.get('cache_key') and entry['cache_key'] != key:
                changed.append(i)
        populated = any(e.get('attempt') or e.get('video_status') == 'SUCCESS' for e in ledger['segments'].values())
        redo = bool(ledger['segments'].get(str(index), {}).get('attempt'))
        policy = (first, mode) != (current['start_index'], current['start_mode'])
        active = ledger['segments'].get(str(index), {}).get('attempt', {}).get('status') in ('PREPARED', 'PENDING', 'CANCELLING', 'BLOCKED')
        if active and not changed and not policy and not submission_id:
            raise ValueError('This exact segment already has an active attempt')
        recoverable = any(int(i) < index and entry.get('video_status') == 'STALE' and
                          entry.get('inherited_from') for i, entry in ledger['segments'].items())
        if populated and (changed or redo or policy) or recoverable:
            current, ledger = fork(current, ledger, state_lock, requested_index=index)
            for i in range(6):
                if i != index and str(i) in ledger['segments']:
                    revisions[i] = ledger['segments'][str(i)].get('revision', revisions[i])
            if redo:
                # A new attempt changes the selected output even when its
                # conditioning cache is identical. Descendants cannot merge
                # against the new attempt until regenerated.
                p.invalidate_video_chain(p.ledger_path(current), ledger, current, index, state_lock)
        current = {**current, 'start_index': first, 'start_mode': mode, 'revisions': revisions}
        ledger['execution'] = current
        p.atomic_json(p.ledger_path(current), ledger)
        select(current)
        stories = p.read_state(p.story_registry()) or {}
        stories[sid] = current
        p.atomic_json(p.story_registry(), stories)
        if submission_id:
            submissions[submission_id] = {'request_sha256': request_hash, 'binding': copy.deepcopy(current)}
            p.atomic_json(submission_path, submissions)
        return {'binding': current, 'changed_segments': changed}


def fork(source, ledger, state_lock=None, requested_index=None):
    remember(source)
    version = uuid.uuid4().hex
    binding = {**source, 'project_id': 'H3_EXEC_' + version,
               'execution_version': version, 'parent_execution_version': source['execution_version']}
    old = p.ledger_path(source).parent
    new = p.ledger_path(binding).parent
    new.mkdir(parents=True, exist_ok=False)
    data = copy.deepcopy(ledger)
    data.update(project_id=binding['project_id'], execution=binding)
    receipts = p.read_state(old / 'six_acceptance.json') or {}
    source_timeline = p.read_state(old / 'long_song_timeline.json') or {}
    if not isinstance(source_timeline, dict):
        source_timeline = {}
    inherited = {}
    inherited_timeline = {}
    index = p.read_state(old / 'index.json') or {}
    retained = []
    for i, entry in sorted(data['segments'].items(), key=lambda item: int(item[0])):
        receipt = receipts.get(i, {})
        origin = old
        provenance = entry.get('inherited_from', {})
        if (requested_index is not None and int(i) < requested_index and
                entry.get('video_status') == 'STALE' and
                receipt.get('invalidated_reason') == 'CACHE_CONTRACT_CHANGED' and provenance):
            # Migrate only a proven inherited output invalidated by the former
            # all-editors planner. Never bless a stale receipt or a filename.
            matches = [b for b in bindings() if
                       b['story_id'] == source['story_id'] and b['group_id'] == source['group_id'] and
                       b['project_id'] == provenance.get('project_id') and
                       b['execution_version'] == provenance.get('execution_version')]
            if len(matches) == 1:
                parent = matches[0]
                parent_root = p.ledger_path(parent).parent
                parent_receipt = (p.read_state(parent_root / 'six_acceptance.json') or {}).get(i, {})
                if (parent_receipt.get('prompt_id') == provenance.get('prompt_id') ==
                        receipt.get('invalidated_prompt_id') and parent_receipt.get('status') == 'SUCCESS'):
                    try:
                        p.verify_predecessor(parent, int(i) + 1)
                        intact = p.codec.file_sha(old / ('seg_%05d.safetensors' % int(i))) == parent_receipt['latent_sha256']
                    except (ValueError, OSError, SafetensorError):
                        intact = False
                    parent_data = p.read_state(p.ledger_path(parent))
                    parent_entry = parent_data['segments'][i]
                    video = p.Path(parent_receipt.get('video_path', '')).resolve()
                    output_root = old.parent.parent.resolve()
                    intact = (intact and video.is_relative_to(output_root) and video.is_file() and
                              p.codec.file_sha(video) == parent_receipt.get('video_sha256') and
                              parent_receipt.get('cache_key') == parent_entry.get('cache_key') and
                              parent_receipt.get('revision') == parent_entry.get('revision'))
                    dependency = parent_entry.get('predecessor_index', 'UNKNOWN')
                    dependency_matches = dependency is None or (isinstance(dependency, int) and
                        data['segments'].get(str(dependency), {}).get('video_status') == 'SUCCESS' and
                        data['segments'][str(dependency)].get('prompt_id') ==
                        parent_data['segments'].get(str(dependency), {}).get('prompt_id'))
                    if dependency_matches and intact:
                        entry = copy.deepcopy(parent_entry)
                        data['segments'][i] = entry
                        receipt = parent_receipt
                        origin = parent_root
        if entry.get('video_status') != 'SUCCESS' or receipt.get('status') != 'SUCCESS':
            entry.pop('attempt', None)
            entry.update(video_status='NOT_GENERATED', receipt_status='NOT_GENERATED')
            continue
        try:
            p.verify_predecessor(parent if origin != old else source, int(i) + 1)
        except (ValueError, OSError, SafetensorError) as error:
            # Keep the damaged historical branch, but do not adopt its output.
            # An independent task elsewhere still has a legal path forward.
            entry.pop('attempt', None)
            entry.update(video_status='UNAVAILABLE', receipt_status='UNAVAILABLE', recovery_error=str(error))
            continue
        src = origin / ('seg_%05d.safetensors' % int(i))
        dst = new / src.name
        # Native saves atomically replace the path; hard links preserve the old bytes.
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy2(src, dst)
        if p.codec.file_sha(dst) != receipt['latent_sha256']:
            raise ValueError('Execution fork latent copy changed')
        parent_attempt = entry.pop('attempt', None)
        if parent_attempt is not None:
            entry['inherited_attempt'] = copy.deepcopy(parent_attempt)
        entry['inherited_from'] = {'story_id': source['story_id'],
                                   'group_id': source['group_id'],
                                   'project_id': receipt.get('project_id', source['project_id']),
                                   'execution_version': receipt.get('execution_version', source['execution_version']),
                                   'parent_project_id': source['project_id'],
                                   'parent_execution_version': source['execution_version'],
                                   'attempt_id': receipt.get('attempt_id') or (parent_attempt or {}).get('attempt_id'),
                                   'prompt_id': receipt['prompt_id'],
                                   'revision': receipt.get('revision'),
                                   'cache_key': receipt.get('cache_key')}
        inherited[i] = copy.deepcopy(receipt)
        inherited[i]['inherited_from'] = copy.deepcopy(entry['inherited_from'])
        inherited[i]['latent_path'] = str(dst)
        timeline_plan = source_timeline.get(str(i))
        if isinstance(timeline_plan, dict) and timeline_plan.get('segment_index') == int(i):
            timeline_receipt = timeline_plan.get('execution_receipt')
            legacy_plan = 'fps' not in timeline_plan and not timeline_receipt
            exact_new_plan = (isinstance(timeline_receipt, dict) and
                              timeline_receipt.get('prompt_id') == receipt.get('prompt_id') and
                              timeline_receipt.get('project_id') == receipt.get('project_id') and
                              timeline_receipt.get('group_id') == receipt.get('group_id') and
                              timeline_receipt.get('execution_version') == receipt.get('execution_version') and
                              timeline_receipt.get('source_sha256', '').lower() ==
                              str(timeline_plan.get('source_sha256', '')).lower())
            if legacy_plan or exact_new_plan:
                inherited_timeline[str(i)] = copy.deepcopy(timeline_plan)
        retained.extend(e for e in index.get('segments', []) if int(e['segment_index']) == int(i))
    enabled = receipts.get('_native_merge', {}).get('auto_merge_enabled', True)
    inherited['_native_merge'] = {'auto_merge_enabled': enabled, 'active_group_id': binding['group_id'],
                                  'groups': {binding['group_id']: {'eligible': enabled,
                                  'prompt_ids': {i: r['prompt_id'] for i, r in inherited.items() if i.isdigit()},
                                  'merge_status': 'WAITING_6_OF_6' if enabled else 'DISABLED',
                                  'merge_prompt_id': None, 'merge_output': None}}}
    # A fork inherits trim evidence only for the exact retained segment assets.
    # Do not copy trims from outputs invalidated or omitted by this execution.
    retained_indices = {int(s['segment_index']) for s in retained}
    retained_trims = [e for e in index.get('trim_events', [])
                      if int(e['segment_index']) in retained_indices]
    p.atomic_json(new / 'index.json', {**index, 'project_id': binding['project_id'],
                                    'segments': retained, 'trim_events': retained_trims})
    p.atomic_json(new / 'six_acceptance.json', inherited)
    if inherited_timeline:
        p.atomic_json(new / 'long_song_timeline.json', inherited_timeline)
    p.atomic_json(p.ledger_path(binding), data)
    return binding, data
