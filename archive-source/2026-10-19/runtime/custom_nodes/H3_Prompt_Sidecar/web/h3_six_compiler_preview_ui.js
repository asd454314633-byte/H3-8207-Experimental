import {previewCompilePrompt} from './h3_six_compiler.js?v=20261019preview2';

export function installCompilerPreview(ui, root, app) {
  if (!ui?.cards?.length || root.dataset.h3CompilerPreview === 'installed') return;
  root.dataset.h3CompilerPreview = 'installed';
  for (const [index, card] of ui.cards.entries()) {
    if (card.card.querySelector('.h3-compiler-preview')) continue;
    const wrap = document.createElement('details');
    wrap.className = 'h3-compiler-preview';
    wrap.style.cssText = 'margin:8px 0;padding:8px;background:#121b26;border:1px solid #42546a;border-radius:7px';
    const summary = document.createElement('summary');
    summary.textContent = '8210 编译预览（不提交GPU）';
    summary.style.cursor = 'pointer';
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = '预览编译结果';
    button.style.cssText = 'margin:8px 8px 8px 0;padding:7px 12px;background:#315a4e;color:#fff;border:1px solid #8abfa9;border-radius:6px;cursor:pointer';
    const status = document.createElement('div');
    status.textContent = '尚未触发编译预览';
    status.style.cssText = 'font-weight:600;margin:6px 0;color:#d7e5ee';
    const reason = document.createElement('div');
    reason.style.cssText = 'white-space:pre-wrap;margin:5px 0;color:#c4ced8';
    const rawLabel = document.createElement('div'); rawLabel.textContent = '原稿'; rawLabel.style.fontWeight = '600';
    const raw = document.createElement('pre');
    raw.style.cssText = 'white-space:pre-wrap;overflow-wrap:anywhere;max-height:220px;overflow:auto;margin:4px 0;padding:8px;background:#0c1118;border-radius:5px';
    const compiledLabel = document.createElement('div'); compiledLabel.textContent = '8210完整编译稿'; compiledLabel.style.fontWeight = '600'; compiledLabel.hidden = true;
    const compiled = document.createElement('pre');
    compiled.style.cssText = 'white-space:pre-wrap;overflow-wrap:anywhere;max-height:360px;overflow:auto;margin:4px 0;padding:8px;background:#0c1118;border-radius:5px'; compiled.hidden = true;
    const usedLabel = document.createElement('div'); usedLabel.textContent = '本次预览拟用文本（未提交）'; usedLabel.style.fontWeight = '600';
    const used = document.createElement('pre');
    used.style.cssText = 'white-space:pre-wrap;overflow-wrap:anywhere;max-height:260px;overflow:auto;margin:4px 0;padding:8px;background:#0c1118;border-radius:5px';
    wrap.append(summary, button, status, reason, rawLabel, raw, compiledLabel, compiled, usedLabel, used);
    card.area.insertAdjacentElement('afterend', wrap);
    button.addEventListener('click', async () => {
      button.disabled = true; button.textContent = '正在调用8210…';
      status.textContent = '正在通过8207同源代理请求8210；不提交GPU'; reason.textContent = '';
      raw.textContent = card.area.value; compiled.textContent = ''; compiled.hidden = true; compiledLabel.hidden = true; used.textContent = '';
      try {
        const snapshot = await app.graphToPrompt();
        const result = await previewCompilePrompt(card.area.value, index, snapshot);
        status.textContent = result.status === 'COMPILED' ? 'COMPILED · 8210编译成功 · 仅预览' : result.status === 'RAW_FALLBACK' ? 'RAW_FALLBACK · 按原稿直通 · 仅预览' : 'UNCHANGED · 本次未触发结构化编译 · 仅预览';
        reason.textContent = result.reason + (result.refSummary ? `\n\n实际图接线：图片${result.refSummary.pictures}张（用途未指定），视频${result.refSummary.videos}路、音频${result.refSummary.audios}路；预览不推断职责。` : '');
        if (result.compiled) { compiled.textContent = result.compiled; compiled.hidden = false; compiledLabel.hidden = false; }
        used.textContent = result.used; wrap.open = true;
      } catch (error) {
        status.textContent = 'RAW_FALLBACK · 按原稿直通'; reason.textContent = '预览请求失败：' + error.message;
        raw.textContent = card.area.value; used.textContent = card.area.value; wrap.open = true;
      } finally { button.disabled = false; button.textContent = '重新预览编译结果'; }
    });
  }
}
