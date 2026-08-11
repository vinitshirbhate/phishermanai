/*
 * ml_scorer.js - Layer 1.5a, the in-extension LR-lex scorer (F-A2).
 *
 * Loads extension/models/lr_v1.json ({feature_names, means, scales,
 * coefficients, intercept}) and scores in ~40 lines of arithmetic. No WASM, no
 * ONNX runtime, no dependency - it runs offline in the service worker.
 *
 * Because it needs no DOM, this lane can score a link on HOVER and a URL inside
 * a WhatsApp message, surfaces where no DOM exists at all.
 *
 * Feature values MUST come from the same definition as training
 * (ml/features.py). eval/parity_test.py enforces agreement within +/-0.02.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.PhishermanML = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  let MODEL = null;

  function load(model) { MODEL = model; return !!MODEL; }
  function isLoaded() { return MODEL !== null; }

  function _sigmoid(z) { return 1 / (1 + Math.exp(-z)); }

  /**
   * @param {Object} feats name -> numeric value (superset is fine; extra keys ignored)
   * @returns {{p_phishing:number, model_version:string, feature_set_version:string,
   *            top_features:Array, layer:string}|null}
   */
  function score(feats) {
    if (!MODEL) return null;
    const names = MODEL.feature_names;
    let z = MODEL.intercept;
    const contribs = [];
    for (let i = 0; i < names.length; i++) {
      const raw = Number(feats[names[i]] || 0);
      const scale = MODEL.scales[i] || 1;
      const standardised = (raw - MODEL.means[i]) / scale;
      const c = standardised * MODEL.coefficients[i];
      z += c;
      contribs.push({ name: names[i], contribution: c });
    }
    contribs.sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution));
    return {
      p_phishing: _sigmoid(z),
      model_version: MODEL.model_version,
      feature_set_version: MODEL.feature_set_version,
      top_features: contribs.slice(0, 5),
      layer: "1.5a",
    };
  }

  /** Confidence-band routing (requirement.md F-A2 / §4.2). */
  function route(p, registrationState) {
    if (registrationState === "collision" || registrationState === "invalid") return "warn";
    if (p > 0.85) return "warn";
    if (p < 0.15 && (registrationState === "valid" || registrationState === "not_applicable")) return "allow";
    return "escalate";
  }

  return { load: load, isLoaded: isLoaded, score: score, route: route };
});
