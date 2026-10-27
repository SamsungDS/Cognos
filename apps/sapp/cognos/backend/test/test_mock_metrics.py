import pytest


import cognos.backend.mock_metrics as mock_metrics


def test_get_mock_device_stats():
    dummy_device_id = 3231232131
    assert mock_metrics.get_mock_device_stats(dummy_device_id, "total_memory_MB")
    assert mock_metrics.get_mock_device_stats(dummy_device_id, "used_memory_MB")
    assert mock_metrics.get_mock_device_stats(dummy_device_id, "used_bandwidth_Bps")
    assert mock_metrics.get_mock_device_stats(dummy_device_id, "total_bandwidth_MBps")
    assert mock_metrics.get_mock_device_stats(dummy_device_id, "fpga_temp_in_F")
    assert mock_metrics.get_mock_device_stats(dummy_device_id, "available_memory_MB")
    with pytest.raises(ValueError):
        mock_metrics.get_mock_device_stats(dummy_device_id, "invalid_key")
