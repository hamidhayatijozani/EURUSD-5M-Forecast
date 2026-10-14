/**
 * Leakage-free 5M forecast core.
 * Combines timestamp-bound market features with a small auditable ensemble.
 */
import { deriveFeatures } from "./market-features.js";
import { buildModelEnsemble } from "./model-ensemble.js";
import { rankTopTraders, consensusFromTopTraders } from "./trader-intelligence.js";

export const VERSION = "0.3.0";

export function createForecast({symbol="EURUSD", timeframe="5m", createdAt, sourceTimestamp, basePrice, features={}, candles=null}) {
  if (!createdAt || !sourceTimestamp) throw new Error("timestamps required");
  if (new Date(sourceTimestamp) > new Date(createdAt)) throw new Error("source data is from the future");
  if (!Number.isFinite(basePrice) || basePrice <= 0) throw new Error("invalid base price");

  if (candles) {
    for (const candle of candles) {
      if (!candle?.timestamp || new Date(candle.timestamp) > new Date(createdAt)) {
        throw new Error("candle data is from the future");
      }
    }
  }
  const derived = candles ? deriveFeatures(candles) : {};
  const traderRank = Array.isArray(features.traderRecords) ? rankTopTraders(features.traderRecords, createdAt, 50) : [];
  const traderConsensus = traderRank.length ? consensusFromTopTraders(traderRank) : null;
  const merged = {...derived, ...features, indicators:{...derived.indicators,...features.indicators}};
  if (traderConsensus) merged.consensus = traderConsensus.score;
  const ensemble = buildModelEnsemble(merged);

  const momentum = clamp(Number(merged.momentum ?? 0), -1, 1);
  const trend = clamp(Number(merged.trend ?? 0), -1, 1);
  const volatility = clamp(Number(merged.volatility ?? 0.5), 0, 1);
  const consensus = clamp(Number(ensemble.score ?? merged.consensus ?? 0), -1, 1);

  const score = 0.30*momentum + 0.25*trend + 0.35*consensus - 0.10*Math.sign(momentum)*volatility;
  const step = basePrice * 0.00005 * score;
  const path = [0,1,2,3,4,5].map(i => round(basePrice + step*i));
  const move = path[5] - basePrice;
  const uncertainty = clamp(0.10 + 0.55*volatility + 0.20*(1-Math.abs(score)), 0, 1);
  const direction = Math.abs(move) < basePrice*0.00001 ? "FLAT" : move > 0 ? "UP" : "DOWN";

  return {
    version: VERSION,
    forecastId: hashKey(symbol, timeframe, createdAt, sourceTimestamp, basePrice, merged),
    symbol, timeframe, createdAt, sourceTimestamp, horizonMinutes:5,
    basePrice, predictedPath:path, predictedDirection:direction,
    uncertainty:round(uncertainty,6), score:round(score,6),
    modelWeights:ensemble.weights, traderConsensus:traderConsensus ?? {score:Number(merged.consensus??0),coverage:0}, inputs:{...merged}
  };
}

export function resolveForecast(forecast, observedPrices) {
  if (!forecast || !Array.isArray(observedPrices) || observedPrices.length < 2) throw new Error("complete outcome required");
  const finalObserved=observedPrices[observedPrices.length-1];
  const predicted=forecast.predictedPath[forecast.predictedPath.length-1];
  const error=finalObserved-predicted;
  const directionActual=finalObserved===forecast.basePrice?"FLAT":finalObserved>forecast.basePrice?"UP":"DOWN";
  return {...forecast,outcome:{observedPath:observedPrices,finalObserved,directionActual,
    directionalHit:forecast.predictedDirection===directionActual,
    absoluteError:Math.abs(error),signedError:error,resolvedAt:new Date().toISOString()}};
}
function clamp(x,a,b){return Math.max(a,Math.min(b,x))}
function round(x,n=5){const p=10**n;return Math.round(x*p)/p}
function hashKey(...xs){let h=2166136261;for(const c of JSON.stringify(xs)){h^=c.charCodeAt(0);h=Math.imul(h,16777619)}return (h>>>0).toString(16).padStart(8,"0")}
