"""Reference admission regression: pure graph, real JS protocol and HTTP middleware.

No model is loaded and no ComfyUI queue is used. The test HTTP server echoes
the body observed by the downstream handler, proving the native-route contract.
"""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch
from _v28_bootstrap import load, fresh_env, PKG_DIR
from test_v282_manual_continuation import BASE, inputs
from test_v28_optional_director import Replies, semantic

RH=load('v28_reference_hygiene')
PR=load('v28_prompt_resolution')
OR=load('v28_orchestrator')
PJ=load('v28_project')
SM=load('v28_state_machine')
V=load('v28_provider')
C=load('v28_director_core')

def mapping(n=3):
    return C.active_reference_map(list(range(1,n+1)))

def graph(text='<Picture 1> 女人 <Picture 3> 男人。<Audio 1> <Video 1> 瞬间转身。'):
    return {'138':{'class_type':'PrimitiveStringMultiline','inputs':{'value':text}},
        '915':{'class_type':'H3VideoPromptRole','inputs':{'base_prompt':['138',0]}},
        '1042':{'class_type':'H3Audio8ReferencePreflight','inputs':{'prompt':['915',0],'audio1':['900',0]}},
        '136':{'class_type':'MiniMaxH3ReferenceToVideo','inputs':{'prompt':['1042',8],
             **{f'ref_images.ref_image_{i}':[str(687+i),0] for i in range(3)},
             'ref_audio':['1042',0],'ref_video':['800',0],'width':608,'height':1056}},
        '900':{'class_type':'AudioFixture','inputs':{}},'800':{'class_type':'VideoFixture','inputs':{}}}

def images(n=3):return [{'index':i,'slot_index':i,'filename':f'fixture{i}.png'} for i in range(1,n+1)]

class TestReferenceText(unittest.TestCase):
    def check(self,n,used):
        R=load('v28_reference_contract')
        original=' '.join(f'<Picture {i}> 角色身份{i}强烈动作；' for i in used)+' 朝左走，关系及对白不变。'
        rows=R.decisions(original,list(range(1,n+1)))
        contract={'active_reference_index':R.active_map(rows),'canonical_prompt':R.render_reference_tokens(original,rows)}
        self.assertEqual([r['ui_slot'] for r in contract['active_reference_index']],used)
        self.assertEqual(contract['canonical_prompt'],' '.join(f'<Picture {j}> 角色身份{i}强烈动作；' for j,i in enumerate(used,1))+' 朝左走，关系及对白不变。')
    def test_all_have_roles(self):self.check(3,[1,2,3])
    def test_drop_middle(self):self.check(3,[1,3])
    def test_drop_first(self):self.check(3,[2,3])
    def test_drop_last(self):self.check(3,[1,2])
    def test_drop_two(self):self.check(4,[2,4])
    def test_only_one(self):self.check(4,[4])
    def test_none(self):self.check(4,[])
    def test_one_pass_no_cascade(self):self.check(4,[1,3,4])
    def test_dangling_is_error_not_exclusion(self):
        with self.assertRaises(ValueError):load('v28_reference_contract').draft('<Picture 4>',mapping(),mode='MANUAL_FULL',segment_id=1,duration=10)
    def test_role_slots_explicit_only(self):
        R=load('v28_reference_contract')
        self.assertEqual([r['source_slot_id'] for r in R.decisions('图1身份；图3服装',[1,2,3]) if r['decision']=='INCLUDE'],[1,3])
        self.assertEqual([r['source_slot_id'] for r in R.decisions('人物走到窗边，没有指定参考',[1,2,3]) if r['decision']=='INCLUDE'],[])
    def test_legacy_label_spacing_case_and_other_bytes_preserved(self):
        R=load('v28_reference_contract');original=' < picture 3 > 作为服装参考\n'
        canonical=R.render_reference_tokens(original,R.decisions(original,[1,2,3]))
        self.assertEqual(canonical,' < picture 1 > 作为服装参考\n')

