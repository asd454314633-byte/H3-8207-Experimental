import importlib.util
import pathlib
import unittest


MODULE = pathlib.Path(__file__).parents[1] / 'custom_nodes' / 'local_author' / 'H3_LongSong' / 'timeline_contract.py'
SPEC = importlib.util.spec_from_file_location('h3_timeline_contract_under_test', MODULE)
TIMELINE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TIMELINE)


def chain(cross_group=None, clean_rebase_index=None):
    result = {}
    output = (cross_group['global_boundary'] if cross_group else 0.0)
    for index in range(6):
        frames = 175
        prefix = 39 if (cross_group and index == 0) or (index and index != clean_rebase_index) else 0
        discard = 39 if index == clean_rebase_index else 0
        kept = frames - prefix - discard
        source_start = output - (prefix + discard) / 24
        plan = {'segment_index': index, 'origin_index': 0, 'fps': 24,
                'source_sha256': 'a' * 64, 'song_start': 0.0, 'frames': frames,
                'prefix_frames': prefix, 'output_discard_frames': discard,
                'kept_frames': kept, 'source_start': source_start,
                'source_end': source_start + frames / 24,
                'output_start': output, 'output_end': output + kept / 24}
        if cross_group:
            plan['cross_group'] = cross_group
            plan['group_start_seconds'] = cross_group['global_boundary']
        result[str(index)] = plan
        output = plan['output_end']
    return result


class LongSongTimelineContractTests(unittest.TestCase):
    def test_complete_six_segment_chain(self):
        checked = TIMELINE.validate_plan_chain(chain(), 5, 'a' * 64, 0.0,
                                              require_from_zero=True)
        self.assertEqual(checked['through_index'], 5)
        self.assertEqual(checked['origin_index'], 0)

    def test_clean_rebase_discard_is_included_in_source_offset(self):
        checked = TIMELINE.validate_plan_chain(chain(clean_rebase_index=3), 5,
                                              'a' * 64, 0.0,
                                              require_from_zero=True)
        self.assertEqual(checked['through_index'], 5)

    def test_cross_group_boundary_is_exact(self):
        cross = {'global_boundary': 82.375, 'source_project': 'older-project'}
        checked = TIMELINE.validate_plan_chain(chain(cross), 5, 'a' * 64, 0.0,
                                              cross, require_from_zero=True)
        self.assertEqual(checked['through_index'], 5)

    def test_missing_segment_is_rejected(self):
        timeline = chain()
        del timeline['3']
        with self.assertRaisesRegex(ValueError, '缺少第4段'):
            TIMELINE.validate_plan_chain(timeline, 5, 'a' * 64, 0.0,
                                         require_from_zero=True)

    def test_wrong_song_identity_is_rejected(self):
        with self.assertRaisesRegex(ValueError, '原曲SHA256'):
            TIMELINE.validate_plan_chain(chain(), 5, 'b' * 64, 0.0,
                                         require_from_zero=True)

    def test_discontinuous_boundary_is_rejected(self):
        timeline = chain()
        timeline['4']['output_start'] += 0.5
        timeline['4']['output_end'] += 0.5
        timeline['4']['source_start'] += 0.5
        timeline['4']['source_end'] += 0.5
        timeline['5']['output_start'] += 0.5
        timeline['5']['output_end'] += 0.5
        timeline['5']['source_start'] += 0.5
        timeline['5']['source_end'] += 0.5
        with self.assertRaisesRegex(ValueError, '不连续'):
            TIMELINE.validate_plan_chain(timeline, 5, 'a' * 64, 0.0,
                                         require_from_zero=True)

    def test_long_song_group_cannot_submit_without_planner_node(self):
        with self.assertRaisesRegex(ValueError, '必须且只能提交'):
            TIMELINE.validate_graph_identity({}, 'execution-1', 'H3_SONG_1', 0)

    def test_planner_node_must_match_execution_and_real_frame_input(self):
        graph = {'136': {'class_type': 'MiniMaxH3ReferenceToVideo',
                         'inputs': {'length': ['PrimitiveInt1', 0]}},
                 'LONG_SONG': {'class_type': 'H3LongSongSegment', 'inputs': {
                     'project_id': 'execution-1', 'segment_index': 0,
                     'fps': 24, 'source': 'song.wav', 'start_seconds': 0,
                     'frames': ['PrimitiveInt1', 0]}}}
        checked = TIMELINE.validate_graph_identity(graph, 'execution-1', 'H3_SONG_1', 0)
        self.assertEqual(checked['project_id'], 'execution-1')
        graph['LONG_SONG']['inputs']['frames'] = 175
        with self.assertRaisesRegex(ValueError, '帧数未绑定'):
            TIMELINE.validate_graph_identity(graph, 'execution-1', 'H3_SONG_1', 0)

    def test_latest_unverified_completion_blocks_older_verified_fallback(self):
        verified = [(100.0, {'source_project': 'older-82s'})]
        invalid = [(200.0, 'newest', 's6-prompt', 'missing timeline')]
        blocker = TIMELINE.blocking_unverified_candidate(verified, invalid)
        self.assertEqual(blocker[1], 'newest')

    def test_older_unverified_attempt_does_not_block_newer_verified_one(self):
        verified = [(200.0, {'source_project': 'current-latest'})]
        invalid = [(100.0, 'old-incomplete', 'prompt', 'missing timeline')]
        self.assertIsNone(TIMELINE.blocking_unverified_candidate(verified, invalid))


if __name__ == '__main__':
    unittest.main()
