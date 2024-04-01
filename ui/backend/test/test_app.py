import pytest
import unittest
import mysql.connector
import flask
import json
from unittest.mock import MagicMock, patch

import app


def __sql_connect_helper(mocker):
    db = mysql.connector.connection.MySQLConnection()
    cursor = mysql.connector.cursor.MySQLCursor()
    mocker.patch.object(
        mysql.connector,
        "connect",
        return_value=db
    )
    mocker.patch.object(
        mysql.connector.connection.MySQLConnection,
        'is_connected',
        return_value=True
    )
    mocker.patch.object(
        mysql.connector.connection.MySQLConnection,
        'close',
        return_value=True
    )
    mocker.patch.object(
        mysql.connector,
        "cursor",
        return_value=cursor
    )


def test_connect_to_my_sql_and_close(mocker):
    __sql_connect_helper(mocker)
    db, cursor = app.connect_to_mysql()
    unittest.TestCase.assertIsNotNone(db, "connecton failure")
    unittest.TestCase.assertIsNotNone(cursor, "cursor not created")
    app.disconnect_mysql(db)


def test_get_hosts(mocker):
    def __cursor_execute():
        return None
    res = flask.Response()
    res.set_data(json.dumps([('host1', 128, 256, 128, 'GB'),
                             ('host2', 128, 256, 128, 'GB')]))

    __sql_connect_helper(mocker)
    db, cursor = app.connect_to_mysql()
    db.cursor = MagicMock(return_value=cursor)
    cursor.execute = MagicMock(size_effect=__cursor_execute)
    cursor.fetchall = MagicMock(return_value=[
                        ('host1', 128, 256, 128, 'GB'),
                        ('host2', 128, 256, 128, 'GB')])
    app.app.jsonify = MagicMock(return_value=res)
    app.app.jsonify(res)
    ctx = app.app.app_context()
    ctx.push()
    response = app.get_hosts()
    ctx.pop()


def test_get_partitions(mocker):
    def __cursor_execute():
        return None

    __sql_connect_helper(mocker)
    db, cursor = app.connect_to_mysql()
    res = flask.Response()
    res.set_data(json.dumps([
        ('active', 'd1', 'p1', 'd1', 'direct', 256, 'GB', 0,
         'GB', 'SLD', 'host1')]))
    db.cursor = MagicMock(return_value=cursor)
    cursor.execute = MagicMock(size_effect=__cursor_execute)
    cursor.fetchall = MagicMock(return_value=[(
                        'active', 'd1', 'p1', 'd1',
                        'direct', 256, 'GB', 0, 'GB', 'SLD',
                        'host1')])
    app.app.jsonify = MagicMock(return_value=res)
    app.app.jsonify(res)
    ctx = app.app.app_context()
    ctx.push()
    response = app.get_partitions()
    ctx.pop()


def test_get_membox_lmds(mocker):

    def __cursor_execute():
        return None

    __sql_connect_helper(mocker)
    db, cursor = app.connect_to_mysql()
    res = flask.Response()
    res.set_data(json.dumps([('active', 'd1', 'mb1', 'SLD', 'direct',
                              'p1', 256, 'GB', 'host1')]))

    db.cursor = MagicMock(return_value=cursor)
    cursor.execute = MagicMock(size_effect=__cursor_execute)
    cursor.fetchall = MagicMock(return_value=[('active', 'd1', 'mb1',
                                               'SLD', 'direct', 'p1',
                                               256, 'GB', 'host1')])
    app.app.jsonify = MagicMock(return_value=res)
    app.app.jsonify(res)
    ctx = app.app.app_context()
    ctx.push()
    request_ctx = app.app.test_request_context(
        "/membox_lmds", json={"mem_box": "mb1"})
    request_ctx.push()
    response = app.get_membox_lmds()
    ctx.pop()
    request_ctx.pop()


def test_host_lmds(mocker):

    def __cursor_execute():
        return None

    __sql_connect_helper(mocker)
    db, cursor = app.connect_to_mysql()
    res = flask.Response()
    res.set_data(json.dumps([('d1', 'p1', 'SLD', 'direct',
                              256, 'GB', 0, 'GB')]))

    db.cursor = MagicMock(return_value=cursor)
    cursor.execute = MagicMock(size_effect=__cursor_execute)
    cursor.fetchall = MagicMock(return_value=[('d1', 'p1', 'SLD', 'direct',
                                               256, 'GB', 0, 'GB')])
    app.app.jsonify = MagicMock(return_value=res)
    app.app.jsonify(res)
    ctx = app.app.app_context()
    ctx.push()
    request_ctx = app.app.test_request_context("/host_lmds",
                                               json={"host": "host1"})
    request_ctx.push()
    response = app.host_lmds()
    ctx.pop()
    request_ctx.pop()


