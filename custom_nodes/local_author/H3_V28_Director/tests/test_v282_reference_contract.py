"""Contract gates G1-G11. Actual production Python/JS; no model or GPU."""
import copy
import json
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
from _v28_bootstrap import load,fresh_env,PKG_DIR
from test_v28_optional_director import semantic
R=load('v28_reference_contract');H=load('v28_reference_hygiene');F=load('v28_h3_format')
C=load('v28_director_core');PR=load('v28_prompt_resolution');OR=load('v28_orchestrator');PJ=load('v28_project')
MC=load('v28_manual_continuation');V=load('v28_provider')

def prompt(slots=(1,3)):
    defs='\n'.join(f'<Subject {s}> is the woman in <Picture {s}>.' for s in slots) or 'N/A'
    retention='\n'.join(f'<Subject {s}>: fully_preserved - identity.' for s in slots) or 'N/A'
    return f'subject_definitions:\n{defs}\n\nsummary:\n[reference generation] A neutral person walks.\n\nretention_analysis:\n{retention}\n\ndetailed_description:\n[Shot 1] A neutral person walks to the window.\n\noverall_soundscape:\nRoom tone.\n\nnon_diegetic_music:\nN/A'

def graph(text=None,slots=(1,2,3,4)):
    g={'138':{'class_type':'PrimitiveStringMultiline','inputs':{'value':text or prompt()}},
       '136':{'class_type':'MiniMaxH3ReferenceToVideo','inputs':{'prompt':['138',0],**{f'ref_images.ref_image_{s-1}':[str(686+s),0] for s in slots}}}}
    for s in slots:g[str(686+s)]={'class_type':'LoadImageCrop','inputs':{'image':f'neutral{s}.png','crop':'disabled'}}
    return g

def context(pid='fixture',mode='MANUAL_FULL',sid=1,revision=1,epoch='A'):
    return {'project_id':pid,'workflow_id':'workflow_fixture','segment_id':sid,'generation_mode':mode,'workflow_revision':revision,'edit_epoch':epoch}

