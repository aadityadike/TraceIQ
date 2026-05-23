import json
from tasks.analyze_logs import parse_groq_response, strip_markdown_json


def test_strip_clean_json():
    raw = '[{"error_type": "ConnectionTimeout", "severity": "critical", "count": 5}]'
    assert strip_markdown_json(raw) == raw


def test_strip_markdown_fenced_json():
    raw = '```json\n[{"error_type": "NPE", "severity": "high", "count": 1}]\n```'
    result = strip_markdown_json(raw)
    assert result.startswith("[")
    parsed = json.loads(result)
    assert parsed[0]["error_type"] == "NPE"


def test_parse_valid_json():
    content = '[{"error_type": "Timeout", "severity": "critical", "count": 3, "root_cause": "DB pool exhausted", "suggested_fix": "Increase pool size", "example_line": "ERROR timeout"}]'
    result = parse_groq_response(content)
    assert result is not None
    assert len(result) == 1
    assert result[0]["error_type"] == "Timeout"


def test_parse_empty_array():
    result = parse_groq_response("[]")
    assert result == []


def test_parse_invalid_json_returns_none():
    result = parse_groq_response("not json at all", retries=1)
    assert result is None


def test_parse_markdown_wrapped_json():
    content = "```json\n[]\n```"
    result = parse_groq_response(content)
    assert result == []
