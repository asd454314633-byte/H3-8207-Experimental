"""Catalog and dispatch. All local process control belongs to ModelManager."""
import configparser, importlib, json, threading
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from .base import ModelProvider, ProviderError, FallbackableError
from .local_llamacpp import LocalLlamaCppProvider
from .model_manager import H3DirectorModelManager, atomic_json

class RegisteredProvider(ModelProvider):
    name = 'local_llamacpp'
    def __init__(self,config_path):
        self.path=Path(config_path)
        self.config=configparser.ConfigParser(interpolation=None)
        self.config.read(self.path,encoding='utf-8')
        self.default_model=self.config['director']['default_model']
        self.ui_default_model=self.config['director'].get('ui_default_model','').strip() or self.default_model
        self.planner_model=None
        self.registry_path=Path(self.config['director']['model_registry'])
        self.lock=threading.RLock()
        self.selected=self.ui_default_model
        self.preferences_path=self.path.parent/'director_preferences.json'
        if self.preferences_path.exists():
            saved=json.loads(self.preferences_path.read_text(encoding='utf-8')).get('selected_model')
            if saved in self.catalog():self.selected=saved
        self.manager=H3DirectorModelManager(self)

    def catalog(self):
        registry=json.loads(self.registry_path.read_text(encoding='utf-8-sig'));models={}
        for section in self.config.sections():
            if not section.startswith('model.'):continue
            key=section[6:];profile=dict(self.config['local_llamacpp']);profile.update(self.config[section])
            if profile['provider'] not in {'local_llamacpp','openai_compat'}:raise ProviderError('PROVIDER_NOT_ALLOWED')
            item=registry['models'].get(profile.get('registry_key',key))
            if not item and profile['provider']=='local_llamacpp':raise ProviderError('MODEL_NOT_REGISTERED: '+key)
            item=item or profile
            if profile['provider']=='local_llamacpp':
                profile['model']=item['path']
                if profile.get('port')!='8095' or profile.get('parallel')!='1':raise ProviderError('SINGLE_LOCAL_MODEL_CONFIGURATION_REQUIRED')
            profile.setdefault('runtime',str(Path(registry['llama_server']).parent))
            profile.setdefault('alias','h3-prompt-director-'+key);profile.setdefault('label',item['label']);models[key]=profile
        if self.default_model not in models:raise ProviderError('DEFAULT_MODEL_NOT_REGISTERED')
        return models

    def models(self):
        return {'default_model':self.selected,'runtime_default_model':self.default_model,'planner_model':None,'active_director_llm_max':1,
                'models':[{'model_key':k,'model_label':c['label'],'provider':c['provider'],'chain':c['chain'].split(',') if c.get('chain') else None} for k,c in self.catalog().items()]}
    def _provider(self,key):
        config=self.catalog().get(key)
        if not config:raise ProviderError('UNKNOWN_DIRECTOR_MODEL: '+str(key))
        if config['provider']=='local_llamacpp':return LocalLlamaCppProvider(config)
        return importlib.import_module(f'{__package__}.{config["provider"]}').create(config)
    def preferences(self):return {'selected_model':self.selected}
    def select_model(self,key):
        if key not in self.catalog():raise ProviderError('UNKNOWN_DIRECTOR_MODEL: '+str(key))
        with self.lock:
            atomic_json(self.preferences_path,{'selected_model':key});self.selected=key
        return self.preferences()
    def get_status(self):return self.manager.get_status()
    def local_backend_status(self,key):
        value=self.get_status();return dict(value,model_key=key,model_match=value.get('running_model')==key)
    def ensure_backend(self,key):return self.manager.warm_model(key)
    def warm_model(self,key):return self.manager.warm_model(key)
    def planner_session(self,key):
        return self.manager.planner_session(key) if self.catalog().get(key,{}).get('provider')=='local_llamacpp' else nullcontext()
    def _chain_generate(self,key,config,request):
        attempts=[];catalog=self.catalog()
        for member in [m.strip() for m in config['chain'].split(',') if m.strip()]:
            c=catalog.get(member)
            if not c or c['provider']!='openai_compat':raise ProviderError('INVALID_CLOUD_CHAIN_MEMBER: '+member)
            try:
                response=self._provider(member).generate(request)
                validator=request.metadata.get('response_validator')
                if validator:response.text=validator(response.text)
                response.raw_metadata.update(model_key=key,model_label=config['label'],requested_model_key=key,actual_model_key=member,actual_model_label=c['label'],fallback_count=len(attempts),chain_attempts=attempts)
                return response
            except FallbackableError as exc:attempts.append({'model_key':member,'trigger':str(exc)[:300]})
        raise ProviderError('CHAIN_EXHAUSTED: '+json.dumps(attempts,ensure_ascii=False)[:800])
    def generate(self,request):
        key=request.metadata.get('model_key') or self.selected;config=self.catalog().get(key)
        if not config:raise ProviderError('UNKNOWN_DIRECTOR_MODEL: '+str(key))
        request=replace(request,temperature=float(config.get('temperature',request.temperature)),top_p=float(config.get('top_p',request.top_p)))
        if config.get('chain'):return self._chain_generate(key,config,request)
        response=self.manager.generate_with_model(key,request) if config['provider']=='local_llamacpp' else self._provider(key).generate(request)
        response.raw_metadata.update(model_key=key,model_label=config['label'],requested_model_key=key,actual_model_key=key,fallback_count=0)
        return response
    def health(self):return self.get_status().get('healthy',False)
    def capabilities(self):
        status=self.get_status();key=status.get('running_model') or self.default_model
        return dict(self._provider(key).capabilities(),default_model=self.default_model,active_model_key=status.get('running_model'),selected_model=self.selected,active_director_llm_max=1)
