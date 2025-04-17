import pytest

from cognos.backend.feature import Feature


def test_feature_attrs():
    cognos_feature = Feature(
        'cxl_plugin', 152, 'used for cxl device operations and metadata',
        True, {'param_1': 'desc of param1'}
    )
    assert cognos_feature
    assert cognos_feature.feature_name == 'cxl_plugin'
    assert cognos_feature.feature_id == 152
    assert len(cognos_feature.feature_desc) > 1
    assert cognos_feature.enabled is True
    assert cognos_feature.feature_params
