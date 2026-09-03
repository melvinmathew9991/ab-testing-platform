# Cookie Cats - first gate at level 30 vs level 40

_Moving the first progression gate from level 30 to level 40 lets players go deeper before they are blocked, which should increase the share of players who come back on day 1 and day 7._

**Recommendation: do not ship** (high confidence)  
retention_7 moved -4.31% against the hypothesis (p=0.0047)

## Results

| Metric | Role | Control | Treatment | Lift | 95% CI | p (adj.) | Verdict |
|---|---|---:|---:|---:|---:|---:|---|
| retention_1 | primary | 0.4482 | 0.4423 | -1.32% | -2.77% to +0.13% | 0.1116 | flat |
| retention_7 | primary | 0.1902 | 0.182 | -4.31% | -6.98% to -1.64% | 0.0047 | regression |
| game_rounds | guardrail | 49.14 | 48.85 | -0.57% | -2.81% to +1.66% | 0.6152 | flat |

## Trust checks

- **PASS** `sample_ratio_mismatch` - Split 49.563%/50.437% vs expected 50.0%/50.0% (chi2=6.90, p=0.0086)
- **PASS** `assignment_integrity` - No unit appears in both variants
- **PASS** `normal_approximation[retention_1 / gate_30]` - retention_1 / gate_30: 20,034 conversions / 24,666 non-conversions
- **PASS** `normal_approximation[retention_1 / gate_40]` - retention_1 / gate_40: 20,119 conversions / 25,370 non-conversions
- **PASS** `normal_approximation[retention_7 / gate_30]` - retention_7 / gate_30: 8,502 conversions / 36,198 non-conversions
- **PASS** `normal_approximation[retention_7 / gate_40]` - retention_7 / gate_40: 8,279 conversions / 37,210 non-conversions
- **PASS** `outlier_influence[game_rounds]` - game_rounds: top 91 units (0.10% of the sample) hold 3.8% of the total
