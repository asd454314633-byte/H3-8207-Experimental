from .nodes import NODE_CLASS_MAPPINGS
from .recovery import H3RecoveredNativeLatent
NODE_CLASS_MAPPINGS['H3RecoveredNativeLatent']=H3RecoveredNativeLatent
WEB_DIRECTORY = './web'

# Optional one-shot handoff of authentic process-local history on an idle reload.
# Never replaces a current history record and never creates SUCCESS receipts.
from pathlib import Path
_handoff=Path(__file__).with_name('restore_history_once.json')
if _handoff.exists():
    import json
    from server import PromptServer
    _queue=PromptServer.instance.prompt_queue
    with _queue.mutex:
        for _pid,_record in json.loads(_handoff.read_text('utf-8')).items():
            _queue.history.setdefault(_pid,_record)
    _handoff.replace(_handoff.with_suffix('.restored'))

from .recovery import register
register()
from .start_validation import register as register_start_validation
register_start_validation()
from .cross_group import H3CrossGroupPrevious,H3CrossGroupPrefixAudit,register as register_cross_group
NODE_CLASS_MAPPINGS.update({c.__name__:c for c in (H3CrossGroupPrevious,H3CrossGroupPrefixAudit)})
register_cross_group()
