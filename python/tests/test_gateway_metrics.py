import unittest
from unittest import mock

import services.gateway.app.main as gateway_main


class GatewayMetricsHelpersTests(unittest.TestCase):
    def test_record_http_metrics_uses_counter_and_histogram(self) -> None:
        histogram = mock.Mock()
        counter = mock.Mock()
        with mock.patch.object(gateway_main, "REQUEST_LATENCY", histogram), mock.patch.object(
            gateway_main, "REQUEST_COUNTER", counter
        ):
            gateway_main._record_http_metrics("/opt/start", "POST", "202", 0.42)
        histogram.labels.assert_called_once_with(endpoint="/opt/start", method="POST")
        histogram.labels.return_value.observe.assert_called_once()
        counter.labels.assert_called_once_with(endpoint="/opt/start", method="POST", status="202")
        counter.labels.return_value.inc.assert_called_once()

    def test_observe_solver_duration_tracks_histogram(self) -> None:
        histogram = mock.Mock()
        with mock.patch.object(gateway_main, "SOLVER_LATENCY", histogram):
            with gateway_main._observe_solver_duration("sealed_frequency_response"):
                pass
        histogram.labels.assert_called_once_with(solver="sealed_frequency_response")
        histogram.labels.return_value.observe.assert_called_once()

    def test_observe_measurement_comparison_tracks_histogram(self) -> None:
        histogram = mock.Mock()
        with mock.patch.object(gateway_main, "MEASUREMENT_COMPARISON_LATENCY", histogram):
            with gateway_main._observe_measurement_comparison("sealed", False):
                pass
        histogram.labels.assert_called_once_with(alignment="sealed", calibrated="false")
        histogram.labels.return_value.observe.assert_called_once()

    def test_update_run_metrics_sets_gauge_for_each_status(self) -> None:
        gauge = mock.Mock()
        label_calls: dict[str, mock.Mock] = {}

        def label_side_effect(*, status: str):  # type: ignore[override]
            label_mock = mock.Mock()
            label_calls[status] = label_mock
            return label_mock

        gauge.labels.side_effect = label_side_effect
        store = mock.Mock()
        store.status_counts.return_value = {
            "queued": 1,
            "running": 2,
            "succeeded": 3,
            "failed": 4,
        }
        with mock.patch.object(gateway_main, "RUN_STATUS_GAUGE", gauge):
            gateway_main._update_run_metrics(store)

        self.assertEqual(set(label_calls.keys()), gateway_main.VALID_STATUSES)
        for status, label_mock in label_calls.items():
            expected = float(store.status_counts.return_value.get(status, 0))
            label_mock.set.assert_called_once_with(expected)


if __name__ == "__main__":
    unittest.main()
