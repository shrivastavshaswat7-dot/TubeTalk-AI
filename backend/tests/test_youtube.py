from unittest.mock import MagicMock, patch

import pytest
import requests

from app.core.errors import AppError
from app.services.youtube import extract_video_id, fetch_metadata

VID = "jNQXAC9IVRw"


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.youtube.com/watch?v={VID}",
        f"https://youtube.com/watch?v={VID}&t=30s",
        f"https://www.youtube.com/watch?feature=share&v={VID}",
        f"https://m.youtube.com/watch?v={VID}",
        f"https://youtu.be/{VID}",
        f"https://youtu.be/{VID}?si=abc",
        f"https://www.youtube.com/embed/{VID}",
        f"https://www.youtube.com/shorts/{VID}",
        f"https://www.youtube.com/live/{VID}",
        f"www.youtube.com/watch?v={VID}",
        f"  https://youtu.be/{VID}  ",
    ],
)
def test_extract_video_id_valid(url):
    assert extract_video_id(url) == VID


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        None,
        "not a url",
        "https://example.com/watch?v=jNQXAC9IVRw",
        "https://evil.com/?u=youtube.com/watch?v=jNQXAC9IVRw",
        "https://www.youtube.com/watch",
        "https://www.youtube.com/watch?v=short",
        "https://www.youtube.com/watch?v=jNQXAC9IVRw12345",
        "https://www.youtube.com/playlist?list=PL1234567890A",
        "ftp://youtu.be/jNQXAC9IVRw",
    ],
)
def test_extract_video_id_invalid(url):
    with pytest.raises(AppError) as exc:
        extract_video_id(url)
    assert exc.value.error == "INVALID_VIDEO_URL"
    assert exc.value.status_code == 400


def _response(status=200, json_data=None, ok=True):
    r = MagicMock()
    r.status_code = status
    r.ok = ok
    r.json.return_value = json_data
    return r


def test_fetch_metadata_success():
    data = {"title": "Me at the zoo", "author_name": "jawed", "thumbnail_url": "http://t/img.jpg"}
    with patch("app.services.youtube.requests.get", return_value=_response(json_data=data)):
        meta = fetch_metadata(VID)
    assert meta.title == "Me at the zoo"
    assert meta.channel_name == "jawed"
    assert meta.thumbnail_url == "http://t/img.jpg"
    assert meta.youtube_url.endswith(VID)


@pytest.mark.parametrize(
    "status,code",
    [(404, "VIDEO_NOT_FOUND"), (401, "VIDEO_RESTRICTED"), (403, "VIDEO_RESTRICTED"), (500, "NETWORK_ERROR")],
)
def test_fetch_metadata_http_errors(status, code):
    with patch(
        "app.services.youtube.requests.get", return_value=_response(status, ok=status < 400)
    ):
        with pytest.raises(AppError) as exc:
            fetch_metadata(VID)
    assert exc.value.error == code


def test_fetch_metadata_network_failure():
    with patch("app.services.youtube.requests.get", side_effect=requests.ConnectionError()):
        with pytest.raises(AppError) as exc:
            fetch_metadata(VID)
    assert exc.value.error == "NETWORK_ERROR" and exc.value.status_code == 503
