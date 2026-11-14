"""Failure contracts never reveal original exception strings."""
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

from timmy.failure_diagnostics import classify


def test_http_failure_maps_to_code_without_private_details():
    result=classify(HTTPException(409,'private row; bank account'),step='STRUCTURAL_VALIDATION')
    assert result.code=='STRUCTURAL_VALIDATION_HTTP_409'
    assert 'private row' not in str(result)
    assert len(result.correlation_id)==36


def test_db_failure_maps_to_database_code():
    error=OperationalError('SELECT SECRET',{},Exception('hidden row'))
    result=classify(error,step='CHAT_REQUEST')
    assert result.code=='CHAT_REQUEST_DATABASE_ERROR'
    assert 'SECRET' not in str(result)


def test_unknown_failure_has_operator_correlation():
    result=classify(RuntimeError('private info'),step='CHAT_REQUEST')
    assert result.code=='CHAT_REQUEST_UNEXPECTED_ERROR'
    assert 'private info' not in str(result)
