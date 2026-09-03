import unittest
from unittest.mock import Mock, patch
import pandas as pd
import numpy as np
from scipy.stats import t

import sys

sys.path.append("..")
from permutation.analytics.statistical_test import (
    compute_t_test,
    ABTest,
)

# TODO: Mock-test PowerAnalysis
# , PowerAnalysis


class TestABTest(unittest.TestCase):
    def setUp(self):
        self.conn = Mock()
        self.ab_test = ABTest(self.conn)

    def test_compute_t_test(self):
        # Test if the function returns the expected columns
        c = pd.DataFrame(
            {
                ("conversions", "Treatment"): [10],
                ("conversions", "Control"): [5],
                ("conversion_rate", "Treatment"): [0.5],
                ("conversion_rate", "Control"): [0.25],
                ("visitors", "Treatment"): [20],
                ("visitors", "Control"): [20],
            }
        )
        result = compute_t_test(c)
        expected_columns = [
            "conversions_treatment",
            "conversions_control",
            "conversion_rate_treatment",
            "conversion_rate_control",
            "visitors_treatment",
            "visitors_control",
            "difference",
            "stdev",
            "t-score",
            "degrees_freedom",  # 'degrees_of_freedom'
            "p-value",
            "minimum_detectable_effect",
            "significant",
        ]
        self.assertListEqual(
            list(result.columns), expected_columns
        )

        # Test if the function correctly calculates t-test statistics
        c = pd.DataFrame(
            {
                ("conversions", "Treatment"): [40],
                ("conversions", "Control"): [32],
                ("conversion_rate", "Treatment"): [0.5],
                ("conversion_rate", "Control"): [0.4],
                ("visitors", "Treatment"): [80],
                ("visitors", "Control"): [80],
            }
        )
        result = compute_t_test(c)
        expected_p_value = t.sf(np.abs(1.2778), 159) * 2
        self.assertAlmostEqual(
            result["p-value"][0], expected_p_value, places=3
        )


if __name__ == "__main__":
    unittest.main()