def test_attached_hosts(mocker):

    def __cursor_execute():
        return None

    __sql_connect_helper(mocker)
    db, cursor = app.connect_to_mysql()
    res = flask.Response()
    res.set_data(json.dumps([('host1')]))
    db.cursor = MagicMock(return_value=cursor)
    cursor.execute = MagicMock(size_effect=__cursor_execute)
    cursor.fetchall = MagicMock(return_value=[('host1')])
    app.app.jsonify = MagicMock(return_value=res)
    app.app.jsonify(res)
    ctx = app.app.app_context()
    ctx.push()
    response = app.attached_hosts()
    ctx.pop()


def test_attach_lmd(mocker):

    def __cursor_execute():
        return None

    __sql_connect_helper(mocker)
    db, cursor = app.connect_to_mysql()
    db.commit = MagicMock(return_value=True)
    res = flask.Response()
    res.set_data(json.dumps([('d1', 'p1', 'SLD', 'direct', 256,
                              'GB', 0, 'GB')]))
    db.cursor = MagicMock(return_value=cursor)
    cursor.execute = MagicMock(size_effect=__cursor_execute)
    cursor.fetchall = MagicMock(return_value=[('d1', 'p1', 'SLD',
                                               'direct', 256,
                                               'GB', 0, 'GB')])
    app.app.jsonify = MagicMock(return_value=res)
    app.app.jsonify(res)
    ctx = app.app.app_context()
    ctx.push()
    request_ctx = app.app.test_request_context("/host_lmds",
                                               json={"host": "host1",
                                                     "host_memory_address":
                                                     "0xdeadbeef",
                                                     "lmd": "d1"})
    request_ctx.push()
    response = app.attach_lmd()
    request_ctx.pop()
    ctx.pop()


def test_detach_lmd(mocker):

    def __cursor_execute():
        return None

    __sql_connect_helper(mocker)
    db, cursor = app.connect_to_mysql()
    db.commit = MagicMock(return_value=True)
    res = flask.Response()
    res.set_data(json.dumps([('d1', 'p1', 'SLD', 'direct',
                              256, 'GB', 0, 'GB')]))
    db.cursor = MagicMock(return_value=cursor)
    cursor.execute = MagicMock(size_effect=__cursor_execute)
    cursor.fetchall = MagicMock(return_value=[('d1', 'p1', 'SLD', 'direct',
                                               256, 'GB', 0, 'GB')])
    app.app.jsonify = MagicMock(return_value=res)
    app.app.jsonify(res)
    ctx = app.app.app_context()
    ctx.push()
    request_ctx = app.app.test_request_context("/host_lmds",
                                               json={"host": "host1",
                                                     "lmd": "d1"})
    request_ctx.push()
    response = app.detach_lmd()
    request_ctx.pop()
    ctx.pop()


def test_update_device_status(mocker):

    def __cursor_execute():
        return None

    __sql_connect_helper(mocker)
    db, cursor = app.connect_to_mysql()
    db.commit = MagicMock(return_value=True)
    res = flask.Response()
    res.set_data(json.dumps([('active', 'd1', 'p1', 'SLD', 'direct', 256, 'GB',
                              0, 'GB', 'SLD', 'host1')]))

    db.cursor = MagicMock(return_value=cursor)
    cursor.execute = MagicMock(size_effect=__cursor_execute)
    cursor.fetchall = MagicMock(return_value=[('active', 'd1', 'p1', 'SLD',
                                               'direct', 256, 'GB', 0, 'GB',
                                               'SLD', 'host1')])
    app.app.jsonify = MagicMock(return_value=res)
    app.app.jsonify(res)
    ctx = app.app.app_context()
    ctx.push()
    request_ctx = app.app.test_request_context("/host_lmds",
                                               json={"host": "host1",
                                                     "lmd": "d1"})
    request_ctx.push()
    response = app.update_device_status()
    request_ctx.pop()
    ctx.pop()


