"""Prompt-only contracts; temporary projects, no provider, GPU, queue or package init."""
import ast
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from _v28_bootstrap import load, fresh_env

C = load('v28_director_core')
tree = ast.parse(Path(__file__).with_name('test_v28_gate6b_core.py').read_text(encoding='utf-8'))
scope = {}
exec(compile(ast.Module(body=[next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == '_plan')], type_ignores=[]), '<neutral fixture>', 'exec'), scope)


def fixture():
    planner = C.planner_input(active_slots=[1, 3], reference_usage='图1参考身份；图3仅参考动作感觉，不作为首帧。',
        constraints='图3禁止复制身份和服装。保持背景不变。', story_goal='Complete the declared motion.',
        total_seconds=10, segment_seconds=10,
        planner_controls={'backend': 'pdd8', 'steps': 8, 'seed': 42, 'resolution': '1344x768',
                          'cache_id': 'fixture', 'slot_id': 3, 'first_frame_enabled': False,
                          'dialogue_density': '正常', 'allow_polish': False})
    plan = C.validate_director_plan(scope['_plan'](), planner)
    plan.update(version=1, story_goal=planner['story_goal'], global_state={'director_contract': 'GATE6C_STRUCTURED'},
                references={'picture_count': 2, 'picture_indices': [1, 2]}, style='auto', continuation_mode='same_shot', warnings=[])
    for seg in plan['segments']:
        seg['reference_usage']=['图1参考身份','图3仅参考动作感觉，不作为首帧']
        seg.update(beat='执行声明动作', directives={}, locked=False, seed=None)
    for key in set(plan) - {'version', 'story_goal', 'global_state', 'references', 'segments', 'style', 'continuation_mode', 'director', 'generated_from', 'warnings'}:
        plan.pop(key)
    profile = {'version': 1, 'source_pictures': [{'index': i, 'filename': f'{i}.png', 'width': 0, 'height': 0} for i in [1, 2]],
               'subjects': [], 'scene': {'user_text_only': True}, 'props': [], 'composition': {},
               'uncertain': [], 'not_answerable': [], 'director_input': planner}
    return planner, plan, profile


