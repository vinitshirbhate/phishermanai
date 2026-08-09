# Model Card - lr_v1 (LR-lex)

| Field | Value |
|---|---|
| model_version | `lr_v1` |
| feature_set_version | `fs_v2` |
| trained_at | 2026-08-09T11:12:13.891183+00:00 |
| commit | `4707c7b-dirty` |
| dataset | PhiUSIIL (UCI id 967), URL column only |
| dataset_sha256 (16) | `45134bb6ced2138d` |
| n_train / n_test | 13,898 / 6,102 |
| distinct registrable domains | 15,230 |
| features used | 18 (the artefact-free `domain` group) of 41 defined |
| split | domain-grouped (`GroupShuffleSplit`, test_size=0.3), no domain in both sides |
| decision threshold (FPR<=1%) | 0.8124 |

## Metrics (held-out 30%, domain-grouped)

| Metric | Value | Target (requirement.md §7.1) | Met? |
|---|---|---|---|
| MCC | 0.6370 (95% CI 0.6190-0.6554) | >= 0.55 | YES |
| PR-AUC | 0.8907 | - | - |
| Recall @ FPR<=1% | 0.5705 | - | - |
| Brier | 0.1420 | <= 0.12 | NO |
| Confusion | TN=2815 FP=165 FN=1028 TP=2094 | - | - |

## Split-to-split robustness (5-fold GroupKFold, reporting only)

The single held-out number above comes with a bootstrap CI that only reflects
sampling variance of the test *rows* given the domains that happened to land in
test. Since `GroupShuffleSplit`'s domain assignment is itself a random draw,
this 5-fold group-CV summary gives a more honest picture of how much
MCC would move under a different domain split. It does not change what ships —
the model above is trained on the single split, per the split rationale below.

| Fold MCC | Mean | Std |
|---|---|---|
| 0.5876, 0.6318, 0.6239, 0.6256, 0.5946 | 0.6127 | 0.0180 |

The MCC target was revised from 0.85 to 0.55 on the evidence of
`eval/corpus_audit.py`. The rationale is in `eval/REPORT.md` §B.2: 0.85 was set
before anyone audited the corpus, and it is not reachable honestly on PhiUSIIL's
URL column. It IS reachable dishonestly - 34 artefact-bearing features score MCC
0.99 - which is precisely why the target moved rather than the feature set.

## Features used (artefact-free `domain` group)
- `host_len`  (coef +6.344)
- `host_entropy`  (coef -0.401)
- `label_count`  (coef -1.238)
- `hyphens`  (coef +0.695)
- `digits`  (coef +2.262)
- `digit_ratio`  (coef -0.030)
- `vowel_ratio`  (coef +0.013)
- `longest_label`  (coef -3.046)
- `tld_len`  (coef -0.087)
- `suspicious_tld`  (coef +1.695)
- `has_ip`  (coef +0.087)
- `has_punycode`  (coef +0.117)
- `brand_token_count`  (coef +0.087)
- `domain_entropy`  (coef +0.148)
- `domain_len`  (coef -1.175)
- `repeated_char_runs`  (coef -0.026)
- `consonant_run_max`  (coef +0.237)
- `has_digit_letter_mix`  (coef -0.008)

## Features deliberately EXCLUDED
Not a variance filter - a decision. Scheme, `www.` prefix, path length, query
length, slash count and path depth all carry ample variance in this corpus; they
are excluded because they encode the collection artefact rather than fraud.
DOM and page-text features are additionally unavailable from a bare URL.

- `url_length`
- `url_entropy`
- `subdomain_count`
- `param_count`
- `has_ip_host`
- `sensitive_keyword_count`
- `external_link_ratio`
- `empty_links_ratio`
- `suspicious_form_action`
- `hidden_iframe_count`
- `script_to_content_ratio`
- `password_field_count`
- `input_field_count`
- `meta_refresh_present`
- `external_resource_ratio`
- `dom_nesting_depth`
- `upi_id_present`
- `upi_outside_valid_namespace`
- `registration_claim_present`
- `registration_resolves`
- `securities_keyword_density`
- `typosquat_distance_to_intermediary`
- `guaranteed_return_claim_present`

## Known limitations
- Artefact-free by construction: scheme, www-prefix, path and query are EXCLUDED because eval/corpus_audit.py shows all four are collection artefacts in PhiUSIIL (100% of legitimate URLs are canonicalised https://www. homepages with no path). A model given those columns scores MCC 0.99 and flags every legitimate deep link, including sebi.gov.in's own register URL. This model is deliberately weaker and deliberately honest.
- URL-only: DOM and page-text features cannot be recovered from a dead phishing URL.
- No temporal split available (no timestamps in PhiUSIIL); the domain-grouped split controls campaign leakage but not concept drift over time.
- Not evaluated on Indian securities-scam URLs specifically — PhiUSIIL is general phishing. Treat the securities framing as untested for this lane.
- This is a PRE-FILTER, never the verdict. The authentication path (registration resolution against the SEBI register) is deterministic, offline and independent of this model.

## Rollback
The deterministic path (registration check + 18-rule offline gate) is independent
of this model and is immune to model drift. Deleting
`extension/models/lr_v1.json` disables Layer 1.5a; the chain still returns a
verdict from the remaining layers (F-D2).
