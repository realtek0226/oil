from datetime import date

from app.clients.jlc_refined_oil_client import JlcRefinedOilClient


def test_parse_archive_page_uses_real_article_anchor() -> None:
    client = JlcRefinedOilClient()
    html = """
    <html>
      <body>
        <ul class="list list14time bord_botdes">
          <li>
            <span class="fr">2026-05-29</span>·
            <a href="javascript:void(0);"><span>[汽柴油]</span></a>
            <a href="/infodetail/i21471273_p001002_c001015.html" title="山东地炼汽柴油价格汇总表（20260529）">
              山东地炼汽柴油价格汇总表（20260529）
            </a>
          </li>
        </ul>
      </body>
    </html>
    """

    items = client._parse_archive_page(html, base_url="https://oil.315i.com/cmlc/Nav-001002001-qcy")

    assert len(items) == 1
    assert items[0]["headline"] == "山东地炼汽柴油价格汇总表（20260529）"
    assert items[0]["publish_date"] == date(2026, 5, 29).isoformat()
    assert items[0]["url"].endswith("/infodetail/i21471273_p001002_c001015.html")
