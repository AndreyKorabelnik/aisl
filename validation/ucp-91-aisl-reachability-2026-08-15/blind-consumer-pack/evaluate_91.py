#!/usr/bin/env python3
"""Acceptance-only structural comparison. Gold is supplied only after agent output is frozen."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

POS={"confirmed","strongly_supported","probable"}

def load_results(path: Path):
    obj=json.loads(path.read_text(encoding="utf-8"))
    if isinstance(obj,list): return obj
    return obj.get("results",[])

def norm_alt(alt):
    if isinstance(alt,str): return alt
    if isinstance(alt,dict):
        f=alt.get("field"); o=alt.get("object_fqcn")
        return f"{o}.{f}" if o and f else (f or o)
    return None

def match_target(g,r):
    if g.get("object_fqcn")==r.get("object_fqcn") and g.get("field")==r.get("field") and g.get("object_fqcn"):
        return "exact"
    rf=r.get("field"); ro=r.get("object_fqcn")
    cand={x for x in (norm_alt(a) for a in g.get("alternatives",[])) if x}
    forms={rf, f"{ro}.{rf}" if ro and rf else None, ro}
    return "alternative" if any(x in cand for x in forms if x) else None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--gold",required=True,type=Path)
    ap.add_argument("--result",required=True,type=Path)
    ap.add_argument("--out",required=True,type=Path)
    a=ap.parse_args()
    gold={x["input_index"]:x for x in load_results(a.gold)}
    res={x["input_index"]:x for x in load_results(a.result)}
    rows=[]
    for idx in sorted(gold):
        g=gold[idx]; r=res.get(idx)
        if r is None:
            cls="missing_result"; tm=None
        else:
            gs=g.get("status"); rs=r.get("status"); tm=match_target(g,r)
            if gs in POS:
                if rs in POS and tm: cls="accepted_positive"
                elif rs in POS: cls="wrong_positive_candidate"
                else: cls="missed_positive"
            elif gs=="unresolved":
                cls="aligned_unresolved" if rs=="unresolved" else ("conservative_ambiguity" if rs=="ambiguous" else "semantic_overclaim")
            elif gs=="ambiguous":
                cls="ambiguity_preserved" if rs in {"ambiguous","unresolved"} else "ambiguous_gold_positive_claim_review"
            else: cls="status_review"
        rows.append({"input_index":idx,"classification":cls,"target_match":tm,"gold_status":g.get("status"),"result_status":None if r is None else r.get("status"),"gold_object_fqcn":g.get("object_fqcn"),"gold_field":g.get("field"),"result_object_fqcn":None if r is None else r.get("object_fqcn"),"result_field":None if r is None else r.get("field")})
    counts={}
    for x in rows: counts[x["classification"]]=counts.get(x["classification"],0)+1
    gold_pos=sum(g["status"] in POS for g in gold.values())
    accepted=sum(x["classification"]=="accepted_positive" for x in rows)
    result_pos=sum((res.get(i) or {}).get("status") in POS for i in gold)
    precision=accepted/result_pos if result_pos else None
    recall=accepted/gold_pos if gold_pos else None
    out={"schema_version":"ucp-91-structural-diff/v1","result_sha256":hashlib.sha256(a.result.read_bytes()).hexdigest(),"gold_positive_count":gold_pos,"accepted_positive_count":accepted,"result_positive_count":result_pos,"positive_recall":recall,"positive_precision":precision,"classification_counts":counts,"rows":rows}
    a.out.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in out.items() if k!="rows"},ensure_ascii=False,indent=2))
if __name__=="__main__": main()