class PromptContract(unittest.TestCase):
    def test_sparse_map_and_semantic_constraints(self):
        p, plan, profile = fixture()
        self.assertEqual(p['ACTIVE_REFERENCE_MAP'], [{'ui_slot': 1, 'h3_picture': 1}, {'ui_slot': 3, 'h3_picture': 2}])
        b = C.compile_h3_prompt(planner=p, plan=plan, segment_id=1)
        self.assertIn('<Picture 2>禁止复制身份和服装。保持背景不变。', b['CANONICAL_H3_PROMPT'])
        self.assertIn('<Picture 2>仅参考动作感觉，不作为首帧', b['CANONICAL_H3_PROMPT'])
        self.assertEqual(b['UI_PREVIEW'], b['SUBMISSION_PROMPT'])
        self.assertEqual(load('v28_h3_format').audit_prompt(b['CANONICAL_H3_PROMPT']), [])

    def test_frozen_159_mapping(self):
        self.assertEqual(C.active_reference_map([9, 1, 5]), [{'ui_slot': 1, 'h3_picture': 1}, {'ui_slot': 5, 'h3_picture': 2}, {'ui_slot': 9, 'h3_picture': 3}])

    def test_negation_precedes_keyword(self):
        for text in ['图1不作为首帧', '不要把图1当首帧', '图1不是首帧', '图1仅作身份参考，不做首帧']:
            with self.subTest(text=text):
                r = C.compile_reference_text(text, C.active_reference_map([1]))
                self.assertFalse(r['reference_relationships'][0]['first_frame'])
                self.assertFalse(r['reference_relationships'][0]['keyframe_anchor'])
                self.assertEqual(r['REFERENCE_TIMELINE'], 'NONE')
        for text in ['图1作为首帧', '图1用作首帧']:
            self.assertTrue(C.compile_reference_text(text, C.active_reference_map([1]))['reference_relationships'][0]['first_frame'])

    def test_controls_do_not_enter_prompt(self):
        p, plan, _ = fixture()
        text = C.compile_h3_prompt(planner=p, plan=plan, segment_id=1)['CANONICAL_H3_PROMPT']
        for token in ['backend=', 'steps=', 'seed=', 'resolution=', 'cache', 'slot_id', 'first_frame_enabled', 'DIALOGUE_DENSITY', 'ALLOW_POLISH']:
            self.assertNotIn(token, text)
        for key in ['backend', 'steps', 'seed', 'resolution', 'cache_id', 'slot_id', 'first_frame_enabled']:
            with self.subTest(key=key):
                bad = copy.deepcopy(p); bad['user_constraints'] = f'{key}=1'
                with self.assertRaises(C.DirectorCompileError):
                    C.compile_h3_prompt(planner=bad, plan=plan, segment_id=1)

    def test_unuploaded_reference_refused(self):
        p, plan, _ = fixture(); p['user_constraints'] = '图9参考背景'
        with self.assertRaisesRegex(C.DirectorCompileError, 'REFERENCE_SLOT_MISSING'):
            C.compile_h3_prompt(planner=p, plan=plan, segment_id=1)

    def test_edit_cache_restore_and_submission_share_compiler(self):
        with fresh_env() as (m, root):
            p, plan, profile = fixture(); pj = m['v28_project']; sm = m['v28_state_machine']; o = load('v28_orchestrator')
            pid = 'backport_contract'; pj.create('Prompt control fixture', project_id=pid)
            initial = o._compile_segment(plan, 1, profile)['CANONICAL_H3_PROMPT']
            plan['segments'][0].update(prompt=initial, start_state={'text': plan['segments'][0]['start_state']}, end_state={'text': plan['segments'][0]['end_state']})
            pj.write(pid, 'REFERENCE_PROFILE.json', profile); sm.set_plan(pid, plan)
            with patch.object(m['v28_h3_format'], 'render', side_effect=AssertionError('manual renderer entered Director path')):
                self.assertEqual(o.segment_prompt(pid, 1), initial)
                o.edit_and_recompile(pid, segment_id=1, prompt=initial)
                self.assertEqual(o.segment_prompt(pid, 1), initial)
                cache = pj.project_dir(pid) / 'prompts/seg_001_compiled.txt'; cache.unlink()
                self.assertEqual(o.segment_prompt(pid, 1), initial)
                cache.write_text('stale old compiler text', encoding='utf-8')
                self.assertEqual(o.segment_prompt(pid, 1), initial)
                o.edit_and_recompile(pid, segment_id=1, prompt='The subject raises one hand slowly.')
                edited = o.segment_prompt(pid, 1)
                self.assertIn('The subject raises one hand slowly.', edited)
                self.assertIn('<Picture 2>禁止复制身份和服装', edited)
                cache.unlink(); self.assertEqual(o.segment_prompt(pid, 1), edited)
                instr = sm.widget_instructions(pid, seed=42)
                self.assertEqual(instr['prompt'], edited)
                before = pj.read(pid, 'STORY_PLAN.json')
                with self.assertRaises(C.DirectorCompileError):
                    o.edit_and_recompile(pid, segment_id=1, prompt='backend=pdd8')
                self.assertEqual(pj.read(pid, 'STORY_PLAN.json'), before)
                envelope_edit = edited.replace('then lowers it.', 'then lowers it.') if 'then lowers it.' in edited else edited.replace('one hand slowly.', 'one hand slowly, then lowers it.')
                o.edit_and_recompile(pid, segment_id=1, prompt=envelope_edit)
                envelope_result = o.segment_prompt(pid, 1)
                self.assertIn('then lowers it.', envelope_result)
                self.assertIn('<Picture 2>禁止复制身份和服装', envelope_result)
                cache.unlink(); self.assertEqual(o.segment_prompt(pid, 1), envelope_result)
                self.assertEqual(sm.widget_instructions(pid, seed=42)['prompt'], envelope_result)
                before = pj.read(pid, 'STORY_PLAN.json')
                with self.assertRaises(load('v28_provider').DirectorError):
                    o.edit_and_recompile(pid, segment_id=1, prompt=envelope_result.replace('Complete the declared motion.', 'A different story.'))
                self.assertEqual(pj.read(pid, 'STORY_PLAN.json'), before)

    def test_legacy_metadata_migration_no_old_compiler(self):
        _, plan, profile = fixture(); o = load('v28_orchestrator')
        profile['director_input']['user_constraints'] = 'DIALOGUE_DENSITY=正常; ALLOW_POLISH=OFF; 图3不得换服装'
        b = o._compile_segment(plan, 1, profile)
        self.assertNotIn('DIALOGUE_DENSITY', b['CANONICAL_H3_PROMPT'])
        self.assertIn('<Picture 2>不得换服装', b['CANONICAL_H3_PROMPT'])
        self.assertIn('DIALOGUE_DENSITY', profile['director_input']['user_constraints'])

    def test_missing_planner_refuses_instead_of_fallback(self):
        _, plan, _ = fixture()
        with self.assertRaisesRegex(load('v28_provider').DirectorError, '不会回退旧编译器'):
            load('v28_orchestrator')._compile_segment(plan, 1, {})


if __name__ == '__main__':
    unittest.main(verbosity=2)
