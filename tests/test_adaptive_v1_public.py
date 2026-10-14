"""Synthetic, CPU-only checks of the exact published Adaptive V1 core.

No private fixtures and no ComfyUI/model imports. These are not GPU acceptance.
"""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'public_adaptive_v1',
    ROOT/'custom_nodes/local_author/h3_conditioning_prebake/adaptive_v1/core.py')
import sys
core = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = core
spec.loader.exec_module(core)


class PublicAdaptiveChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root/'clip.mp4').write_bytes(b'synthetic-output-identity-only')
        self.meta = core.Metadata({
            'SyntheticVideo': {'input': {'required': {'fps': ['FLOAT'], 'seed': ['INT']}}, 'output': ['VIDEO']},
            'UserVideoWriter': {'input': {'required': {'video': ['VIDEO'], 'filename_prefix': ['STRING']}}, 'output': [], 'output_node': True},
        })
        self.graph = {
            'source': {'class_type': 'SyntheticVideo', 'inputs': {'fps': 24, 'seed': 1}},
            'writer': {'class_type': 'UserVideoWriter', 'inputs': {'video': ['source', 0], 'filename_prefix': 'example'}},
        }
        self.pid = 'synthetic-task'
        self.receipt = {'prompt_id': self.pid, 'video_sha256': core.file_sha(self.root/'clip.mp4')}
        self.snapshot = core.TaskSnapshot.create(self.pid, self.graph, self.meta, self.receipt)
        self.history = {'prompt': [0, self.pid, copy.deepcopy(self.graph)], 'status': {'completed': True, 'status_str': 'success', 'messages': []}, 'outputs': {'writer': {'videos': [{'filename': 'clip.mp4', 'subfolder': '', 'type': 'output'}]}}}
        self.engine = core.RecoveryEngine()
        self.resolver = core.AssetResolver({'output': self.root})

    def tearDown(self):
        self.temp.cleanup()

    def test_numeric_representation(self):
        graph = copy.deepcopy(self.graph)
        graph['source']['inputs']['fps'] = 24.0
        self.assertEqual(core.analyze(graph, self.meta).semantic_version, self.snapshot.semantic_version)

    def test_node_ids_and_layout(self):
        graph = {'88': copy.deepcopy(self.graph['source']), '99': copy.deepcopy(self.graph['writer'])}
        graph['99']['inputs']['video'] = ['88', 0]
        graph['88']['pos'] = [500, 800]
        self.assertEqual(core.analyze(graph, self.meta).semantic_version, self.snapshot.semantic_version)

    def test_original_output_with_changed_canvas(self):
        graph = copy.deepcopy(self.graph)
        graph['source']['inputs']['seed'] = 2
        self.assertNotEqual(core.analyze(graph, self.meta).semantic_version, self.snapshot.semantic_version)
        result = self.engine.recover(self.snapshot, self.history, self.resolver, current_graph=graph)
        self.assertEqual(result['output_status'], 'RECOVERED')
        self.assertEqual(result['prompt_id'], self.pid)

    def test_missing_continuation_keeps_output(self):
        result = self.engine.recover(self.snapshot, self.history, self.resolver, current_graph={})
        self.assertEqual(result['output_status'], 'RECOVERED')
        self.assertEqual(result['continuation']['status'], 'UNAVAILABLE')
        self.assertTrue(result['continuation']['preserve_completed_output'])

    def test_wrong_history_owner_rejected(self):
        history = copy.deepcopy(self.history)
        history['prompt'][1] = 'different-task'
        self.assertEqual(self.engine.recover(self.snapshot, history, self.resolver)['output_status'], 'NOT_RECOVERED')

    def test_changed_output_rejected(self):
        (self.root/'clip.mp4').write_bytes(b'other-task-output')
        result = self.engine.recover(self.snapshot, self.history, self.resolver)
        self.assertEqual(result['gpu_status'], 'SUCCESS')
        self.assertEqual(result['output_status'], 'NOT_RECOVERED')

    def test_snapshot_integrity(self):
        path = self.snapshot.persist(self.root/'tasks')
        self.assertEqual(core.TaskSnapshot.load(path).semantic_version, self.snapshot.semantic_version)
        value = json.loads(path.read_text(encoding='utf-8'))
        value['graph_json'] = '{}'
        path.write_text(json.dumps(value), encoding='utf-8')
        with self.assertRaises(core.CompatibilityError):
            core.TaskSnapshot.load(path)


if __name__ == '__main__':
    unittest.main()
