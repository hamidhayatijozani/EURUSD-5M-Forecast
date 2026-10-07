"""Overlap-aware inference for ClaimLab.

Block bootstrap handles serial dependence. Hypothesis p-values are computed from
a null-centered bootstrap, not from a bootstrap distribution centered on the
observed effect. The distinction matters, because otherwise a strong-looking
result can manufacture its own p-value.
"""
from __future__ import annotations
import math, random
from typing import Dict, Iterable, List, Sequence

class StatisticalEngine:
    @staticmethod
    def calculate_effective_n(values: Sequence[float], horizon: int) -> int:
        x=[float(v) for v in values]; n=len(x); h=max(1,int(horizon))
        if n<=1 or n<=h:return max(1,n)
        m=sum(x)/n; var=sum((v-m)**2 for v in x)/n
        if var<=0:return n
        rho=0.0
        for lag in range(1,min(h,n-1)+1):
            cov=sum((x[i]-m)*(x[i+lag]-m) for i in range(n-lag))/(n*var)
            rho+=(1-lag/float(h))*cov
        d=1+2*rho
        return n if d<=0 else max(1,min(n,int(math.floor(n/d))))

    @staticmethod
    def benjamini_hochberg_correction(p_values:Sequence[float],alpha:float=.05)->List[bool]:
        p=[min(1,max(0,float(v))) for v in p_values]; m=len(p)
        if not m:return []
        ranked=sorted(enumerate(p),key=lambda z:z[1]); cutoff=-1
        for rank,(_,v) in enumerate(ranked,1):
            if v <= (rank/m)*alpha: cutoff=rank
        out=[False]*m
        if cutoff>=0:
            for rank,(idx,_) in enumerate(ranked,1):
                if rank<=cutoff: out[idx]=True
        return out

    @staticmethod
    def _draw_means(x,block_size,resamples,seed,center=0.0):
        n=len(x); b=max(1,min(int(block_size),n)); rng=random.Random(seed)
        full=n//b; rem=n%b
        if full==0: full=1; b=n; rem=0
        blocks=[]
        for start in range(n):
            total=sum(x[(start+j)%n] for j in range(b))
            partial=sum(x[(start+j)%n] for j in range(rem))
            blocks.append((total,partial))
        draws=max(100,int(resamples)); means=[]
        for _ in range(draws):
            total=0.0
            for _ in range(full): total+=blocks[rng.randrange(n)][0]
            if rem: total+=blocks[rng.randrange(n)][1]
            means.append(total/n-center)
        return means

    @staticmethod
    def block_bootstrap_ci(values,block_size,resamples=2000,alpha=.05,seed=20261006):
        x=[float(v) for v in values]; n=len(x)
        if not x:return {"mean":float("nan"),"ci_lower":float("nan"),"ci_upper":float("nan"),"p_value":float("nan")}
        means=StatisticalEngine._draw_means(x,block_size,resamples,seed,0.0)
        ordered=sorted(means); lo=max(0,min(len(ordered)-1,int(alpha/2*len(ordered))))
        hi=max(0,min(len(ordered)-1,int((1-alpha/2)*len(ordered))-1))
        observed=sum(x)/n
        null=StatisticalEngine._draw_means([v-observed for v in x],block_size,resamples,seed+7919,0.0)
        # Two-sided test: the null distribution is centered at zero, so compare
        # absolute deviations rather than only positive-tail draws.
        p=(sum(abs(v)>=abs(observed) for v in null)+1)/(len(null)+1)
        return {"mean":observed,"ci_lower":ordered[lo],"ci_upper":ordered[hi],"p_value":min(1.0,p)}

    @staticmethod
    def wilson_ci(successes:int,n:int,alpha=.05)->Dict[str,float]:
        if n<=0:return {"value":float("nan"),"ci_lower":float("nan"),"ci_upper":float("nan"),"p_value":float("nan")}
        z=1.959963984540054; phat=max(0,min(1,successes/n)); denom=1+z*z/n
        center=(phat+z*z/(2*n))/denom
        radius=z*math.sqrt(phat*(1-phat)/n+z*z/(4*n*n))/denom
        se=math.sqrt(max(1e-18,.25/n)); zstat=(phat-.5)/se
        return {"value":phat,"ci_lower":max(0,center-radius),"ci_upper":min(1,center+radius),
                "p_value":.5*math.erfc(zstat/math.sqrt(2))}

    @staticmethod
    def summarize(rows:Iterable[dict],horizon=5,resamples=2000,alpha=.05,seed=20261006)->Dict[str,object]:
        valid=[r for r in rows if r.get("status")=="VALID"]; n=len(valid)
        if not n:return {"n":0,"effective_n":0,"status":"INSUFFICIENT_DATA"}
        delta=[(float(r["baseline_error_absolute"])-float(r["error_absolute"]) if "baseline_error_absolute" in r and "error_absolute" in r else abs(float(r["actual"])-float(r["baseline_prediction"]))-abs(float(r["actual"])-float(r.get("prediction",0.0)))) for r in valid]
        net=[float(r["friction_adjusted_return"]) for r in valid]
        hit=sum(bool(r["direction_hit"]) for r in valid)
        neff=StatisticalEngine.calculate_effective_n(net,horizon)
        mae=StatisticalEngine.block_bootstrap_ci(delta,horizon,resamples,alpha,seed)
        ret=StatisticalEngine.block_bootstrap_ci(net,horizon,resamples,alpha,seed+1)
        hit_ci=StatisticalEngine.wilson_ci(hit,n,alpha)
        p=[mae["p_value"],hit_ci["p_value"],ret["p_value"]]
        bh=StatisticalEngine.benjamini_hochberg_correction(p,alpha)
        return {"n":n,"effective_n":neff,
          "mae_delta":mae["mean"],"mae_delta_ci_lower":mae["ci_lower"],"mae_delta_ci_upper":mae["ci_upper"],"mae_delta_p_value":mae["p_value"],
          "hit_rate":hit_ci["value"],"hit_rate_ci_lower":hit_ci["ci_lower"],"hit_rate_ci_upper":hit_ci["ci_upper"],"hit_rate_p_value":hit_ci["p_value"],
          "friction_adjusted_return":ret["mean"],"friction_adjusted_return_ci_lower":ret["ci_lower"],"friction_adjusted_return_ci_upper":ret["ci_upper"],"friction_adjusted_return_p_value":ret["p_value"],
          "bh_reject":{"C001":bh[0],"C002":bh[1],"C003":bh[2]},"status":"OK"}
