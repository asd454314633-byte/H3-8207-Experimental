"""One business implementation shared by migration HTTP and Comfy routes."""
from pathlib import Path
from director_engine import Director, DirectorError, ROOT
from director_groups import SixSegmentDirector

PREFIX = '/api/h3-director'

class DirectorCore:
    def __init__(self, director=None):
        self.director = director or Director()
        self.groups = SixSegmentDirector(self.director)

    def activity(self):
        idle = self.director.lock.acquire(blocking=False)
        if idle:self.director.lock.release()
        return {'busy':not idle or self.director.provider.get_status().get('busy',False)}

    def dispatch(self, method, path, payload=None):
        # Old routes are only a transport mapping during offline migration tests.
        path = path.removeprefix(PREFIX).removeprefix('/director')
        provider = self.director.provider
        if method == 'GET':
            if path in ('/status','/local-backend','/health'):return provider.get_status()
            if path == '/activity':return self.activity()
            if path == '/models':return provider.models()
            if path == '/preferences':return provider.preferences()
            if path == '/state':return self.director.state()
            if path == '/groups/latest':return self.groups.latest()
        elif method == 'POST':
            if not isinstance(payload,dict):raise DirectorError('需要JSON对象')
            if path == '/preferences':return provider.select_model(payload.get('selected_model'))
            if path in ('/model/warm','/model/start'):return provider.warm_model(str(payload.get('model_key','')))
            if path in ('/planner/generate','/groups/generate'):return self.groups.generate(payload)
            if path in ('/generate','/continue','/refine'):return self.director.generate(payload,path.rsplit('/',1)[1])
            if path == '/confirm':return self.director.confirm(payload)
            if path == '/new-story':return self.director.new_story()
            if path == '/groups/save':return self.groups.save(payload)
            if path == '/groups/confirm':return self.groups.confirm(payload)
        raise DirectorError('NOT_FOUND')

    @staticmethod
    def asset(path):
        names={'/director':'director.html','/six':'six.html','/six_ui.js':'six_ui.js'}
        if path not in names:raise DirectorError('NOT_FOUND')
        name=names[path]
        return (ROOT/name).read_bytes(), ('text/javascript' if name.endswith('.js') else 'text/html')
