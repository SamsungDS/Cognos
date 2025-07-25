import pytest

from cognos.backend.logger import create_logger


def test_create_logger(caplog):
    name = 'mock_logger'
    logger = create_logger(name)
    logger.info('MOCK LOG')
    assert 'MOCK LOG' in caplog.text
    logger.critical('MOCK WARNING')
    assert caplog.records[-1].levelname == "CRITICAL"
