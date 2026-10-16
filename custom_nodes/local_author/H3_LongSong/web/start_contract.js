// One deterministic origin for all six segments. Never infer lyric timing from prose.
export function seconds(value) {
 const s=String(value).trim();
 if(!/^-?\d+(?:\.\d+)?(?::\d+(?:\.\d+)?){0,2}$/.test(s))throw Error('音频起点须为秒数或mm:ss / hh:mm:ss');
 const parts=s.split(':').map(Number);
 if(parts.length>1&&parts.slice(1).some(n=>n>=60))throw Error('时间码的分、秒须小于60');
 const n=parts.reduce((a,b)=>a*60+b,0);
 if(!Number.isFinite(n)||n<0)throw Error('音频起点须为非负有限秒数');
 return n;
}
export function resolveSongStart(config,text='') {
 if(!config?.enabled)return config;
 const t=String(text),values=[];
 const number='(-?\\d+(?::\\d+){0,2}(?:\\.\\d+)?)';
 const patterns=[
  new RegExp('(?:音频|原音频|原曲|歌曲|音乐)(?:的)?(?:起点|起始时间|起始秒|开始时间|开始位置)\\s*(?:设置为|设为|为|是|[:：=])?\\s*'+number+'\\s*(?:秒|s(?:econds?)?\\b)?','gi'),
  new RegExp('从\\s*(?:(?:音频|原音频|原曲|歌曲|音乐)(?:的)?)?\\s*(?:第)?'+number+'\\s*(?:秒|s\\b)\\s*(?:处|位置)?\\s*(?:开始(?:生成|演唱|说唱|唱歌)?|起)','gi'),
  new RegExp('(?:audio|song|soundtrack|music)[ _-]*(?:start|offset)\\s*[:=]\\s*'+number+'\\s*(?:s(?:econds?)?)?','gi'),
  new RegExp('(?:start(?:ing)?|begin(?:ning)?)\\s+(?:the\\s+(?:video|generation)\\s+)?(?:at|from)\\s+'+number+'\\s*(?:seconds?|s)\\s*(?:of|into)\\s+(?:the\\s+)?(?:original\\s+|supplied\\s+)*(?:audio|song|recording|music)','gi'),
  new RegExp('(?:第一句歌词|首句歌词)[（(]\\s*'+number+'\\s*秒?\\s*[）)]','g')
 ];
 for(const re of patterns)for(const m of t.matchAll(re))values.push(seconds(m[1]));
 if(/从(?:原音频|音频|原曲|歌曲|音乐)(?:的)?(?:开头|最开头|开始处|头部)(?:开始|起)?/.test(t)||/(?:beginning|starting|begin|start)\s+(?:at|from)\s+(?:the\s+)?(?:actual\s+)?(?:start|beginning)\s+of\s+(?:the\s+)?(?:original\s+|supplied\s+)*(?:song|audio|recording|music)/i.test(t))values.push(0);
 const distinct=[...new Set(values)];
 if(distinct.length>1)throw Error('首段提示词存在冲突音频起点：'+distinct.join('、')+'秒；请保留一个起点');
 let start,origin;
 if(distinct.length){start=distinct[0];origin='首段提示词'}
 else if(/第一句歌词|首句歌词|first\s+(?:lyric|line\s+of\s+(?:the\s+)?lyrics)/i.test(t)){
  if(config.lyric_start_seconds==null||config.lyric_start_seconds==='')throw Error('提示词要求从第一句歌词开始：请填写“首句歌词秒数”，或写明“音频起点=12.5秒”。系统不会猜测歌词时间');
  start=seconds(config.lyric_start_seconds);origin='首句歌词定位';
 }else{start=seconds(config.start_seconds??0);origin='起始秒设置'}
 return {...config,start_seconds:start,start_origin:origin};
}
