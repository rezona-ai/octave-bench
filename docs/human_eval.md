# Human cross-check of the automated evaluator

We compared the automated evaluator (`gpt-6-astra`, static source-code review) with human play-testing on the same
requirements (paper Section 4.4 and Appendix F). This page gives aggregate results only. Per-item human labels are
not released.

## Sample

* **8 Mobile player tasks, 75 generated artifacts, 344 requirements**, aligned one by one with the final evaluator
  judgments. Matching uses task, platform, model, artifact and requirement text. Records with a different
  requirement-list version or artifact mapping are excluded.
* Humans marked each requirement "satisfied", "not satisfied" or "indeterminate". 78 of the 344 are indeterminate
  (22.7%), which leaves **266 judgeable records**. Of the 204 public (Completeness) requirements, 39 are
  indeterminate (19.1%); of the 140 hidden (Richness) requirements, 39 are indeterminate (27.9%).
* Judgments for artifacts that failed the static gate are kept.
* Each artifact was assessed by one human annotator. The quality-control field is not a second independent
  annotation, so Cohen's κ and Krippendorff's α are not computed.

## Results (paper Table 5)

| Human / evaluator | Fail (0) | Pass (1) |
|---|---|---|
| Satisfied | 91 | 112 |
| Not satisfied | 52 | 11 |

* Human–evaluator agreement: 164 / 266 = **61.7%**.
* Human satisfaction rate: 203 / 266 = **76.3%**. Evaluator pass rate: 123 / 266 = **46.2%**.
* Disagreement goes mainly one way: 91 requirements were judged satisfied by humans but failed by the evaluator,
  and 11 were judged not satisfied by humans but passed by the evaluator.

The static source-code review is therefore stricter than human observation. The human assessment is used to find
where automated judgments and actual play diverge; it is not used in any score.

## Limitations

* The sample is small and covers only Mobile player tasks.
* One annotator per artifact, so there is no inter-annotator agreement.
* The returned records do not preserve play-testing duration per artifact, dual ratings or full recordings, and do
  not record whether machine scores or source code were visible during reassessment (paper Appendix F.1).
