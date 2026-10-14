import copy
import unittest
from unittest.mock import patch
from _v28_bootstrap import load, fresh_env

MC=load("v28_manual_continuation")
F=load("v28_h3_format")
P=load("v28_paths")
PJ=load("v28_project")
PR=load("v28_prompt_resolution")
OR=load("v28_orchestrator")
SM=load("v28_state_machine")
V=load("v28_provider")
G=load("v28_gemma_runtime")

BASE="""subject_definitions:
<Subject 1> is the woman in <Picture 1>, wearing glasses and a blue coat.
<Subject 2> is the man in <Picture 2>.

summary:
[reference generation] The woman sits on a sofa in a quiet room.

retention_analysis:
<Subject 1>: fully_preserved - identity, clothing and hairstyle.
<Subject 2>: fully_preserved - identity.

detailed_description:
[Shot 1] The woman sits on the sofa. The man stands near the door.
Lighting is warm. The blue coat and glasses remain unchanged.

overall_soundscape:
Quiet room tone.

non_diegetic_music:
N/A"""

def inputs():
    return [BASE,"女人从沙发走到窗边，回头问男人为什么还不离开。","她转身继续说话。","男人走到门边。","女人看向男人。","女人停在窗边。"]

def clocks():
    return [{"segment_index":i+1,"start_time":i*10,"end_time":(i+1)*10} for i in range(6)]

def compiler():
    return MC.ManualContinuationCompiler(BASE,[{"ui_slot":1,"h3_picture":1},{"ui_slot":2,"h3_picture":2}])

