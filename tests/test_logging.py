import json
import logging

from app.logging_config import JsonFormatter


def _make_record(msg="hello world", level=logging.INFO, name="test.logger"):
    return logging.LogRecord(
        name=name,
        level=level,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )


def test_json_formatter_emits_valid_json():
    record = _make_record()
    out = JsonFormatter().format(record)
    payload = json.loads(out)
    assert payload["message"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.logger"
    assert "timestamp" in payload


def test_json_formatter_includes_request_id_when_present():
    record = _make_record()
    record.request_id = "req-123"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["request_id"] == "req-123"


def test_json_formatter_omits_optional_fields_by_default():
    payload = json.loads(JsonFormatter().format(_make_record()))
    assert "request_id" not in payload
    assert "exception" not in payload


def test_json_formatter_includes_exception():
    record = _make_record()
    try:
        raise ValueError("boom")
    except ValueError:
        record.exc_info = __import__("sys").exc_info()
    payload = json.loads(JsonFormatter().format(record))
    assert "boom" in payload["exception"]
