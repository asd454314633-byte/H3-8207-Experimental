#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
H3-8207 公开包轻量冒烟测试（离线、无需 GPU / 权重）。
验证：包内 JSON 可解析、local_author 文件数与清单一致、workflows/current 齐全。
"""
import os, json, sys

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def walk_json(root):
    bad, total = [], 0
    for dp, _, fns in os.walk(root):
        for fn in fns:
            if not fn.lower().endswith('.json'):
                continue
            total += 1
            fp = os.path.join(dp, fn)
            try:
                json.load(open(fp, encoding='utf-8'))
            except Exception as e:
                bad.append((os.path.relpath(fp, PKG), str(e)))
    return total, bad

def main():
    errs = []
    # 1) 全包 JSON 可解析
    total, bad = walk_json(PKG)
    if bad:
        errs.append(f"{len(bad)} 个 JSON 解析失败（共 {total}）")
        for rel, e in bad[:10]:
            print("  BAD:", rel, e)
    else:
        print(f"[1] 包内全部 {total} 个 JSON 解析通过")

    # 2) local_author 文件数 == 清单（COPY_INVENTORY.json 为元数据，不计入源码）
    la = os.path.join(PKG, 'custom_nodes', 'local_author')
    la_files = sum(len(f) for _, _, f in os.walk(la))
    if os.path.exists(os.path.join(la, 'COPY_INVENTORY.json')):
        la_files -= 1
    inv = os.path.join(la, 'COPY_INVENTORY.json')
    inv_n = 0
    if os.path.exists(inv):
        inv_n = len(json.load(open(inv, encoding='utf-8')))
    if inv_n and la_files != inv_n:
        errs.append(f"local_author 实际 {la_files} != 清单 {inv_n}")
    else:
        print(f"[2] local_author 文件数 {la_files}（清单 {inv_n}）一致")

    # 3) workflows/current 12 个
    cur = os.path.join(PKG, 'workflows', 'current')
    wf = [f for f in os.listdir(cur) if f.lower().endswith('.json')] if os.path.isdir(cur) else []
    if len(wf) != 12:
        errs.append(f"workflows/current 应为 12，实际 {len(wf)}")
    else:
        print(f"[3] workflows/current 含 {len(wf)} 个已脱敏工作流")

    if errs:
        print("\nSMOKE TEST FAILED:")
        for e in errs:
            print("  -", e)
        sys.exit(1)
    print("\nSMOKE TEST PASSED.")
    sys.exit(0)

if __name__ == '__main__':
    main()
