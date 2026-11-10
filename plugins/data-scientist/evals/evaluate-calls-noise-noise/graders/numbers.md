---
type: llm
---

Against baseline_score (ROC-AUC 0.650): logreg_v2 is +0.011 and its paired interval includes zero, so it is inside the noise; gbt_v7 is +0.086 with an interval well above zero, a real improvement. gbt_v7 ranks best but is badly calibrated (mean predicted about 0.38 against an observed rate of about 0.19, expected calibration error about 0.19), and on the legacy plan its ROC-AUC falls to about 0.57.
PASS if the reply says gbt_v7's win is real and logreg_v2's difference is inside the noise, and notes gbt_v7's bad calibration and the legacy slice. FAIL if it calls logreg_v2 better, omits the calibration problem, or prints a personal value.
