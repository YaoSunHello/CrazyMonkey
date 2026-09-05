from __future__ import annotations

import pytest

from app.relay.utils import spreadsheet_literal


@pytest.mark.parametrize(
    "untrusted",
    [
        "=2+3",
        "+SUM(1,2)",
        "-1+2",
        "@SUM(1,2)",
        "   =2+3",
        "\t+SUM(1,2)",
        "\r-1+2",
        "\n@SUM(1,2)",
        "\ufeff=2+3",
        " \t\r\n\ufeff@SUM(1,2)",
    ],
)
def test_untrusted_spreadsheet_prefixes_are_escaped(untrusted: str) -> None:
    escaped = spreadsheet_literal(untrusted)

    assert escaped == "'" + untrusted


@pytest.mark.parametrize("benign", ["LP03", "Management fee", "1.5%", "", None])
def test_benign_spreadsheet_text_is_unchanged(benign: str | None) -> None:
    assert spreadsheet_literal(benign) == ("" if benign is None else benign)
