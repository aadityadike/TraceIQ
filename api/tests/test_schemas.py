from uuid import uuid4
from datetime import datetime, timezone
from schemas.log_job import LogIngestRequest, LogJobDetailResponse, ErrorPatternSchema


def test_ingest_request_requires_raw_log():
    req = LogIngestRequest(raw_log="ERROR: something failed", source="auth-api")
    assert req.raw_log == "ERROR: something failed"
    assert req.source == "auth-api"


def test_ingest_request_source_optional():
    req = LogIngestRequest(raw_log="some log")
    assert req.source is None


def test_log_job_detail_maps_id_to_job_id():
    # Simulates how FastAPI maps ORM object to response schema
    class FakeJob:
        id = uuid4()
        status = "completed"
        source = "payment-service"
        error_count = 3
        created_at = datetime.now(timezone.utc)
        updated_at = datetime.now(timezone.utc)
        patterns = []

    response = LogJobDetailResponse.model_validate(FakeJob(), from_attributes=True)
    assert response.job_id == FakeJob.id
    assert response.status == "completed"
