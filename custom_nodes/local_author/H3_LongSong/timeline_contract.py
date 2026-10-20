"""Pure validation for persisted H3 long-song segment timelines."""
import math


def validate_graph_identity(graph, project_id, group_id, segment_index):
    """Check that the submitted graph contains the exact long-song planner."""
    nodes = [node for node in graph.values()
             if node.get('class_type') == 'H3LongSongSegment']
    required = str(group_id or '').startswith('H3_SONG_') or bool(nodes)
    if not required:
        return None
    if len(nodes) != 1:
        raise ValueError('长歌组必须且只能提交一个H3LongSongSegment时间轴节点')
    inputs = nodes[0].get('inputs', {})
    if inputs.get('project_id') != project_id or inputs.get('segment_index') != segment_index:
        raise ValueError('长歌时间轴节点项目身份/段号与PreBake执行不一致')
    if inputs.get('fps') != 24:
        raise ValueError('长歌时间轴节点必须使用原生24fps')
    if not isinstance(inputs.get('source'), str) or not inputs['source'].strip():
        raise ValueError('长歌时间轴节点没有原曲来源')
    try:
        start = float(inputs.get('start_seconds'))
    except (TypeError, ValueError):
        raise ValueError('长歌时间轴节点原曲起点无效') from None
    if not math.isfinite(start) or start < 0:
        raise ValueError('长歌时间轴节点原曲起点无效')
    if '136' not in graph or graph['136'].get('class_type') != 'MiniMaxH3ReferenceToVideo':
        raise ValueError('长歌时间轴节点缺少目标H3生成图')
    if inputs.get('frames') != graph['136'].get('inputs', {}).get('length'):
        raise ValueError('长歌时间轴节点帧数未绑定到实际H3生成帧数')
    return inputs


def blocking_unverified_candidate(verified, invalid):
    """Return a newest unverified same-story completion that forbids fallback."""
    if not invalid:
        return None
    newest_verified = max((item[0] for item in verified), default=0)
    newest_invalid = max(invalid, key=lambda item: item[0])
    return newest_invalid if newest_invalid[0] >= newest_verified else None


def _number(plan, key):
    value = plan.get(key)
    if isinstance(value, bool):
        raise ValueError(f'时间轴字段 {key} 不是数值')
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'时间轴字段 {key} 缺失或无效') from None
    if not math.isfinite(result):
        raise ValueError(f'时间轴字段 {key} 不是有限数值')
    return result


def validate_plan_chain(timeline, through_index, source_sha256=None,
                        song_start=None, expected_cross_group=None,
                        require_from_zero=False):
    """Validate saved plans and their exact frame/time continuity.

    A partial independent segment may start at its recorded ``origin_index``.
    A complete six-segment group must set ``require_from_zero`` so no missing
    prefix can be mistaken for a complete original-song timeline.
    """
    if not isinstance(timeline, dict) or type(through_index) is not int or not 0 <= through_index <= 5:
        raise ValueError('长歌时间轴结构或段号无效')
    current = timeline.get(str(through_index))
    if not isinstance(current, dict):
        raise ValueError(f'缺少第{through_index + 1}段长歌时间轴计划')
    origin = current.get('origin_index', 0)
    if type(origin) is not int or not 0 <= origin <= through_index:
        raise ValueError('长歌时间轴 origin_index 无效')
    if require_from_zero and origin != 0:
        raise ValueError('六段长歌时间轴未从第1段开始')
    first_index = 0 if require_from_zero else origin
    expected_sha = str(source_sha256).lower() if source_sha256 else None
    expected_start = float(song_start) if song_start is not None else None
    expected_cross = expected_cross_group
    previous = None

    for index in range(first_index, through_index + 1):
        plan = timeline.get(str(index))
        if not isinstance(plan, dict):
            raise ValueError(f'长歌时间轴缺少第{index + 1}段')
        if type(plan.get('segment_index')) is not int or plan['segment_index'] != index:
            raise ValueError(f'第{index + 1}段时间轴身份不匹配')
        if plan.get('origin_index', origin) != origin:
            raise ValueError('六段时间轴的 origin_index 不一致')
        fps = _number(plan, 'fps') if 'fps' in plan else 24.0
        if fps != 24.0:
            raise ValueError('长歌时间轴不是原生24fps')
        digest = str(plan.get('source_sha256') or '').lower()
        if not digest or (expected_sha is not None and digest != expected_sha):
            raise ValueError(f'第{index + 1}段原曲SHA256缺失或不匹配')
        start = _number(plan, 'song_start')
        if expected_start is not None and abs(start - expected_start) > 1e-8:
            raise ValueError('六段长歌的原曲起点不一致')
        if expected_start is None:
            expected_start = start

        frames = plan.get('frames')
        if type(frames) is not int or frames < 48 or frames % 17 != 5:
            raise ValueError(f'第{index + 1}段生成帧数无效')
        prefix = plan.get('prefix_frames', 0)
        discard = plan.get('output_discard_frames', 0)
        kept = plan.get('kept_frames')
        if prefix not in (0, 39) or discard not in (0, 39) or (prefix and discard):
            raise ValueError(f'第{index + 1}段前缀/裁剪规则无效')
        if type(kept) is not int or kept != frames - prefix - discard or kept <= 0:
            raise ValueError(f'第{index + 1}段保存帧数与裁剪记录不匹配')

        source_begin = _number(plan, 'source_start')
        source_end = _number(plan, 'source_end')
        output_begin = _number(plan, 'output_start')
        output_end = _number(plan, 'output_end')
        tolerance = 1e-8
        if abs(source_end - source_begin - frames / fps) > tolerance:
            raise ValueError(f'第{index + 1}段原曲区间与模型帧数不匹配')
        if abs(output_end - output_begin - kept / fps) > tolerance:
            raise ValueError(f'第{index + 1}段输出区间与实际保留帧数不匹配')
        if abs(source_begin + (prefix + discard) / fps - output_begin) > tolerance:
            raise ValueError(f'第{index + 1}段39帧前缀/裁剪与时间轴边界不匹配')

        cross = plan.get('cross_group')
        if expected_cross is not None and cross != expected_cross:
            raise ValueError('跨组前驱合同在六段时间轴中不一致')
        if expected_cross is None and index > first_index and cross != (previous or {}).get('cross_group'):
            raise ValueError('六段时间轴的跨组前驱身份不一致')
        if previous is None:
            if cross:
                boundary = _number(cross, 'global_boundary')
                if abs(output_begin - boundary) > tolerance:
                    raise ValueError('跨组第1段输出起点与前驱边界不匹配')
                if abs(_number(plan, 'group_start_seconds') - boundary) > tolerance:
                    raise ValueError('跨组第1段组起点与前驱边界不匹配')
            elif prefix or discard or abs(output_begin - start) > tolerance:
                raise ValueError('独立长歌起点或首段裁剪无效')
        elif abs(output_begin - _number(previous, 'output_end')) > tolerance:
            raise ValueError(f'第{index + 1}段与前段输出时间轴不连续')
        previous = plan
    return {'origin_index': origin, 'through_index': through_index,
            'source_sha256': expected_sha or str(timeline[str(first_index)]['source_sha256']).lower(),
            'song_start': expected_start}