class Gates(unittest.TestCase):
    def setUp(self):
        self.env=fresh_env();self.mods,self.root=self.env.__enter__()
        input_dir=self.mods['v28_paths'].COMFY_ROOT/'input';input_dir.mkdir(parents=True,exist_ok=True)
        for s in range(1,5):(input_dir/f'neutral{s}.png').write_bytes(f'neutral file contents {s}'.encode())
        self.server=R.ReferenceContractV2()
    def tearDown(self):self.env.__exit__(None,None,None)
    def test_G1_variants_positive_negative_conflict_unmentioned(self):
        for token in ('图2','图片2','第2张','第2张图','槽位2','Slot 2','slot  2','Picture 2','<Picture 2>','<Picture  2>','< picture 2 >','第 2 张图'):
            with self.subTest(token=token):
                self.assertEqual(R.decisions(token+'作为服装参考',[1,2,3])[1]['decision'],'INCLUDE')
                self.assertEqual(R.decisions('不要使用'+token,[1,2,3])[1]['decision'],'EXCLUDE')
                with self.assertRaisesRegex(ValueError,'REFERENCE_ROLE_CONFLICT'):R.decisions(token+'作为服装参考；但不要使用'+token,[1,2,3])
        for text in ('图2不要参与','排除图2','不用图2','忽略图2','图2仅作为反例','Picture 2 is not a reference','do not use Picture 2','ignore Picture 2','exclude Picture 2'):
            self.assertEqual(R.decisions(text,[2])[0]['decision'],'EXCLUDE')
        self.assertEqual(R.decisions('人物走到窗边',[1,2])[0]['decision'],'UNMENTIONED')
        with self.assertRaisesRegex(ValueError,'REFERENCE_ROLE_CONFLICT'):R.decisions('<Picture 2>',[2])
    def test_G2_all_three_modes_segment_contract_edges(self):
        sets=[(1,3),(1,),(4,),(3,),(1,4),()]
        images=[{'index':s,'slot_index':s,'filename':f'neutral{s}.png'} for s in range(1,5)]
        for mode in ('MANUAL_FULL','MANUAL_CONTINUATION','DIRECTOR'):
            pid='segments_'+mode;PJ.create(project_id=pid,title='neutral')
            if mode!='DIRECTOR':
                texts=[prompt(x) for x in sets] if mode=='MANUAL_FULL' else [prompt(sets[0]),'这一段仅使用图1，女人向左走。','这一段仅使用图4，人物停下。','这一段仅使用图3，人物转身。','这一段仅使用图1、图4作为参考，人物继续行走。','这一段不使用任何参考，人物停下。']
                with patch.object(V,'get_provider',side_effect=AssertionError('manual called Director')):
                    OR.manual_now(project_id=pid,manual_prompts=texts,manual_mode=mode,images=images)
                segs=PR.execution_segments(pid)
                if mode=='MANUAL_CONTINUATION':
                    for i in range(1,6):self.assertIn(texts[i],segs[i]['final_prompt'])
            else:
                planner=C.planner_input(active_slots=[1,2,3,4],reference_usage='图1身份；图3人物；图4场景',story_goal='Neutral walk',total_seconds=60,segment_seconds=10)
                plan=C.validate_director_plan({'segments':[dict(semantic(i),reference_usage=('；'.join(f'图{s}作为人物参考' for s in ss) or 'none')) for i,ss in enumerate(sets,1)]},planner)
                bundles=[C.compile_h3_prompt(planner=planner,plan=plan,segment_id=i) for i in range(1,7)]
                segs=PR.resolve(plan,planner,prompts=[b['CANONICAL_H3_PROMPT'] for b in bundles],contracts=[b['REFERENCE_CONTRACT'] for b in bundles],generation_mode=mode)
                PJ.write(pid,PR.RESOLVED_FILE,segs)
            for i,(seg,ss) in enumerate(zip(segs,sets),1):
                with self.subTest(mode=mode,segment=i):
                    self.assertEqual([r['ui_slot'] for r in seg['reference_contract']['active_reference_index']],list(ss))
                    out=self.server.compile_graph(graph(seg['final_prompt']),context(pid,mode,i))
                    self.assertEqual(out['graph']['138']['inputs']['value'],seg['final_prompt'])
                    actual=[v[0] for k,v in out['graph']['136']['inputs'].items() if R.SOCKET.fullmatch(k)]
                    self.assertEqual(actual,[str(686+s) for s in ss])
    def test_G3_idempotence_one_two_five_and_repeated_compile(self):
        first=self.server.compile_graph(graph(),context())
        result=copy.deepcopy(first['graph'])
        for _ in range(5):self.assertEqual(self.server.verify_graph(result,context()),result)
        self.assertEqual(self.server.compile_graph(graph(),context()),first)
        with patch.object(R,'SERVER',self.server):
            for _ in range(5):self.assertEqual(H.sanitize_graph(result,context())['graph'],result)
    def test_G4_mutations_reject_old_receipt(self):
        first=self.server.compile_graph(graph(),context())['graph']
        changes={
            'prompt':lambda g:g['138']['inputs'].__setitem__('value',g['138']['inputs']['value']+' Changed.'),
            'edge':lambda g:g['136']['inputs'].__setitem__('ref_images.ref_image_1',['688',0]),
            'node':lambda g:g.__setitem__('689',{'class_type':'Other','inputs':{'image':'neutral3.png'}}),
            'filename':lambda g:g['689']['inputs'].__setitem__('image','neutral2.png'),
            'remove':lambda g:g['136']['inputs'].__delitem__('ref_images.ref_image_1'),
            'add':lambda g:g['136']['inputs'].__setitem__('ref_images.ref_image_8',['688',0]),
        }
        for name,mutate in changes.items():
            g=copy.deepcopy(first);mutate(g)
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'H3_REFERENCE_RECEIPT_INVALID'):self.server.verify_graph(g,context())
        for field,value in (('generation_mode','DIRECTOR'),('workflow_id','other'),('project_id','other'),('segment_id',2),('workflow_revision',2),('edit_epoch','undo')):
            ctx=context();ctx[field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'H3_REFERENCE_RECEIPT_INVALID'):self.server.verify_graph(first,ctx)
        p=self.mods['v28_paths'].COMFY_ROOT/'input'/'neutral3.png';p.write_bytes(b'new bytes with same filename')
        with self.assertRaisesRegex(ValueError,'H3_REFERENCE_RECEIPT_INVALID'):self.server.verify_graph(first,context())
    def test_G5_signature_and_contract_forgery_rejected(self):
        base=self.server.compile_graph(graph(),context())['graph']
        for key in ('source_references','active_reference_index','prompt_picture_label','canonical_prompt_sha256','compile_revision','graph_reference_edges_digest','reference_decisions'):
            g=copy.deepcopy(base);g['136']['_meta']['h3_reference_receipt_v2']['reference_contract'][key]='forged'
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'H3_REFERENCE_RECEIPT_INVALID'):self.server.verify_graph(g,context())
        g=copy.deepcopy(base);g['136']['_meta']['h3_reference_receipt_v2']['signature']='00'*32
        with self.assertRaisesRegex(ValueError,'H3_REFERENCE_RECEIPT_INVALID'):self.server.verify_graph(g,context())
    def test_G7_second_tab_invalidates_old_compilation(self):
        a=self.server.compile_graph(graph(),context())
        b=self.server.compile_graph(graph(),context(revision=2,epoch='B'))
        self.assertGreater(b['receipts'][0]['reference_contract']['compile_revision'],a['receipts'][0]['reference_contract']['compile_revision'])
        with self.assertRaisesRegex(ValueError,'旧编译revision'):self.server.verify_graph(a['graph'],context())
        self.assertEqual(self.server.verify_graph(b['graph'],context(revision=2,epoch='B')),b['graph'])
    def test_G9_reload_and_server_restart_distrust_saved_receipt(self):
        out=self.server.compile_graph(graph(),context())['graph'];saved=json.loads(json.dumps(out))
        self.assertEqual(saved,out)
        with self.assertRaisesRegex(ValueError,'H3_REFERENCE_RECEIPT_INVALID'):self.server.verify_graph(saved,context(epoch='reload'))
        with self.assertRaisesRegex(ValueError,'H3_REFERENCE_RECEIPT_INVALID'):R.ReferenceContractV2().verify_graph(saved,context())
    def test_G10_legacy_migration_domains(self):
        with patch.object(R,'SERVER',self.server):
            self.assertTrue(H.sanitize_graph(graph())['receipts'])
            with self.assertRaisesRegex(ValueError,'LEGACY_REFERENCE_AMBIGUOUS'):H.sanitize_graph(graph(prompt((2,)),slots=(2,3)))
        pid='trusted';PJ.create(project_id=pid,title='neutral')
        planner=C.planner_input(active_slots=[1,3],reference_usage='',story_goal='neutral',total_seconds=60,segment_seconds=10)
        segs=PR.resolve({},planner,prompts=[prompt((1,3))]*6)
        PJ.write(pid,PR.RESOLVED_FILE,segs)
        self.assertTrue(self.server.compile_graph(graph(segs[0]['final_prompt'],slots=(1,3)),context(pid))['receipts'])
    def test_G11_official_validator_matrix(self):
        base=prompt();self.assertEqual(F.audit_prompt(base),[])
        invalid={
          'illegal_task':base.replace('[reference generation]','[made up]'),
          'duplicate_task':base.replace('[reference generation]','[reference generation + reference generation]'),
          'retention':base.replace('fully_preserved','fully_copy'),
          'shot_gap':base.replace('A neutral person walks to the window.','[Shot 3] At 00:01.000, A person walks.'),
          'shot_time_missing':base.replace('Room tone.','Room tone.').replace('A neutral person walks to the window.','[Shot 2] A person walks.'),
          'first_timestamp':base.replace('[Shot 1]','[Shot 1] At 00:00.000,'),
          'backwards':base.replace('A neutral person walks to the window.','[Shot 2] At 00:08.000, wait. [Shot 3] At 00:02.000, turn.'),
          'over_duration':base.replace('A neutral person walks to the window.','[Shot 2] At 00:11.000, wait.'),
          'speaker':base.replace('A neutral person walks to the window.','<Subject 1> says <d>[English] Hello.</d>'),
          'speaker_drift':base.replace('A neutral person walks to the window.','<Subject 1> (S1) says <d>[English] Hello.</d> <Subject 1> (S2) says <d>[English] Bye.</d>'),
          'language':base.replace('A neutral person walks to the window.','<Subject 1> (S1) says <d>Hello.</d>'),
          'fake_language':base.replace('A neutral person walks to the window.','<Subject 1> (S1) says <d>[Shot 3] Hello.</d>'),
          'picture':base.replace('Room tone.','<Picture 99> room.'),
          'audio':base.replace('Room tone.','<Audio 99> room.'),
          'video':base.replace('Room tone.','<Video 99> room.'),
        }
        for name,text in invalid.items():
            with self.subTest(name=name):self.assertTrue(F.audit_prompt(text,duration_seconds=10))
        with self.assertRaisesRegex(ValueError,'TASK_TYPE_AMBIGUOUS'):F.complete_base_format(base.replace('[reference generation]',''))
        words='女人向左走，严厉地问：“为什么不离开？”'
        self.assertEqual(words,words);self.assertTrue(F.VALIDATOR.warnings(words))
    def test_G6_G8_G9_actual_JS_race_and_restoration(self):
        node=shutil.which('node');self.assertIsNotNone(node)
        helper=PKG_DIR.parent/'h3_workflow_helpers'/'web'/'h3_workflow_registry_core.js'
        import base64
        uri='data:text/javascript;base64,'+base64.b64encode(helper.read_bytes()).decode()
        script='''const H=await import(URI); const assert=(await import('node:assert/strict')).default;
const n={id:'138',mode:0,widgets:[{name:'value',value:'old'}],properties:{}};
const g={_nodes:[n],links:[],extra:{h3_reference_context:{workflow_revision:1}},getNodeById:()=>n};
let release;globalThis.fetch=()=>new Promise(r=>release=()=>r({ok:true,json:async()=>({graph:{},receipts:[]})}));
const p=H.compileReferenceGraph({},g,g.extra.h3_reference_context);n.widgets[0].value='new input';release();
await assert.rejects(p,/内容已在编译期间修改/);assert.equal(n.widgets[0].value,'new input');
const duration={id:'132',mode:0,widgets:[{name:'value',value:10}],properties:{}};g._nodes.push(duration);
const pending=H.compileReferenceGraph({},g,g.extra.h3_reference_context);duration.widgets[0].value=8;release();
await assert.rejects(pending,/内容已在编译期间修改/);assert.equal(duration.widgets[0].value,8);
n.properties.h3_reference_receipt_v2={signature:'old'};n.properties.h3_reference_hygiene={old:true};
H.initializeReferenceWorkflow(g);assert.equal(n.properties.h3_reference_receipt_v2,undefined);
const old=g.extra.h3_reference_context.edit_epoch;H.initializeReferenceWorkflow(g);assert.notEqual(old,g.extra.h3_reference_context.edit_epoch);
const rev=g.extra.h3_reference_context.workflow_revision;g.onAfterChange();assert.equal(g.extra.h3_reference_context.workflow_revision,rev+1);
console.log('G6 race preserved; restore distrust; change revision PASS');'''.replace('URI',json.dumps(uri))
        result=subprocess.run([node,'--input-type=module','-e',script],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

class MiddlewareGate(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_receipt_cannot_reach_handler_or_submitted(self):
        from aiohttp import web
        from aiohttp.test_utils import TestClient,TestServer
        seen=[]
        async def native(request):seen.append(await request.json());return web.json_response({'prompt_id':'accepted_fixture'})
        app=web.Application(middlewares=[H.request_middleware()]);app.router.add_post('/prompt',native)
        client=TestClient(TestServer(app));await client.start_server()
        try:
            r=await client.post('/prompt',json={'prompt':graph(),'extra_data':{'extra_pnginfo':{'workflow':{'nodes':[]}}}})
            self.assertEqual(r.status,400);self.assertEqual(seen,[])
        finally:await client.close()

class AdditionalContractGates(unittest.TestCase):
    setUp=Gates.setUp
    tearDown=Gates.tearDown
    def test_shared_source_multiple_conditions_is_not_reinterpreted(self):
        g=graph();g['137']=copy.deepcopy(g['136'])
        out=self.server.compile_graph(g,context())['graph']
        self.assertEqual(out['136']['inputs'],out['137']['inputs'])
        self.assertEqual(self.server.verify_graph(out,context()),out)
    def auxiliary(self):
        g=graph();g['900']={'class_type':'LoadAudio','inputs':{'audio':'fixture.wav'}}
        g['800']={'class_type':'LoadVideo','inputs':{'video':'fixture.mp4'}}
        inp=self.mods['v28_paths'].COMFY_ROOT/'input'
        (inp/'fixture.wav').write_bytes(b'audio bytes');(inp/'fixture.mp4').write_bytes(b'video bytes')
        g['136']['inputs'].update(ref_audio=['900',0],ref_video=['800',0])
        return g
    def test_audio_video_edges_unchanged_and_bound(self):
        g=self.auxiliary();out=self.server.compile_graph(g,context())['graph']
        for key in ('ref_audio','ref_video','prompt'):self.assertEqual(out['136']['inputs'][key],g['136']['inputs'][key])
        self.assertEqual(len(out['136']['_meta']['h3_reference_receipt_v2']['reference_contract']['auxiliary_sources']),2)
        self.assertEqual(self.server.verify_graph(out,context()),out)
    def test_auxiliary_edge_mutation_not_hidden_by_raw_compaction(self):
        g=self.auxiliary();receipt=self.server.compile_graph(g,context())['receipts'][0]
        g['136']['_meta']={'h3_reference_receipt_v2':receipt};g['138']['inputs']['value']=receipt['reference_contract']['canonical_prompt']
        g['136']['inputs']['ref_audio']=['800',0]
        with self.assertRaisesRegex(ValueError,'H3_REFERENCE_RECEIPT_INVALID'):self.server.verify_graph(g,context(),raw=True)
    def test_same_filename_audio_content_invalidates_receipt(self):
        g=self.server.compile_graph(self.auxiliary(),context())['graph']
        (self.mods['v28_paths'].COMFY_ROOT/'input/fixture.wav').write_bytes(b'changed audio bytes')
        with self.assertRaisesRegex(ValueError,'H3_REFERENCE_RECEIPT_INVALID'):self.server.verify_graph(g,context())
    def test_same_filename_video_content_invalidates_receipt(self):
        g=self.server.compile_graph(self.auxiliary(),context())['graph']
        (self.mods['v28_paths'].COMFY_ROOT/'input/fixture.mp4').write_bytes(b'changed video bytes')
        with self.assertRaisesRegex(ValueError,'H3_REFERENCE_RECEIPT_INVALID'):self.server.verify_graph(g,context())
    def test_unknown_prompt_source_is_never_guessed(self):
        g=graph();g['138']['class_type']='UnknownRewriter'
        with self.assertRaises(ValueError):self.server.compile_graph(g,context())
    def test_real_dynamic_audio_video_socket_families_are_content_bound(self):
        g=self.auxiliary();g['136']['inputs']['ref_audios.ref_audio_0']=g['136']['inputs'].pop('ref_audio')
        g['136']['inputs']['ref_videos.ref_video_0']=g['136']['inputs'].pop('ref_video')
        out=self.server.compile_graph(g,context())['graph'];c=out['136']['_meta']['h3_reference_receipt_v2']['reference_contract']
        self.assertIn('ref_audios.ref_audio_0',c['graph_reference_edges']);self.assertEqual(c['media_labels'],{'Audio':[1],'Video':[1]})
        out['136']['inputs']['ref_audios.ref_audio_0']=['800',0]
        with self.assertRaisesRegex(ValueError,'H3_REFERENCE_RECEIPT_INVALID'):self.server.verify_graph(out,context())
    def test_actual_browser_JSON_number_roundtrip_preserves_signature(self):
        signed=self.server.compile_graph(graph(),context())['graph']
        node=shutil.which('node');self.assertTrue(node)
        result=subprocess.run([node,'-e','let s="";process.stdin.on("data",x=>s+=x);process.stdin.on("end",()=>process.stdout.write(JSON.stringify(JSON.parse(s))));'],input=json.dumps(signed),capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.server.verify_graph(json.loads(result.stdout),context()),signed)
    def test_sparse_legacy_unique_source_and_unique_dense_migrate(self):
        for text,slots in ((prompt((3,)),(1,3)),(prompt((2,)),(1,3))):
            out=self.server.compile_graph(graph(text,slots=slots),context(epoch=text))
            self.assertEqual(out['graph']['136']['inputs']['ref_images.ref_image_0'],['689',0])
            self.assertEqual(self.server.verify_graph(out['graph'],context(epoch=text)),out['graph'])
    def test_actual_segment_duration_and_frame_derivation_are_bound(self):
        g=graph();g['132']={'class_type':'PrimitiveFloat','inputs':{'value':10.0}};g['131']={'class_type':'ComfyMathExpression','inputs':{'expression':'a * 24','values.a':['132',0]}}
        out=self.server.compile_graph(g,context())['graph'];out['132']['inputs']['value']=8
        with self.assertRaisesRegex(ValueError,'H3_REFERENCE_RECEIPT_INVALID'):self.server.verify_graph(out,context())
        out=self.server.compile_graph(g,context())['graph'];out['131']['inputs']['expression']='a * 48'
        with self.assertRaisesRegex(ValueError,'H3_REFERENCE_RECEIPT_INVALID'):self.server.verify_graph(out,context())
    def test_missing_format_task_not_guessed_for_full_manual(self):
        with self.assertRaisesRegex(ValueError,'OFFICIAL_H3_FORMAT_INVALID'):self.server.compile_graph(graph(prompt().replace('[reference generation]','')),context())
    def test_role_modifiers_and_temporal_negation_are_not_dropped(self):
        rows=R.decisions('图3仅参考动作感觉，不作为首帧',[3])
        self.assertIn('不作为首帧',rows[0]['role_text']);self.assertEqual(rows[0]['decision'],'INCLUDE')
        self.assertEqual(R.decisions('不要把图3当首帧',[3])[0]['decision'],'INCLUDE')

class QueueAcceptanceGate(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, status):
        from aiohttp import web
        from aiohttp.test_utils import TestClient,TestServer
        with fresh_env() as (mods,root):
            inp=mods['v28_paths'].COMFY_ROOT/'input';inp.mkdir(parents=True,exist_ok=True)
            for s in range(1,5):(inp/f'neutral{s}.png').write_bytes(f'fixture {s}'.encode())
            pid='queue_acceptance';PJ.create(project_id=pid,title='fixture')
            OR.manual_now(project_id=pid,manual_prompts=[prompt()]*6,images=[{'slot_index':s,'filename':f'neutral{s}.png'} for s in range(1,5)])
            OR.prepare_segment(pid)
            server=R.ReferenceContractV2();ctx=context(pid)
            signed=server.compile_graph(graph(PR.final_prompt(pid,1)),ctx)['graph']
            seen=[]
            async def native(request):
                seen.append(PJ.read(pid,'SESSION_STATE.json')['status'])
                return web.json_response({'prompt_id':'native-accepted-fixture'} if status==200 else {'error':'native graph rejected'},status=status)
            app=web.Application(middlewares=[H.request_middleware()]);app.router.add_post('/prompt',native)
            client=TestClient(TestServer(app));await client.start_server()
            try:
                with patch.object(R,'SERVER',server):
                    response=await client.post('/prompt',json={'prompt':signed,'extra_data':{'extra_pnginfo':{'workflow':{'extra':{'h3_reference_context':ctx}}}}})
                self.assertEqual(response.status,status);self.assertEqual(seen,['READY'])
                return PJ.read(pid,'SESSION_STATE.json')['status'],server.accepted(pid,'native-accepted-fixture')
            finally:await client.close()
    async def test_native_acceptance_precedes_submitted(self):
        state,receipt=await self.exercise(200);self.assertEqual(state,'GENERATING');self.assertIsNotNone(receipt)
    async def test_native_rejection_does_not_mark_submitted(self):
        state,receipt=await self.exercise(400);self.assertEqual(state,'READY');self.assertIsNone(receipt)

