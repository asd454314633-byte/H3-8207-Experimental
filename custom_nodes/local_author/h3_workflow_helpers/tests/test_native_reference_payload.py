import ast
import types
import unittest
from pathlib import Path

class Image:
    def __init__(self, name, h=1024, w=1024): self.name=name; self.shape=(1,h,w,3)
    def __getitem__(self, key): return self

class NativeReferencePayload(unittest.TestCase):
    def test_all_nine_images_reach_both_qwen_and_vae_in_order(self):
        src=Path(__file__).parents[3]/'comfy_extras/nodes_minimax_h3.py'
        tree=ast.parse(src.read_text(encoding='utf-8'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='MiniMaxH3ReferenceToVideo')
        fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='execute'); fn.decorator_list=[];fn.returns=None
        images=[Image('image-'+str(i),h=1024+i*32,w=768) for i in range(9)]
        seen={}; resized=[];vae_seen=[]
        def resize(image,w,h,crop):
            self.assertEqual(crop,'disabled');resized.append((image.name,w,h));return image
        def tokenize(prompt,**kwargs):seen.update(prompt=prompt,items=kwargs['minimax_ref_items']);return 'tokens'
        def set_values(cond,values):seen['payload']=values;return cond
        scope={'_empty_av_latent':lambda w,h,l:({},l),'math':__import__('math'),'CANVAS_MULTIPLE':32,'REF_IMAGE_SHORT_EDGE':2048,'_resize':resize,'node_helpers':types.SimpleNamespace(conditioning_set_values=set_values),'io':types.SimpleNamespace(NodeOutput=lambda *x:x)}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),str(src),'exec'),scope)
        clip=types.SimpleNamespace(tokenize=tokenize,encode_from_tokens_scheduled=lambda t:['conditioning'])
        vae=types.SimpleNamespace(encode=lambda x:vae_seen.append(x.name) or x.name)
        prompt='<Subject 1> uses <Picture 1> only for identity; <Picture 9> supplies an object.'
        scope['execute'](None,clip,prompt,608,1056,243,vae=vae,ref_images={f'ref_image_{i}':img for i,img in enumerate(images)})
        expected=[i.name for i in images]
        self.assertEqual([x['data'].name for x in seen['items']],expected)
        self.assertEqual(vae_seen,expected)
        self.assertEqual([x['latent'] for x in seen['payload']['minimax_refs']],expected)
        self.assertEqual(seen['prompt'],prompt)
        self.assertEqual(len(resized),9)

if __name__=='__main__':unittest.main()
