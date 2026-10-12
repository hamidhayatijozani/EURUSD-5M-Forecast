"""Evaluate the forward-only cross-asset paper ledger; never execute orders."""
import json, os
from datetime import datetime
from pathlib import Path
from claimlab.statistics import StatisticalEngine
from scripts.live_minute_loop import _read_cross_asset_ledger, CROSS_ASSET_CONTRACT_VERSION

REGISTRATION=Path("research/LIVE_CROSS_ASSET_PREREGISTRATION.json")
OUTPUT=Path("evidence/cross-asset-forward-evaluation.json")
COSTS=(0.00002,0.00005,0.0001)
MIN_RESOLVED=1000
MIN_TRADES=200
RESAMPLES=2000
BLOCK_SIZE=5


def evaluate(rows,code_commit="LOCAL"):
    registration=json.loads(REGISTRATION.read_text(encoding="utf-8"))
    total_chain_rows=len(rows)
    activation=datetime.fromisoformat(registration["activation_time"].replace("Z","+00:00"))
    rows=[r for r in rows if r.get("contract_version")==CROSS_ASSET_CONTRACT_VERSION
          and r.get("freshness_status")=="FRESH"
          and datetime.fromisoformat(r["issued_at"].replace("Z","+00:00"))>=activation]
    candidates=registration["candidate_ids"]
    metrics={}; p_values=[]
    for index,candidate in enumerate(candidates):
        items=[r for r in rows if r.get("candidate_id")==candidate]
        net=[]; gross_sum=0.0; net_sums={cost:0.0 for cost in COSTS}; trades=hits=0
        for row in items:
            position=int(row["position"]); actual=float(row["actual_return"])
            gross=position*actual
            if position:
                trades+=1
            for cost in COSTS:
                net_value=gross-cost*abs(position) if position else 0.0
                net_sums[cost]+=net_value
                if cost==COSTS[0]:
                    net.append(net_value); gross_sum+=gross; hits+=int(position!=0 and net_value>0)
        if len(net)>=MIN_RESOLVED:
            inference=StatisticalEngine.block_bootstrap_ci(
                net,block_size=BLOCK_SIZE,resamples=RESAMPLES,alpha=.05,seed=20261015+index)
            pvalue=inference["p_value"]
            ci_lower=inference["ci_lower"]; ci_upper=inference["ci_upper"]
            net_mean=inference["mean"]
        else:
            pvalue=1.0; ci_lower=None; ci_upper=None; net_mean=(sum(net)/len(net) if net else None)
        metrics[candidate]={
            "resolved_observations":len(items),
            "trades":trades,
            "coverage":trades/len(items) if items else None,
            "trade_hit_rate_after_cost":hits/trades if trades else None,
            "gross_return_sum":gross_sum,
            "net_return_sum_at_0_2_pip":net_sums[COSTS[0]],
            "net_return_mean_per_observation":net_mean,
            "ci_lower_net_mean":ci_lower,"ci_upper_net_mean":ci_upper,
            "two_sided_block_bootstrap_p_value":pvalue,
            "net_return_sum_sensitivity":{
                f"{cost/0.0001:.1f}_pip":net_sums[cost] for cost in COSTS},
            "status":"READY_FOR_INFERENCE" if len(items)>=MIN_RESOLVED else "INSUFFICIENT_DATA",
        }
        p_values.append(pvalue)
    rejects=StatisticalEngine.benjamini_hochberg_correction(p_values,alpha=.05)
    for candidate,reject in zip(candidates,rejects):
        metric=metrics[candidate]
        metric["bh_reject_at_0_2_pip"]=reject
        metric["survives_gate"]=bool(
            candidate!="LIVE1M_NO_TRADE"
            and metric["resolved_observations"]>=MIN_RESOLVED
            and metric["trades"]>=MIN_TRADES
            and metric["ci_lower_net_mean"] is not None
            and metric["ci_lower_net_mean"]>0.0
            and reject)
    survivors=[c for c in candidates if metrics[c]["survives_gate"]]
    enough=any(metrics[c]["resolved_observations"]>=MIN_RESOLVED for c in candidates if c!="LIVE1M_NO_TRADE")
    return {
        "schema":"claimlab.live_cross_asset_evaluation.v1",
        "status":"COMPUTED_FORWARD_PAPER_EVIDENCE" if enough else "INSUFFICIENT_DATA",
        "verdict":"SURVIVES" if survivors else ("KILLED" if enough else "INSUFFICIENT_DATA"),
        "surviving_candidates":survivors,
        "registration":registration,
        "execution":{"code_commit":code_commit,"contract_version":CROSS_ASSET_CONTRACT_VERSION,
                     "rows_in_hash_chain":total_chain_rows,"eligible_fresh_rows":len(rows),"minimum_resolved":MIN_RESOLVED,
                     "minimum_trades":MIN_TRADES,"primary_cost":COSTS[0],
                     "cost_sensitivity":list(COSTS),"block_size":BLOCK_SIZE,
                     "bootstrap_resamples":RESAMPLES,
                     "multiple_testing":"Benjamini-Hochberg across frozen candidates"},
        "metrics":metrics,
        "scientific_boundary":{"paper_only":True,"broker_cost_verified":False,
            "profitability_established":False,"real_orders_executed":False},
    }


def main():
    rows,_=_read_cross_asset_ledger()
    result=evaluate(rows,code_commit=os.getenv("GITHUB_SHA","LOCAL"))
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
