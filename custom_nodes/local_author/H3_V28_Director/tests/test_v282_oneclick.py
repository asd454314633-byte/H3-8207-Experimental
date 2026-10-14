import copy
import unittest
from unittest.mock import patch
import test_v282_reference_contract as T
from test_v282_reference_contract import context, graph, prompt, R, OR, PJ, PR, V


class OneClickGates(unittest.TestCase):
    setUp = T.Gates.setUp
    tearDown = T.Gates.tearDown

    def test_expired_receipt_is_rejected_and_run_renews_it(self):
        with patch.object(R.time, 'time', return_value=1000):
            old = self.server.compile_graph(graph(), context())
            self.assertEqual(old, self.server.compile_graph(graph(), context()))
        with patch.object(R.time, 'time', return_value=1901):
            with self.assertRaisesRegex(ValueError, '签名已过期'):
                self.server.verify_graph(old['graph'], context())
            new = self.server.compile_graph(graph(), context())
            self.assertNotEqual(old['receipts'][0]['signature'], new['receipts'][0]['signature'])
            self.assertEqual(self.server.verify_graph(new['graph'], context()), new['graph'])

    def test_full_manual_run_without_preview_or_director_and_changed_prompt(self):
        PJ.create(project_id='oneclick', title='neutral')
        images = [{'slot_index':s,'filename':f'neutral{s}.png'} for s in range(1,5)]
        with patch.object(V, 'get_provider', side_effect=AssertionError('manual called Director')):
            OR.plan_now(project_id='oneclick', prompt_source=PR.MANUAL,
                manual_mode=PR.MANUAL_FULL, manual_prompts=[prompt()]*6, images=images)
            instr = OR.prepare_segment('oneclick', seed=123)
            out = self.server.compile_graph(graph(instr['prompt']), context('oneclick'))
            self.assertEqual(self.server.verify_graph(out['graph'], context('oneclick')), out['graph'])
            changed = prompt().replace('walks to the window', 'stands by the window')
            OR.plan_now(project_id='oneclick', prompt_source=PR.MANUAL,
                manual_mode=PR.MANUAL_FULL, manual_prompts=[changed]*6, images=images)
            instr2 = OR.prepare_segment('oneclick', seed=123)
            out2 = self.server.compile_graph(graph(instr2['prompt']), context('oneclick',revision=2))
            self.assertIn('stands by the window', out2['graph']['138']['inputs']['value'])
            with self.assertRaisesRegex(ValueError,'H3_REFERENCE_RECEIPT_INVALID'):
                self.server.verify_graph(out['graph'], context('oneclick'))

    def test_stale_tab_cannot_mutate_the_newer_project(self):
        PJ.create(project_id='tabs', title='neutral')
        old = PJ.revision('tabs')
        OR.plan_now(project_id='tabs', prompt_source=PR.MANUAL,
            project_revision=old, manual_mode=PR.MANUAL_FULL,
            manual_prompts=[prompt(())]*6, images=[])
        newer = PJ.core_snapshot('tabs')
        with self.assertRaisesRegex(ValueError, 'PROJECT_STATE_STALE'):
            OR.plan_now(project_id='tabs', prompt_source=PR.MANUAL,
                project_revision=old, manual_mode=PR.MANUAL_FULL,
                manual_prompts=[prompt(())+' changed']*6, images=[])
        self.assertEqual(PJ.core_snapshot('tabs'), newer)

    def test_explicit_reference_selection_replaces_inherited_set(self):
        inherited = R.decisions('图1作为人物参考；图3作为场景参考', [1,2,3,4])
        rows = R.decisions('图4作为人物参考', [1,2,3,4], inherited=inherited)
        self.assertEqual([r['ui_slot'] for r in R.active_map(rows)], [4])
        self.assertEqual(R.active_map(R.decisions('无图片', [1,2,3,4], inherited=inherited)), [])


if __name__ == '__main__': unittest.main()
