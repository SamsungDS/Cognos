from collections import namedtuple

Feature = namedtuple(
    'Feature',
    ['feature_name', 'feature_id', 'feature_desc',
     'enabled', 'feature_params']
)
