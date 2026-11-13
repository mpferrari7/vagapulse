import pytest
from fastapi.testclient import TestClient

from app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'test.db'}")
    with TestClient(app) as test_client:
        yield test_client


def create_application(client, **overrides):
    data = {
        "company": "Acme",
        "role": "Software Engineer Intern",
        "source": "Careers page",
        "applied_on": "2026-10-01",
    }
    data.update(overrides)
    return client.post("/applications", json=data)


def test_create_normalizes_fields_and_lists_results(client):
    response = create_application(client, company="  Acme  ")

    assert response.status_code == 201
    assert response.json()["company"] == "Acme"
    assert response.json()["stage"] == "saved"

    listing = client.get("/applications", params={"q": "software", "page_size": 5})
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["role"] == "Software Engineer Intern"


def test_stage_transitions_reject_skipping_steps(client):
    application_id = create_application(client).json()["id"]

    invalid = client.patch(
        f"/applications/{application_id}/stage",
        json={"stage": "offer"},
    )
    assert invalid.status_code == 409

    applied = client.patch(
        f"/applications/{application_id}/stage",
        json={"stage": "applied"},
    )
    assert applied.status_code == 200
    assert applied.json()["stage"] == "applied"


def test_analytics_and_csv_export(client):
    create_application(client)
    response = client.get("/analytics")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["awaiting_response"] == 1

    export = client.get("/applications/export.csv")
    assert export.status_code == 200
    assert "company,role,source,applied_on,stage" in export.text
    assert "Acme,Software Engineer Intern,Careers page,2026-10-01,saved" in export.text


def test_invalid_date_and_blank_required_fields_are_rejected(client):
    invalid_date = create_application(client, applied_on="not-a-date")
    blank_company = create_application(client, company="   ")
    skipped_stage = create_application(client, stage="offer")

    assert invalid_date.status_code == 422
    assert blank_company.status_code == 422
    assert skipped_stage.status_code == 422


def test_csv_export_escapes_spreadsheet_formulas(client):
    create_application(client, company="=1+1")

    export = client.get("/applications/export.csv")

    assert export.status_code == 200
    assert "'=1+1" in export.text
