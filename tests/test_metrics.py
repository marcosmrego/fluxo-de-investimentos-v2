import unittest

from dashboard.metrics import percentage_change, portfolio_weight


class MetricsTest(unittest.TestCase):
    def test_percentage_change(self):
        self.assertEqual(percentage_change(100, 115), 15.0)
        self.assertEqual(percentage_change(100, 90), -10.0)

    def test_percentage_change_is_undefined_without_a_base(self):
        self.assertIsNone(percentage_change(0, 10))
        self.assertIsNone(percentage_change(None, 10))

    def test_weight_uses_full_portfolio_total(self):
        self.assertEqual(portfolio_weight(250, 1000), 25.0)
        self.assertEqual(portfolio_weight(250, 0), 0.0)


if __name__ == "__main__":
    unittest.main()
