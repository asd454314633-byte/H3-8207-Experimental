from _v28_bootstrap import load
import ast
from pathlib import Path
import unittest

# Reuse the neutral plan fixture without requiring pytest in the production venv.
tree = ast.parse(Path(__file__).with_name('test_v28_gate6b_core.py').read_text(encoding='utf-8'))
exec(compile(ast.Module(body=[next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_plan')], type_ignores=[]), '<plan fixture>', 'exec'))

C = load('v28_director_core')

def test_constraints_survive_even_when_planner_does_not_repeat_them():
    p = C.planner_input(active_slots=[1, 3, 4],
        reference_usage='图1只提供身份；图3只提供起始姿态；图4只提供结束姿态。',
        constraints='不改身份、不改服装、不改背景。图4禁止复制身份和服装。',
        story_goal='Complete a continuous start-to-end posture transition.',
        total_seconds=10, segment_seconds=10)
    b = C.compile_h3_prompt(planner=p, plan={'segments':[dict(_plan()['segments'][0],reference_usage=['图1提供身份','图3提供起始姿态','图4提供结束姿态'])]}, segment_id=1)
    text = b['CANONICAL_H3_PROMPT']
    assert '不改身份、不改服装、不改背景。' in text
    assert '<Picture 3>禁止复制身份和服装。' in text
    assert '图4' not in text
    assert text == b['UI_PREVIEW'] == b['SUBMISSION_PROMPT']

def test_constraints_cannot_silently_reference_an_unloaded_slot():
    p = C.planner_input(active_slots=[1, 3, 4], reference_usage='图1参考身份',
        constraints='图9只提供场景。', story_goal='A continuous transition.',
        total_seconds=10, segment_seconds=10)
    with unittest.TestCase().assertRaisesRegex(C.DirectorCompileError, 'REFERENCE_SLOT_MISSING'):
        C.compile_h3_prompt(planner=p, plan=_plan(), segment_id=1)

if __name__ == '__main__':
    suite = unittest.TestSuite(unittest.FunctionTestCase(f) for f in [test_constraints_survive_even_when_planner_does_not_repeat_them, test_constraints_cannot_silently_reference_an_unloaded_slot])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
