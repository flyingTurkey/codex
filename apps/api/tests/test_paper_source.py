import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from srbg_api.acquisition.contracts import FetchResult, SourceCheckpoint
from srbg_api.papers.parser import parse_openalex_work
from srbg_api.papers.source import CrossrefPaperAdapter, OpenAlexPaperAdapter


class RecordingClient:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = list(responses)
        self.urls: list[str] = []
        self.accepts: list[str] = []

    async def get(
        self, url: str, *, checkpoint: SourceCheckpoint, accept: str = "text/html"
    ) -> FetchResult:
        self.urls.append(url)
        self.accepts.append(accept)
        payload = self.responses.pop(0)
        return FetchResult(
            url=url,
            status_code=200,
            content=json.dumps(payload).encode(),
            content_type="application/json",
            etag=None,
            last_modified=None,
            fetched_at=datetime(2026, 7, 15, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_openalex_uses_cursor_json_field_selection_and_server_secret() -> None:
    client = RecordingClient(
        [{"meta": {"next_cursor": "next-page"}, "results": [{"id": "W1", "title": "桥梁"}]}]
    )
    adapter = OpenAlexPaperAdapter(client=client, api_key="test-secret", contact="data@srbg.local")

    batch = await adapter.discover(SourceCheckpoint())

    assert batch.next_checkpoint.cursor == "next-page"
    assert batch.records[0].external_id == "W1"
    assert "cursor=%2A" in client.urls[0]
    assert "per-page=100" in client.urls[0]
    assert "select=" in client.urls[0]
    assert "api_key=test-secret" in client.urls[0]
    assert client.accepts == ["application/json"]


@pytest.mark.asyncio
async def test_openalex_requires_api_key_and_stops_on_null_cursor() -> None:
    with pytest.raises(RuntimeError, match="OPENALEX_API_KEY"):
        await OpenAlexPaperAdapter(client=RecordingClient([]), api_key=None).discover(
            SourceCheckpoint()
        )

    client = RecordingClient([{"meta": {"next_cursor": None}, "results": []}])
    batch = await OpenAlexPaperAdapter(client=client, api_key="secret").discover(
        SourceCheckpoint(cursor="last")
    )
    assert batch.records == ()
    assert batch.next_checkpoint.cursor is None


@pytest.mark.asyncio
async def test_crossref_lookup_normalizes_doi_and_extracts_update_candidates() -> None:
    client = RecordingClient(
        [
            {
                "message": {
                    "DOI": "10.1000/ABC",
                    "title": ["桥梁论文"],
                    "update-to": [
                        {
                            "DOI": "10.1000/OLD",
                            "type": "retraction",
                            "updated": {"date-time": "2026-01-01T00:00:00Z"},
                        }
                    ],
                }
            }
        ]
    )
    result = await CrossrefPaperAdapter(client=client, contact="data@srbg.local").lookup(
        "https://doi.org/10.1000/ABC"
    )
    assert result.doi == "10.1000/abc"
    assert result.relations[0].relation_type == "RETRACTS"
    assert result.relations[0].target_doi == "10.1000/old"
    assert "mailto=data%40srbg.local" in client.urls[0]


def test_openalex_parser_projects_complete_metadata_without_reconstructing_abstract() -> None:
    payload = json.loads(
        (Path("apps/api/tests/fixtures/round06/openalex-page1.json")).read_text(encoding="utf-8")
    )["results"][0]
    paper = parse_openalex_work(payload, abstract_licensed=False, fulltext_licensed=False)
    assert paper.doi == "10.1000/bridge.2025.1"
    assert paper.journal == "Journal of Highway and Transportation Research"
    assert paper.issns == ("1001-7372",)
    assert paper.authors[0].name == "Zhang San"
    assert paper.authors[0].institutions == ("Southwest Jiaotong University",)
    assert paper.volume == "38" and paper.issue == "7" and paper.year == 2025
    assert paper.keywords == ("digital twin", "bridge monitoring")
    assert paper.abstract is None
    assert paper.access_level == "METADATA_ONLY"
    assert paper.open_fulltext_url is None