class TestManualContinuation(unittest.TestCase):
    def test_missing_structural_markers_completed_without_semantic_rewrite(self):
        raw=BASE.replace('[Shot 1] ','').replace('The man stands near the door.', 'The man stands near the door. She says in Mandarin: <Subject 1> (S1) <d>你为什么还不离开？</d>')
        completed=MC.ManualContinuationCompiler(raw,[{'ui_slot':1,'h3_picture':1},{'ui_slot':2,'h3_picture':2}]).base
        self.assertEqual(F.audit_prompt(completed),[])
        self.assertEqual(completed.replace('\n[Shot 1]','').replace('[Mandarin]',''),raw)
        draft=inputs();draft[0]=raw
        self.assertEqual(MC.ManualContinuationCompiler(raw,[{'ui_slot':1,'h3_picture':1},{'ui_slot':2,'h3_picture':2}]).compile(draft,clocks())[0][0],completed)
    def test_language_tags_preserved_and_unknown_language_not_guessed(self):
        raw=BASE+'\n<d>[Cantonese]原文对白</d>'
        self.assertEqual(F.complete_base_format(raw),raw)
        with self.assertRaisesRegex(ValueError,'语言说明'):F.complete_base_format(BASE+'\n<d>Bonjour.</d>')
    def test_chinese_dialogue_only_gets_language_marker(self):
        raw=BASE+'\n<d>女人问：为什么？男人说：等你。</d>'
        with self.assertRaisesRegex(ValueError,'语言说明'):F.complete_base_format(raw)
    def test_explicit_final_position_wins_in_source_order(self):
        base=BASE.replace("The woman sits on the sofa.", "The woman sits on the sofa. The woman stands at the window.")
        c=MC.ManualContinuationCompiler(base,[{"ui_slot":1,"h3_picture":1},{"ui_slot":2,"h3_picture":2}])
        draft=inputs();draft[0]=base
        self.assertIn("<Subject 1> at the window", c.compile(draft,clocks())[0][1])

    def test_negated_camera_is_not_positive_override(self):
        draft=inputs();draft[1]="这一段不要固定镜头，女人走到窗边。"
        text=compiler().compile(draft,clocks())[0][1]
        self.assertIn(draft[1], text)
        self.assertNotIn("Camera: Static camera", text)

    def test_T01_official_structure(self):
        texts,states=compiler().compile(inputs(),clocks())
        self.assertEqual(texts[0],BASE)
        self.assertEqual(tuple(F.parse_sections(texts[1])),F.SECTIONS)
        self.assertIn(inputs()[1],texts[1])
        self.assertIn("[00:00-00:10.000]",texts[1])
        self.assertNotEqual(texts[1],BASE)
        self.assertNotIn("The woman sits on the sofa",texts[2])

    def test_T02_no_director_calls(self):
        with fresh_env(),patch.object(V,"get_provider",side_effect=AssertionError("Director")),patch.object(G,"start",side_effect=AssertionError("8092 start")),patch.object(G,"api",side_effect=AssertionError("8092 request")):
            PJ.create(project_id="continuation",title="test")
            OR.manual_now(project_id="continuation",manual_prompts=inputs(),manual_mode=PR.MANUAL_CONTINUATION,images=[{"slot_index":1},{"slot_index":2}])
            instruction=OR.prepare_segment("continuation")
            self.assertEqual(instruction["prompt"],BASE)

    def test_T03_verbatim_actions_relationship_dialogue(self):
        samples=["女人走到窗边。","男人猛然转身，女人朝左跑，二人关系保持不变。","女人问：‘为什么还不离开？’ 男人回答：‘我在等你。’"]
        for sample in samples:
            draft=inputs();draft[1]=sample
            text=compiler().compile(draft,clocks())[0][1]
            self.assertIn(sample,text)

    def test_T04_no_sensitive_or_intensity_replacement(self):
        for sample in ["突然，瞬间，猛然，急停，一下子。","暴怒、恐惧、痛苦：全部保留。","suddenly instantly abruptly nsfw violent sensitive"]:
            draft=inputs();draft[1]=sample
            self.assertIn(sample,compiler().compile(draft,clocks())[0][1])

    def test_T05_local_camera(self):
        draft=inputs();draft[1]="这一段固定镜头。女人走到窗边。"
        texts,states=compiler().compile(draft,clocks())
        self.assertIn("Static camera for this segment",texts[1])
        self.assertNotIn("Static camera for this segment",texts[2])

    def test_T06_persistent_camera(self):
        for prefix in ["从现在开始都", "之后一直", "后面都", "从这一段开始一直"]:
            draft=inputs();draft[1]=prefix+"固定机位。"
            texts,states=compiler().compile(draft,clocks())
            self.assertIn("Static camera for this segment",texts[5])

    def test_T07_accepted_endpoint(self):
        texts,states=compiler().compile(inputs(),clocks())
        ledger={"entries":[dict(states[0],accepted=True),dict(states[1],accepted=True)]}
        after=compiler().compile(inputs(),clocks(),ledger)
        self.assertEqual(after[1][2]["start_state"]["position"]["<Subject 1>"],"窗边")
        self.assertIn("<Subject 1> at 窗边",after[0][2])
        bad=inputs();bad[1]="女人离开窗边。"
        with self.assertRaises(ValueError):compiler().compile(bad,clocks(),ledger)

    def test_T08_preview_submission_identity(self):
        C=load("v28_director_core")
        for text in compiler().compile(inputs(),clocks())[0]:
            bundle=C.canonical_prompt_bundle(text,path="MANUAL_CONTINUATION")
            self.assertEqual(bundle["UI_PREVIEW"],bundle["SUBMISSION_PROMPT"])
            self.assertEqual(bundle["PREVIEW_SHA256"],bundle["SUBMISSION_PROMPT_SHA256"])

    def test_T09_full_manual_unchanged(self):
        with fresh_env():
            PJ.create(project_id="full",title="test")
            texts=[BASE+f"\nExact bytes {i}  " for i in range(6)]
            OR.manual_now(project_id="full",manual_prompts=texts,manual_mode=PR.MANUAL_FULL,images=[{'slot_index':1},{'slot_index':2}])
            self.assertEqual([x["final_prompt"] for x in PR.execution_segments("full")],texts)

    def test_T10_director_current_path(self):
        from test_v28_optional_director import director,semantic,args
        with fresh_env():
            PJ.create(project_id="director",title="test")
            result,provider=director("director",[{"segments":[semantic(i) for i in range(1,7)]}])
            self.assertEqual(result["director_status"],"COMMITTED")
            self.assertEqual(provider.starts,1)
            self.assertEqual(provider.stops,1)

    def test_ledger_written_only_on_accept(self):
        with fresh_env():
            PJ.create(project_id="ledger",title="test")
            OR.manual_now(project_id="ledger",manual_prompts=inputs(),manual_mode=PR.MANUAL_CONTINUATION,images=[{"slot_index":1},{"slot_index":2}])
            self.assertFalse(PJ.read("ledger",MC.LEDGER_FILE))
            st=SM.load_state("ledger");st["status"]="CANDIDATE_READY";st["current_candidate"]={"segment_id":1,"video":"fixture.mp4","seed":123}
            SM.save_state("ledger",st)
            slot=PJ.mc_slot_path(1);slot.parent.mkdir(parents=True,exist_ok=True);slot.write_bytes(b"mock latent")
            with patch.object(PJ,"record_clip"):
                SM.accept("ledger")
            self.assertTrue(PJ.read("ledger",MC.LEDGER_FILE)["entries"][0]["accepted"])

    def test_ambiguous_duplicate_sections_rejected(self):
        with self.assertRaises(ValueError):MC.ManualContinuationCompiler(BASE+"\nsummary:\nx",[])

    def test_completed_dialogue_is_not_replayed_in_next_segment(self):
        draft=inputs();draft[1]='女人说："只在这一段说一次。"';draft[2]='她继续看着男人。'
        texts,states=compiler().compile(draft,clocks())
        self.assertNotIn('只在这一段说一次',texts[2])
        self.assertEqual(states[1]["end_state"]["dialogue_events"],['只在这一段说一次。'])

    def test_duplicate_character_aliases_are_not_guessed(self):
        base=BASE.replace('<Subject 2> is the man','<Subject 2> is the woman')
        compiled=MC.ManualContinuationCompiler(base,[{"ui_slot":1,"h3_picture":1},{"ui_slot":2,"h3_picture":2}])
        self.assertNotIn("女人",compiled.aliases)

    def test_registered_prompt_adapter_preserves_all_bytes(self):
        import ast
        source=(P.V28_PKG_DIR.parent/"h3_workflow_helpers/nodes.py").read_text(encoding="utf-8")
        nodes=[n for n in ast.parse(source).body if isinstance(n,ast.ClassDef) and n.name=="H3VideoPromptRole"]
        scope={"_VIDEO_USAGE_MOTION_REF":"动作/镜头参考","H3_VIDEO_USAGE_OPTIONS":["动作/镜头参考","直接编辑源视频"]}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),str(P.V28_PKG_DIR),"exec"),scope)
        original="  突然，瞬间，nsfw。\n<Audio 1> <Video 1> <Picture 1>  "
        result=scope["H3VideoPromptRole"]().apply(original,picture_refs_enabled=False,audio1_enabled=False,video_refs_enabled=True)
        self.assertEqual(result[0],original)

    def test_audio_preflight_preserves_prompt_and_pcm(self):
        import ast
        import torch
        source=(P.V28_PKG_DIR.parent/"H3_Audio8Step/nodes.py").read_text(encoding="utf-8")
        nodes=[n for n in ast.parse(source).body if isinstance(n,ast.ClassDef)]
        scope={"torch":torch}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),str(P.V28_PKG_DIR),"exec"),scope)
        pcm={"waveform":torch.zeros((1,1,16000)),"sample_rate":8000}
        original="原文突然。<Audio 1> remains unchanged."
        result=scope["H3Audio8ReferencePreflight"]().check(original,audio3_enabled=True,role3="Do not append this",audio3=pcm)
        self.assertEqual(result[-1],original)
        self.assertIs(result[2],pcm)
