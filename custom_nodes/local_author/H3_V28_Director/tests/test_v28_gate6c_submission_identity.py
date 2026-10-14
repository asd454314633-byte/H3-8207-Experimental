import pathlib
import sys
from unittest.mock import patch
sys.path.insert(0, pathlib.Path(__file__).resolve().parent.as_posix())
import _v28_bootstrap as B
from test_v282_prompt_control_backport import fixture


def test_gate6c_submits_plan_time_canonical_prompt_without_legacy_recompile():
    with B.fresh_env() as (m, _root):
        pj, sm = m['v28_project'], m['v28_state_machine']
        core, orchestrator = B.load('v28_director_core'), B.load('v28_orchestrator')
        planner, plan, profile = fixture()
        bundle = core.compile_h3_prompt(planner=planner, plan=plan, segment_id=1)
        prompt = bundle['CANONICAL_H3_PROMPT']
        plan['segments'][0]['prompt'] = prompt
        for key in ['start_state', 'end_state']:
            plan['segments'][0][key] = {'text': plan['segments'][0][key]}
        pid = 'gate6c_identity'
        pj.create(project_id=pid, title='identity')
        pj.write(pid, 'REFERENCE_PROFILE.json', profile)
        sm.set_plan(pid, plan)
        pr=B.load("v28_prompt_resolution")
        pj.write(pid,pr.RESOLVED_FILE,pr.resolve(plan,planner,prompts=[prompt],contracts=[bundle["REFERENCE_CONTRACT"]],generation_mode=pr.DIRECTOR))
        with patch.object(m['v28_h3_format'], 'render', side_effect=AssertionError('manual renderer entered Director path')):
            instruction = sm.widget_instructions(pid)
            assert instruction['prompt'] == prompt
            assert '<Picture 2>禁止复制身份和服装' in instruction['prompt']
            assert 'visual reference only' not in instruction['prompt']
            # Resolved-segment execution may never create this optional cache.
            pj.project_dir(pid).joinpath('prompts/seg_001_compiled.txt').unlink(missing_ok=True)
            assert orchestrator.segment_prompt(pid, 1) == prompt