class TestReferenceModes(unittest.TestCase):
    def test_full_manual_missing_markers_stays_byte_identical(self):
        with fresh_env():
            PJ.create(project_id='full_raw',title='fixture')
            raw=BASE.replace('[reference generation] ','').replace('[Shot 1] ','')
            with self.assertRaisesRegex(ValueError,'OFFICIAL_H3_FORMAT_INVALID'):
                OR.manual_now(project_id='full_raw',manual_prompts=[raw]*6,images=images(2))
    def test_full_manual_byte_difference_is_only_picture_renumber(self):
        with fresh_env(),patch.object(V,'get_provider',side_effect=AssertionError('Director')):
            PJ.create(project_id='full',title='fixture');raw=BASE.replace('<Picture 2>','<Picture 3>')
            OR.manual_now(project_id='full',manual_prompts=[raw]*6,images=images())
            for segment in PR.execution_segments('full'):
                self.assertEqual(segment['final_prompt'],BASE)
                self.assertEqual([r['ui_slot'] for r in segment['reference_mapping']],[1,3])
            instr=OR.prepare_segment('full')
            self.assertEqual(instr['prompt'],PR.final_prompt('full',1))
    def test_continuation_preserves_delta_and_source_domain(self):
        with fresh_env(),patch.object(V,'get_provider',side_effect=AssertionError('Director')):
            PJ.create(project_id='simple',title='fixture');draft=inputs();draft[0]=BASE.replace('<Picture 2>','<Picture 3>')
            OR.manual_now(project_id='simple',manual_prompts=draft,manual_mode=PR.MANUAL_CONTINUATION,images=images())
            for segment in PR.execution_segments('simple'):
                self.assertEqual([r['ui_slot'] for r in segment['reference_mapping']],[1,3])
            self.assertIn(draft[1],PR.final_prompt('simple',2))
            self.assertEqual(PJ.read('simple',PR.MANUAL_FILE)['prompts'],draft)
    def test_accept_ledger_retains_source_labels_and_freezes_submitted_canonical(self):
        with fresh_env():
            MC=load('v28_manual_continuation')
            PJ.create(project_id='accepted_map',title='fixture');draft=inputs();draft[0]=BASE.replace('<Picture 2>','<Picture 3>')
            OR.manual_now(project_id='accepted_map',manual_prompts=draft,manual_mode=PR.MANUAL_CONTINUATION,images=images())
            state=SM.load_state('accepted_map');state['status']='CANDIDATE_READY';state['current_candidate']={'segment_id':1,'video':'fixture.mp4','seed':123}
            SM.save_state('accepted_map',state)
            slot=PJ.mc_slot_path(1);slot.parent.mkdir(parents=True,exist_ok=True);slot.write_bytes(b'fixture latent')
            with patch.object(PJ,'record_clip'):SM.accept('accepted_map')
            ledger=PJ.read('accepted_map',MC.LEDGER_FILE)['entries'][0]
            self.assertEqual(ledger['reference_contract']['active_reference_index'][1]['ui_slot'],3)
            self.assertEqual(ledger['canonical_prompt'],BASE)
            draft[2]='她从窗边走向门边。'
            OR.manual_now(project_id='accepted_map',manual_prompts=draft)
            self.assertEqual(PR.final_prompt('accepted_map',1),BASE)
            self.assertEqual(PR.execution_segments('accepted_map')[1]['reference_mapping'][1]['ui_slot'],3)
    def test_full_advanced_edit_retains_original_slot(self):
        with fresh_env():
            PJ.create(project_id='edit',title='fixture');raw=BASE.replace('<Picture 2>','<Picture 3>')
            OR.manual_now(project_id='edit',manual_prompts=[raw]*6,images=images())
            edit=BASE+'\n朝左走，瞬间转身。'
            OR.edit_and_recompile('edit',segment_id=2,prompt=edit)
            self.assertEqual(PR.final_prompt('edit',2),edit)
            self.assertEqual([r['ui_slot'] for r in PR.execution_segments('edit')[1]['reference_mapping']],[1,3])
            self.assertEqual(PR.final_prompt('edit',1),BASE)
    def test_old_cache_normalized_on_read_and_replay(self):
        with fresh_env():
            PJ.create(project_id='cache',title='fixture')
            legacy=[{'segment_id':1,'start_time':0,'end_time':10,'final_prompt':'<Picture 1> 女 <Picture 3> 男','reference_mapping':mapping(),'generation_parameters':{}}]
            PJ.write('cache',PR.RESOLVED_FILE,legacy)
            with self.assertRaisesRegex(ValueError,'REFERENCE_RECOMPILE_REQUIRED'):PR.execution_segments('cache')
    def test_director_filters_before_provider_and_manual_switch_restores_connected(self):
        with fresh_env():
            PJ.create(project_id='director',title='fixture');provider=Replies([{'segments':[semantic(i) for i in range(1,7)]}])
            with patch.object(V,'get_provider',return_value=provider),patch.object(OR,'_stop_and_confirm',side_effect=lambda p,n:(p.stop() or {'verdict':'RELEASED'})),patch.object(SM,'_gate',return_value=(True,'',{})):
                result=OR.plan_now(project_id='director',prompt_source=PR.DIRECTOR,story_goal='人物在房间里走动',reference_usage='图1为人物身份，图3为男人身份',images=images(),total_seconds=60,segment_seconds=10)
            self.assertEqual(result['director_status'],'COMMITTED')
            planner=PJ.read('director','REFERENCE_PROFILE.json')['director_input']
            self.assertEqual([r['ui_slot'] for r in planner['ACTIVE_REFERENCE_MAP']],[1,2,3])
            self.assertEqual(len(planner['CONNECTED_REFERENCE_MAP']),3)
            self.assertEqual(provider.starts,1)
            OR.manual_now(project_id='director',manual_prompts=[BASE.replace('<Picture 2>','<Picture 3>')]*6)
            self.assertEqual([r['ui_slot'] for r in PR.execution_segments('director')[0]['reference_mapping']],[1,3])