def test_create_lmd(mocker):

    def __cursor_execute():
        return None

    __sql_connect_helper(mocker)
    db, cursor = app.connect_to_mysql()
    db.commit = MagicMock(return_value=True)
    res = flask.Response()
    res.set_data(json.dumps([('active', 'd1', 'p1', 'SLD', 'direct', 256,
                              'GB', 0, 'GB', 'SLD', 'host1')]))
    db.cursor = MagicMock(return_value=cursor)
    cursor.execute = MagicMock(size_effect=__cursor_execute)
    cursor.fetchall = MagicMock(return_value=[('active', 'd1', 'p1', 'SLD',
                                               'direct', 256, 'GB', 0, 'GB',
                                               'SLD', 'host1')])
    app.app.jsonify = MagicMock(return_value=res)
    app.app.jsonify(res)
    ctx = app.app.app_context()
    ctx.push()
    request_ctx = app.app.test_request_context(
        "/host_lmds", json={"isPoolFlag": "True", "logicalMemoryDevice": "d1",
                            "pool": "p1", "memoryType": "SLD",
                            "memoryMode": "direct", "memoryAllocation": "direc"
                            }
    )
    request_ctx.push()
    response = app.create_lmd()
    request_ctx.pop()
    ctx.pop()


def test_available_lmds(mocker):

    def __cursor_execute():
        return None

    __sql_connect_helper(mocker)
    db, cursor = app.connect_to_mysql()
    db.commit = MagicMock(return_value=True)
    res = flask.Response()
    res.set_data(json.dumps([('d1')]))
    db.cursor = MagicMock(return_value=cursor)
    cursor.execute = MagicMock(size_effect=__cursor_execute)
    cursor.fetchall = MagicMock(return_value=[('d1')])
    app.app.jsonify = MagicMock(return_value=res)
    app.app.jsonify(res)
    ctx = app.app.app_context()
    ctx.push()
    request_ctx = app.app.test_request_context("/available_lmds")
    request_ctx.push()
    response = app.available_lmds()
    request_ctx.pop()
    ctx.pop()


def test_free_lmd(mocker):

    def __cursor_execute():
        return None

    __sql_connect_helper(mocker)
    db, cursor = app.connect_to_mysql()
    db.commit = MagicMock(return_value=True)
    res = flask.Response()
    res.set_data(json.dumps([('active', 'd1', 'p1', 'SLD', 'direct', 256,
                              'GB', 0, 'GB', 'SLD', 'host1')]))
    db.cursor = MagicMock(return_value=cursor)
    cursor.execute = MagicMock(size_effect=__cursor_execute)
    cursor.fetchall = MagicMock(return_value=[('active', 'd1', 'p1', 'SLD',
                                               'direct', 256, 'GB', 0, 'GB',
                                               'SLD', 'host1')])
    app.app.jsonify = MagicMock(return_value=res)
    app.app.jsonify(res)
    ctx = app.app.app_context()
    ctx.push()
    request_ctx = app.app.test_request_context("/available_lmds",
                                               json={"lmd": "d1"})
    request_ctx.push()
    response = app.free_lmd()
    request_ctx.pop()
    ctx.pop()


def test_get_connections(mocker):

    def __cursor_execute():
        return None

    __sql_connect_helper(mocker)
    db, cursor = app.connect_to_mysql()
    db.commit = MagicMock(return_value=True)
    res = flask.Response()
    res.set_data(json.dumps([('host1', 'd1', 'mb1', 'd1')]))
    db.cursor = MagicMock(return_value=cursor)
    cursor.execute = MagicMock(size_effect=__cursor_execute)
    cursor.fetchall = MagicMock(return_value=[('host1', 'd1', 'mb1', 'd1')])
    app.app.jsonify = MagicMock(return_value=res)
    app.app.jsonify(res)
    ctx = app.app.app_context()
    ctx.push()
    request_ctx = app.app.test_request_context("/connections")
    request_ctx.push()
    response = app.get_connections()
    request_ctx.pop()
    ctx.pop()


def test_get_host_device_map(mocker):

    def __cursor_execute():
        return None

    __sql_connect_helper(mocker)
    db, cursor = app.connect_to_mysql()
    db.commit = MagicMock(return_value=True)
    res = flask.Response()
    res.set_data(json.dumps([('host1', 'd1')]))
    db.cursor = MagicMock(return_value=cursor)
    cursor.execute = MagicMock(size_effect=__cursor_execute)
    cursor.fetchall = MagicMock(return_value=[('host1', 'd1')])
    app.app.jsonify = MagicMock(return_value=res)
    app.app.jsonify(res)
    ctx = app.app.app_context()
    ctx.push()
    request_ctx = app.app.test_request_context("/connections")
    request_ctx.push()
    response = app.get_host_device_map()
    request_ctx.pop()
    ctx.pop()

# def test_get_mb_info(mocker):
#     ctx = app.app.app_context()
#     ctx.push()
#     request_ctx = app.app.test_request_context("/api/v1/cxl/mb/info")
#     request_ctx.push()
#     response = app.get_host_device_map()
#     request_ctx.pop()
#     ctx.pop()
