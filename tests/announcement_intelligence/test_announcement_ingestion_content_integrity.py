from __future__ import annotations

import json
from urllib.error import URLError
from pathlib import Path
from typing import Mapping

import pandas as pd

import quantpilot_core.announcement_intelligence.ingestion as ingestion_module
from quantpilot_core.announcement_intelligence import (
    enrich_announcement_content,
    fetch_akshare_announcement_events,
    normalize_a_share_announcement_events,
    write_announcement_ingestion_artifacts,
)
from quantpilot_core.quant_firm import DeepSeekAdvisoryOutput, DeepSeekAdvisoryRole
from quantpilot_core.real_data_provider import (
    ProviderName,
    TradingCalendar,
    calendar_to_announcement_trading_calendar,
)


def provider_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "代码": "000001",
                "名称": "平安银行",
                "公告标题": "董事会决议公告",
                "公告类型": "重大事项",
                "公告日期": "2026-01-02",
                "网址": "https://example.test/news/AN202601020001",
            },
            {
                "代码": "000001",
                "名称": "平安银行",
                "公告标题": "董事会决议公告",
                "公告类型": "重大事项",
                "公告日期": "2026-01-02",
                "网址": "https://example.test/news/AN202601020001",
            },
            {
                "代码": "600000",
                "名称": "浦发银行",
                "公告标题": "关于诉讼事项的公告",
                "公告内容": "公司收到法院通知，案件仍在审理阶段。公司将持续履行信息披露义务。",
                "公告类型": "诉讼",
                "公告日期": "2026-01-02 10:15:00",
                "网址": "https://example.test/news/AN202601020002",
            },
        ]
    )


class FakeAkShareAnnouncementClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def stock_individual_notice_report(self, *, security: str, symbol: str, begin_date: str, end_date: str) -> pd.DataFrame:
        self.calls.append({"security": security, "symbol": symbol, "begin_date": begin_date, "end_date": end_date})
        if security == "600309":
            raise KeyError("代码")
        if security == "600000":
            raise RuntimeError("fixture provider failure")
        return pd.DataFrame(
            [
                {
                    "代码": security,
                    "公告标题": "年度权益分派实施公告",
                    "公告类型": "分红",
                    "公告日期": "2026-01-02",
                    "网址": f"https://example.test/{security}/AN1",
                },
                {
                    "代码": security,
                    "公告标题": "年度权益分派实施公告",
                    "公告类型": "分红",
                    "公告日期": "2026-01-02",
                    "网址": f"https://example.test/{security}/AN1",
                },
            ]
        )

    def stock_notice_report_detail(self, identifier: str) -> dict[str, object]:
        return {
            "content_source": "provider_summary",
            "summary": f"provider summary for {identifier}",
        }


class FakeSchemaClient:
    def __init__(self, frames: Mapping[str, pd.DataFrame]) -> None:
        self.frames = dict(frames)
        self.calls: list[dict[str, str]] = []

    def stock_individual_notice_report(self, *, security: str, symbol: str, begin_date: str, end_date: str) -> pd.DataFrame:
        self.calls.append({"security": security, "symbol": symbol, "begin_date": begin_date, "end_date": end_date})
        return self.frames.get(security, pd.DataFrame())

    def stock_notice_report_detail(self, identifier: str) -> dict[str, object]:
        return {"content_source": "provider_summary", "summary": f"summary for {identifier}"}


def body_like_text() -> str:
    return (
        "公司董事会于2026年1月2日审议通过年度权益分派方案。"
        "本次利润分配以实施权益分派股权登记日总股本为基数，向全体股东每10股派发现金红利。"
        "公司将按照交易所相关规则及时披露实施进展。"
    )


def eastmoney_chrome_text() -> str:
    return """
    东方财富网 > 数据中心 > 公告大全 > 公司公告正文
    行情中心 Choice数据 龙虎榜单 融资融券 股权质押 大宗交易 条件选股
    查看PDF原文 当前第 1 页 上一页 下一页 共 页
    [点击查看PDF原文]
    郑重声明：本网不保证其真实性和客观性，一切有关该股的有效信息，以交易所的公告为准。
    扫一扫下载APP 版权所有 沪ICP备05006054号 沪公网安备
    """


def mixed_page_text() -> str:
    return (
        "东方财富网 > 数据中心 > 公告大全\n"
        "查看PDF原文 上一页 下一页\n"
        + body_like_text()
        + "\n郑重声明：相关信息不构成投资建议。 沪ICP备05006054号"
    )


def eastmoney_detail_chrome_text() -> str:
    return (
        "财经 焦点 股票 新股 期指 期权 行情 数据 全球 美股 港股 期货 外汇 黄金 "
        "银行 基金 理财 保险 债券 视频 基金吧 全球财经快讯 "
        "ST美晨 ST美晨-公告正文 ST美晨(300237) 公告正文 "
        "重要股东股权质押数据全览 点击查看ST美晨更多公告 - 公告日期： - 共 页 "
        "郑重声明：本网不保证其真实性和客观性，一切有关该股的有效信息，以交易所的公告为准。"
    )


def generic_provider_shell_that_collapses_after_cleaning() -> str:
    line = (
        " 页面展示若干通用栏目说明和行情入口提示，文字长度较长并带有句号用于模拟网页外壳，"
        "继续补充足够多的普通描述字符避免短行过滤。"
    )
    return "\n".join(("东方财富" + line, "数据中心" + line, "全球财经快讯" + line))


def test_provider_rows_bare_codes_dedupe_and_date_only_pit() -> None:
    events = normalize_a_share_announcement_events(
        provider_rows(),
        ingestion_time="2026-01-03T00:00:00",
        trading_calendar=("2026-01-05", "2026-01-06"),
    )

    assert len(events) == 2
    sz_event = events.loc[events["affected_symbols"].map(lambda symbols: symbols == ("000001.SZ",))].iloc[0]
    sh_event = events.loc[events["affected_symbols"].map(lambda symbols: symbols == ("600000.SH",))].iloc[0]
    assert sh_event["publish_time_precision"] == "datetime"
    assert sz_event["publish_time_precision"] == "date"
    assert sz_event["first_available_time"] == "2026-01-05T09:30:00"
    assert sz_event["content_source"] == "title_fallback"
    assert sz_event["content_quality_status"] == "title_fallback"
    assert sz_event["content_quality_reason"] == "title_only_fallback"
    assert bool(sz_event["full_text_available"]) is False
    assert events["deduplication_key"].is_unique


def test_real_calendar_injection_skips_weekday_holiday() -> None:
    calendar = TradingCalendar(
        sessions=(pd.Timestamp("2026-01-05").date(), pd.Timestamp("2026-01-06").date()),
        provider=ProviderName.TUSHARE,
    )
    rows = provider_rows().copy()
    rows.loc[0, "公告日期"] = "2026-01-01"

    events = normalize_a_share_announcement_events(
        rows.iloc[[0]],
        ingestion_time="2026-01-03T00:00:00",
        trading_calendar=calendar_to_announcement_trading_calendar(calendar),
    )

    assert events.iloc[0]["first_available_time"] == "2026-01-05T09:30:00"


def test_genuine_body_like_text_classified_as_full_text(tmp_path: Path) -> None:
    events = normalize_a_share_announcement_events(provider_rows().iloc[[0]], ingestion_time="2026-01-03T00:00:00")

    enriched = enrich_announcement_content(
        events,
        detail_fetcher=lambda event: {"content_source": "full_text", "full_text": body_like_text()},
        cache_dir=tmp_path,
    )

    assert enriched.loc[0, "content_source"] == "full_text"
    assert enriched.loc[0, "content_quality_status"] == "usable_full_text"
    assert enriched.loc[0, "content_quality_reason"] == "body_like_text_detected"
    assert bool(enriched.loc[0, "full_text_available"]) is True
    assert enriched.loc[0, "content_quality_evidence"]["retained_char_count"] >= 80
    assert enriched.loc[0, "content_cache_schema_version"] == "announcement_content_cache_v2"


def test_title_content_english_wrapper_duplicate_is_title_fallback(tmp_path: Path) -> None:
    title = "美晨科技:2024年度业绩预告"
    events = normalize_a_share_announcement_events(
        provider_rows().iloc[[0]].assign(公告标题=title),
        ingestion_time="2026-01-03T00:00:00",
    )

    enriched = enrich_announcement_content(
        events,
        detail_fetcher=lambda event: {"content_source": "full_text", "content": f"Title: {title}\nContent: {title}"},
        cache_dir=tmp_path,
    )

    assert enriched.loc[0, "content_source"] == "title_fallback"
    assert enriched.loc[0, "content_quality_status"] == "title_fallback"
    assert enriched.loc[0, "content_quality_reason"] == "title_only_duplicate_body"
    assert bool(enriched.loc[0, "full_text_available"]) is False
    assert enriched.loc[0, "content_quality_evidence"]["title_only_duplicate_body"] is True
    assert enriched.loc[0, "content_quality_evidence"]["classifier_version"] == "announcement_body_quality_v3"
    assert "title_only_duplicate_body" in enriched.loc[0, "data_quality_flags"]


def test_title_content_chinese_wrapper_duplicate_is_title_fallback(tmp_path: Path) -> None:
    title = "美晨科技:2024年度业绩预告"
    events = normalize_a_share_announcement_events(
        provider_rows().iloc[[0]].assign(公告标题=title),
        ingestion_time="2026-01-03T00:00:00",
    )

    enriched = enrich_announcement_content(
        events,
        detail_fetcher=lambda event: {"content_source": "full_text", "content": f"标题：{title}\n内容：{title}"},
        cache_dir=tmp_path,
    )

    assert enriched.loc[0, "content_source"] == "title_fallback"
    assert enriched.loc[0, "content_quality_reason"] == "title_only_duplicate_body"
    assert bool(enriched.loc[0, "full_text_available"]) is False


def test_repeated_title_with_whitespace_punctuation_is_title_fallback(tmp_path: Path) -> None:
    title = "美晨科技:2024年度业绩预告"
    events = normalize_a_share_announcement_events(
        provider_rows().iloc[[0]].assign(公告标题=title),
        ingestion_time="2026-01-03T00:00:00",
    )

    enriched = enrich_announcement_content(
        events,
        detail_fetcher=lambda event: {"content_source": "full_text", "content": f"  {title}  \n；{title}。 \n {title} "},
        cache_dir=tmp_path,
    )

    assert enriched.loc[0, "content_source"] == "title_fallback"
    assert enriched.loc[0, "content_quality_reason"] == "title_only_duplicate_body"


def test_title_with_trivial_metadata_only_is_title_fallback(tmp_path: Path) -> None:
    title = "美晨科技:2024年度业绩预告"
    events = normalize_a_share_announcement_events(
        provider_rows().iloc[[0]].assign(公告标题=title),
        ingestion_time="2026-01-03T00:00:00",
    )

    enriched = enrich_announcement_content(
        events,
        detail_fetcher=lambda event: {
            "content_source": "full_text",
            "content": f"标题：{title}\n公告日期：2025-01-20\n证券代码：300237\n内容：{title}",
        },
        cache_dir=tmp_path,
    )

    assert enriched.loc[0, "content_source"] == "title_fallback"
    assert enriched.loc[0, "content_quality_reason"] == "title_only_duplicate_body"
    assert bool(enriched.loc[0, "full_text_available"]) is False


def test_title_then_multiple_sentence_body_remains_full_text(tmp_path: Path) -> None:
    title = "美晨科技:2024年度业绩预告"
    body = (
        f"标题：{title}\n内容：{title}\n"
        "公司预计2024年度归属于上市公司股东的净利润较上年同期明显改善，主要原因是主营业务订单交付增加。"
        "报告期内公司持续推进降本增效，期间费用有所下降，现金流状况保持稳定。"
        "本公告所载财务数据为初步测算结果，具体数据以年度报告披露为准。"
    )
    events = normalize_a_share_announcement_events(
        provider_rows().iloc[[0]].assign(公告标题=title),
        ingestion_time="2026-01-03T00:00:00",
    )

    enriched = enrich_announcement_content(
        events,
        detail_fetcher=lambda event: {"content_source": "full_text", "content": body},
        cache_dir=tmp_path,
    )

    assert enriched.loc[0, "content_source"] == "full_text"
    assert enriched.loc[0, "content_quality_status"] == "usable_full_text"
    assert bool(enriched.loc[0, "full_text_available"]) is True


def test_genuine_body_containing_title_once_is_not_rejected(tmp_path: Path) -> None:
    title = "董事会决议公告"
    body = (
        "董事会决议公告显示，公司于2026年1月召开董事会会议，审议通过年度经营计划和内部控制改进方案。"
        "会议同意继续推进重点项目建设，并要求管理层按季度披露项目进展和资金使用情况。"
        "独立董事对相关事项发表明确意见，认为决策程序符合公司章程和监管要求。"
    )
    events = normalize_a_share_announcement_events(
        provider_rows().iloc[[0]].assign(公告标题=title),
        ingestion_time="2026-01-03T00:00:00",
    )

    enriched = enrich_announcement_content(
        events,
        detail_fetcher=lambda event: {"content_source": "full_text", "content": body},
        cache_dir=tmp_path,
    )

    assert enriched.loc[0, "content_source"] == "full_text"
    assert enriched.loc[0, "content_quality_status"] == "usable_full_text"
    assert enriched.loc[0, "content_quality_evidence"]["title_only_duplicate_body"] is False


def test_generic_shell_cannot_transfer_full_text_quality_to_title_only_content(tmp_path: Path) -> None:
    title = "美晨科技:2024年度业绩预告"
    events = normalize_a_share_announcement_events(
        provider_rows().iloc[[0]].assign(公告标题=title),
        ingestion_time="2026-01-03T00:00:00",
    )

    enriched = enrich_announcement_content(
        events,
        detail_fetcher=lambda event: {
            "content_source": "full_text",
            "content": generic_provider_shell_that_collapses_after_cleaning(),
        },
        cache_dir=tmp_path,
    )
    content = enriched.loc[0, "content"]

    assert enriched.loc[0, "content_source"] == "title_fallback"
    assert enriched.loc[0, "content_quality_status"] == "title_fallback"
    assert enriched.loc[0, "content_quality_reason"] == "persisted_content_lacks_validated_body"
    assert bool(enriched.loc[0, "full_text_available"]) is False
    assert content == f"Title: {title}\nContent: {title}"
    assert enriched.loc[0, "content_char_count"] == len(content)
    assert enriched.loc[0, "content_hash"] == ingestion_module._content_hash(content)
    assert enriched.loc[0, "content_quality_evidence"]["raw_page_quality_reason"] == "body_survived_boilerplate_removal"


def test_genuine_body_is_persisted_as_advisory_content(tmp_path: Path) -> None:
    from quantpilot_core.announcement_intelligence import assess_announcement_event_with_deepseek

    class RecordingAgent:
        def __init__(self) -> None:
            self.summary = None

        def advise(self, advisory_input):
            self.summary = advisory_input.information_agent_summary
            return DeepSeekAdvisoryOutput(
                role=DeepSeekAdvisoryRole.INFORMATION_DESK,
                advisory_summary='{"direction":"positive","horizon":"short_term","severity":0.4,"confidence":0.6,"evidence":["body"],"rationale":"body","limitations":["fixture"]}',
                evidence_used=("information_agent_summary",),
                failure_explanation="fixture",
                strategy_mutation_rationale="fixture",
                parameter_tuning_suggestions=(),
                research_directions=(),
                regime_notes=(),
                risk_notes=(),
                tool_integration_notes=(),
                confidence=0.6,
                used_model="fixture",
                is_fallback=False,
                raw_model_response='{"direction":"positive","horizon":"short_term","severity":0.4,"confidence":0.6,"evidence":["body"],"rationale":"body","limitations":["fixture"]}',
            )

    events = normalize_a_share_announcement_events(provider_rows().iloc[[0]], ingestion_time="2026-01-03T00:00:00")
    enriched = enrich_announcement_content(
        events,
        detail_fetcher=lambda event: {"content_source": "full_text", "content": body_like_text()},
        cache_dir=tmp_path,
    )
    agent = RecordingAgent()
    assess_announcement_event_with_deepseek(enriched.iloc[0].to_dict(), advisory_agent=agent)

    assert enriched.loc[0, "content_source"] == "full_text"
    assert "年度权益分派方案" in enriched.loc[0, "content"]
    assert agent.summary["evidence_text"] == enriched.loc[0, "content"]


def test_repeated_generic_shell_across_distinct_events_is_not_usable_full_text(tmp_path: Path) -> None:
    rows = provider_rows().iloc[[0, 2]].copy()
    rows.loc[rows.index[0], "公告标题"] = "美晨科技:2024年度业绩预告"
    rows.loc[rows.index[0], "网址"] = "https://example.test/news/AN-shell-1"
    rows.loc[rows.index[1], "公告标题"] = "美晨科技:关于累计诉讼、仲裁及进展情况的公告"
    rows.loc[rows.index[1], "网址"] = "https://example.test/news/AN-shell-2"
    events = normalize_a_share_announcement_events(rows, ingestion_time="2026-01-03T00:00:00")

    enriched = enrich_announcement_content(
        events,
        detail_fetcher=lambda event: {
            "content_source": "full_text",
            "content": generic_provider_shell_that_collapses_after_cleaning(),
        },
        cache_dir=tmp_path,
    )

    assert set(enriched["content_source"]) == {"title_fallback"}
    assert set(enriched["content_quality_reason"]) == {"persisted_content_lacks_validated_body"}
    assert bool(enriched["full_text_available"].any()) is False


def test_distinct_genuine_bodies_remain_usable_full_text(tmp_path: Path) -> None:
    rows = provider_rows().iloc[[0, 2]].copy()
    rows.loc[rows.index[0], "公告标题"] = "年度权益分派实施公告"
    rows.loc[rows.index[0], "网址"] = "https://example.test/news/AN-body-1"
    rows.loc[rows.index[1], "公告标题"] = "关于诉讼事项的公告"
    rows.loc[rows.index[1], "网址"] = "https://example.test/news/AN-body-2"
    events = normalize_a_share_announcement_events(rows, ingestion_time="2026-01-03T00:00:00")
    bodies = {
        "年度权益分派实施公告": body_like_text(),
        "关于诉讼事项的公告": (
            "公司收到法院关于合同纠纷案件的受理通知，案件目前处于审理阶段，尚未形成生效判决。"
            "公司已组织法律顾问准备应诉材料，并将根据案件进展及时履行信息披露义务。"
            "本次诉讼暂未对公司日常经营造成重大不利影响，最终影响以法院裁判结果为准。"
        ),
    }

    enriched = enrich_announcement_content(
        events,
        detail_fetcher=lambda event: {"content_source": "full_text", "content": bodies[str(event["title"])]},
        cache_dir=tmp_path,
    )

    assert set(enriched["content_source"]) == {"full_text"}
    assert set(enriched["content_quality_status"]) == {"usable_full_text"}
    assert bool(enriched["full_text_available"].all()) is True


def test_eastmoney_navigation_footer_pdf_placeholder_downgraded(tmp_path: Path) -> None:
    events = normalize_a_share_announcement_events(provider_rows().iloc[[0]], ingestion_time="2026-01-03T00:00:00")

    enriched = enrich_announcement_content(
        events,
        detail_fetcher=lambda event: {"content_source": "full_text", "content": eastmoney_chrome_text()},
        cache_dir=tmp_path,
    )

    assert enriched.loc[0, "content_source"] == "title_fallback"
    assert enriched.loc[0, "content_quality_status"] == "title_fallback"
    assert enriched.loc[0, "content_quality_reason"] == "boilerplate_dominated_page"
    assert bool(enriched.loc[0, "full_text_available"]) is False
    assert "PDF原文" not in enriched.loc[0, "content"]


def test_mixed_page_keeps_real_body_after_boilerplate_removal(tmp_path: Path) -> None:
    events = normalize_a_share_announcement_events(provider_rows().iloc[[0]], ingestion_time="2026-01-03T00:00:00")

    enriched = enrich_announcement_content(
        events,
        detail_fetcher=lambda event: {"content_source": "full_text", "content": mixed_page_text()},
        cache_dir=tmp_path,
    )

    assert enriched.loc[0, "content_source"] == "full_text"
    assert enriched.loc[0, "content_quality_status"] == "usable_full_text"
    assert "年度权益分派方案" in enriched.loc[0, "content"]
    assert "东方财富网" not in enriched.loc[0, "content"]


def test_eastmoney_detail_shell_chrome_is_not_full_text(tmp_path: Path) -> None:
    events = normalize_a_share_announcement_events(provider_rows().iloc[[0]], ingestion_time="2026-01-03T00:00:00")

    enriched = enrich_announcement_content(
        events,
        detail_fetcher=lambda event: {"content_source": "full_text", "content": eastmoney_detail_chrome_text()},
        cache_dir=tmp_path,
    )

    assert enriched.loc[0, "content_source"] == "title_fallback"
    assert enriched.loc[0, "content_quality_status"] == "title_fallback"
    assert enriched.loc[0, "content_quality_reason"] == "boilerplate_dominated_page"
    assert bool(enriched.loc[0, "full_text_available"]) is False
    assert "全球财经快讯" not in enriched.loc[0, "content"]


def test_certificate_failure_falls_back_to_requests_and_still_classifies_body(tmp_path: Path, monkeypatch) -> None:
    events = normalize_a_share_announcement_events(provider_rows().iloc[[0]], ingestion_time="2026-01-03T00:00:00")
    calls = {"urllib": 0, "requests": 0}

    class FakeRequestModule:
        @staticmethod
        def Request(url: str, headers: Mapping[str, str]) -> Mapping[str, object]:
            return {"url": url, "headers": dict(headers)}

        @staticmethod
        def urlopen(request: Mapping[str, object], timeout: int) -> object:
            calls["urllib"] += 1
            raise URLError("CERTIFICATE_VERIFY_FAILED: certificate verify failed")

    class FakeResponse:
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def iter_content(chunk_size: int):
            body = f"<html><body>{mixed_page_text()}</body></html>".encode("utf-8")
            yield body[:chunk_size]

    class FakeRequestsModule:
        @staticmethod
        def get(url: str, timeout: int, headers: Mapping[str, str], stream: bool, verify: object) -> FakeResponse:
            calls["requests"] += 1
            assert headers["User-Agent"]
            assert stream is True
            assert verify is not False
            return FakeResponse()

    class FakeCertifiModule:
        @staticmethod
        def where() -> str:
            return "/tmp/fake-certifi-ca.pem"

    real_import_module = ingestion_module.importlib.import_module

    def fake_import_module(name: str):
        if name == "urllib.request":
            return FakeRequestModule
        if name == "requests":
            return FakeRequestsModule
        if name == "certifi":
            return FakeCertifiModule
        return real_import_module(name)

    monkeypatch.setattr(ingestion_module.importlib, "import_module", fake_import_module)

    enriched = enrich_announcement_content(events, cache_dir=tmp_path)

    assert calls == {"urllib": 1, "requests": 1}
    assert enriched.loc[0, "content_retrieval_status"] == "retrieved"
    assert enriched.loc[0, "content_source"] == "full_text"
    assert enriched.loc[0, "content_quality_status"] == "usable_full_text"
    assert "东方财富网" not in enriched.loc[0, "content"]


def test_url_body_download_is_bounded(monkeypatch) -> None:
    body = b"x" * (ingestion_module.MAX_DETAIL_RESPONSE_BYTES + 100)

    class FakeResponse:
        def read(self, size: int) -> bytes:
            assert size == ingestion_module.MAX_DETAIL_RESPONSE_BYTES + 1
            return body[:size]

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

    class FakeRequestModule:
        @staticmethod
        def Request(url: str, headers: Mapping[str, str]) -> Mapping[str, object]:
            return {"url": url, "headers": dict(headers)}

        @staticmethod
        def urlopen(request: Mapping[str, object], timeout: int) -> FakeResponse:
            return FakeResponse()

    real_import_module = ingestion_module.importlib.import_module

    def fake_import_module(name: str):
        if name == "urllib.request":
            return FakeRequestModule
        return real_import_module(name)

    monkeypatch.setattr(ingestion_module.importlib, "import_module", fake_import_module)

    detail = ingestion_module._fetch_url_text("https://example.test/announcement.html")

    assert len(detail["content"]) == ingestion_module.MAX_DETAIL_RESPONSE_BYTES


def test_provider_summary_and_failed_body_retrieval_are_honest(tmp_path: Path) -> None:
    events = normalize_a_share_announcement_events(provider_rows().iloc[:2], ingestion_time="2026-01-03T00:00:00")

    summary = enrich_announcement_content(
        events.iloc[[0]],
        detail_fetcher=lambda event: {"content_source": "provider_summary", "summary": "供应商摘要显示公司披露分红实施安排。"},
        cache_dir=tmp_path / "summary",
    )
    failed = enrich_announcement_content(
        events.iloc[[0]],
        detail_fetcher=lambda event: (_ for _ in ()).throw(RuntimeError("detail unavailable")),
        cache_dir=tmp_path / "failed",
    )

    assert summary.loc[0, "content_source"] == "provider_summary"
    assert summary.loc[0, "content_quality_status"] == "usable_provider_summary"
    assert bool(summary.loc[0, "full_text_available"]) is False
    assert failed.loc[0, "content_source"] == "title_fallback"
    assert failed.loc[0, "content_retrieval_error"].startswith("RuntimeError")
    assert "content_retrieval_failed" in failed.loc[0, "data_quality_flags"]


def test_old_low_quality_cache_is_revalidated_and_valid_cache_is_reused(tmp_path: Path) -> None:
    events = normalize_a_share_announcement_events(provider_rows().iloc[[0]], ingestion_time="2026-01-03T00:00:00")
    calls = 0

    first = enrich_announcement_content(
        events,
        detail_fetcher=lambda event: {"content_source": "full_text", "content": eastmoney_chrome_text()},
        cache_dir=tmp_path,
    )

    def fetcher(event: Mapping[str, object]) -> Mapping[str, object]:
        nonlocal calls
        calls += 1
        return {"content_source": "full_text", "content": body_like_text()}

    second = enrich_announcement_content(events, detail_fetcher=fetcher, cache_dir=tmp_path)
    assert calls == 0
    assert second.loc[0, "content_retrieval_status"] == "cache_hit"
    assert second.loc[0, "content_source"] == "title_fallback"
    assert second.loc[0, "content_quality_reason"] == "boilerplate_dominated_page"

    valid_cache = tmp_path / "valid"
    valid_first = enrich_announcement_content(events, detail_fetcher=fetcher, cache_dir=valid_cache)
    valid_second = enrich_announcement_content(events, detail_fetcher=fetcher, cache_dir=valid_cache)

    assert calls == 1
    assert first.loc[0, "content_hash"] == second.loc[0, "content_hash"]
    assert valid_first.loc[0, "content_source"] == "full_text"
    assert valid_second.loc[0, "content_retrieval_status"] == "cache_hit"
    assert valid_second.loc[0, "content_source"] == "full_text"


def test_cached_title_only_duplicate_payload_is_revalidated_and_downgraded(tmp_path: Path) -> None:
    title = "美晨科技:2024年度业绩预告"
    events = normalize_a_share_announcement_events(
        provider_rows().iloc[[0]].assign(公告标题=title),
        ingestion_time="2026-01-03T00:00:00",
    )
    calls = 0

    first = enrich_announcement_content(
        events,
        detail_fetcher=lambda event: {"content_source": "full_text", "content": f"Title: {title}\nContent: {title}"},
        cache_dir=tmp_path,
    )

    def fetcher(event: Mapping[str, object]) -> Mapping[str, object]:
        nonlocal calls
        calls += 1
        return {"content_source": "full_text", "content": body_like_text()}

    second = enrich_announcement_content(events, detail_fetcher=fetcher, cache_dir=tmp_path)

    assert calls == 0
    assert first.loc[0, "content_source"] == "title_fallback"
    assert second.loc[0, "content_retrieval_status"] == "cache_hit"
    assert second.loc[0, "content_source"] == "title_fallback"
    assert second.loc[0, "content_quality_reason"] == "title_only_duplicate_body"
    assert bool(second.loc[0, "full_text_available"]) is False


def test_600309_empty_response_does_not_collapse_valid_batch(tmp_path: Path) -> None:
    client = FakeAkShareAnnouncementClient()

    events = fetch_akshare_announcement_events(
        symbols=("000001.SZ", "600309.SH", "600000.SH"),
        start_date="2026-01-01",
        end_date="2026-01-31",
        akshare_client=client,
        content_cache_dir=tmp_path,
    )
    report = events.attrs["run_report"]
    statuses = {item["symbol"]: item for item in report["symbol_request_statuses"]}

    assert [call["security"] for call in client.calls] == ["000001", "600309", "600000"]
    assert len(events) == 1
    assert events.loc[0, "affected_symbols"] == ("000001.SZ",)
    assert report["run_status"] == "partial"
    assert report["request_count"] == 3
    assert report["successful_request_count"] == 2
    assert report["empty_response_count"] == 1
    assert report["failed_request_count"] == 1
    assert statuses["600309.SH"]["status"] == "empty"
    assert statuses["600309.SH"]["reason"] == "provider_empty_response"
    assert statuses["600309.SH"]["diagnostic"] == "akshare_empty_result_keyerror_code_column"
    assert statuses["600000.SH"]["status"] == "failed"
    assert statuses["600000.SH"]["reason"] == "provider_connection_error"
    assert not events["affected_symbols"].map(lambda symbols: "600309.SH" in symbols).any()


def test_actual_akshare_schema_fetches_and_filters_without_network(tmp_path: Path) -> None:
    client = FakeSchemaClient(
        {
            "300750": pd.DataFrame(
                [
                    {
                        "代码": "300750",
                        "名称": "宁德时代",
                        "公告标题": "关于回购股份事项的公告",
                        "公告类型": "重大事项",
                        "公告日期": "2025-10-31",
                        "网址": "https://data.eastmoney.com/notices/detail/300750/AN1.html",
                    }
                ]
            )
        }
    )

    events = fetch_akshare_announcement_events(
        symbols=("300750.SZ",),
        start_date="2025-10-31",
        end_date="2025-10-31",
        akshare_client=client,
        content_cache_dir=tmp_path,
    )

    assert [call["security"] for call in client.calls] == ["300750"]
    assert len(events) == 1
    assert events.loc[0, "affected_symbols"] == ("300750.SZ",)
    assert events.attrs["run_report"]["run_status"] == "completed"


def test_supported_provider_alias_schema_is_normalized(tmp_path: Path) -> None:
    client = FakeSchemaClient(
        {
            "000001": pd.DataFrame(
                [
                    {
                        "stock_code": "000001",
                        "short_name": "平安银行",
                        "title": "关于董事会会议决议的公告",
                        "column_name": "重大事项",
                        "notice_date": "2025-10-31",
                        "url": "https://data.eastmoney.com/notices/detail/000001/AN1.html",
                    }
                ]
            )
        }
    )

    events = fetch_akshare_announcement_events(
        symbols=("000001.SZ",),
        start_date="2025-10-31",
        end_date="2025-10-31",
        akshare_client=client,
        content_cache_dir=tmp_path,
    )

    assert len(events) == 1
    assert events.loc[0, "affected_symbols"] == ("000001.SZ",)
    assert events.loc[0, "announcement_category"] == "重大事项"


def test_missing_required_code_column_is_schema_error_not_keyerror(tmp_path: Path) -> None:
    client = FakeSchemaClient(
        {
            "000001": pd.DataFrame(
                [
                    {
                        "名称": "平安银行",
                        "公告标题": "关于董事会会议决议的公告",
                        "公告日期": "2025-10-31",
                        "网址": "https://data.eastmoney.com/notices/detail/000001/AN1.html",
                    }
                ]
            )
        }
    )

    events = fetch_akshare_announcement_events(
        symbols=("000001.SZ",),
        start_date="2025-10-31",
        end_date="2025-10-31",
        akshare_client=client,
        content_cache_dir=tmp_path,
    )
    report = events.attrs["run_report"]
    statuses = {item["symbol"]: item for item in report["symbol_request_statuses"]}

    assert events.empty
    assert report["run_status"] == "failed"
    assert report["failed_request_count"] == 1
    assert statuses["000001.SZ"]["reason"] == "provider_schema_error"
    assert statuses["000001.SZ"]["missing_semantic_fields"] == ("代码",)
    assert "名称" in statuses["000001.SZ"]["observed_columns"]


def test_requested_symbol_not_present_does_not_collapse_valid_symbols(tmp_path: Path) -> None:
    client = FakeSchemaClient(
        {
            "000001": pd.DataFrame(
                [
                    {
                        "代码": "000001",
                        "公告标题": "关于董事会会议决议的公告",
                        "公告日期": "2025-10-31",
                        "网址": "https://data.eastmoney.com/notices/detail/000001/AN1.html",
                    }
                ]
            ),
            "600309": pd.DataFrame(
                [
                    {
                        "代码": "600000",
                        "公告标题": "关于利润分配事项的公告",
                        "公告日期": "2025-10-31",
                        "网址": "https://data.eastmoney.com/notices/detail/600000/AN1.html",
                    }
                ]
            ),
        }
    )

    events = fetch_akshare_announcement_events(
        symbols=("000001.SZ", "600309.SH"),
        start_date="2025-10-31",
        end_date="2025-10-31",
        akshare_client=client,
        content_cache_dir=tmp_path,
    )
    statuses = {item["symbol"]: item for item in events.attrs["run_report"]["symbol_request_statuses"]}

    assert len(events) == 1
    assert events.loc[0, "affected_symbols"] == ("000001.SZ",)
    assert statuses["600309.SH"]["reason"] == "requested_symbol_not_present"
    assert not events["affected_symbols"].map(lambda symbols: "600309.SH" in symbols).any()


def test_empty_dataframe_remains_provider_empty_response(tmp_path: Path) -> None:
    client = FakeSchemaClient({"600309": pd.DataFrame(columns=["代码", "公告标题", "公告日期", "网址"])})

    events = fetch_akshare_announcement_events(
        symbols=("600309.SH",),
        start_date="2025-10-31",
        end_date="2025-10-31",
        akshare_client=client,
        content_cache_dir=tmp_path,
    )
    status = events.attrs["run_report"]["symbol_request_statuses"][0]

    assert events.empty
    assert status["status"] == "empty"
    assert status["reason"] == "provider_empty_response"


def test_announcement_ingestion_artifacts_split_event_list_and_report_dict(tmp_path: Path) -> None:
    client = FakeAkShareAnnouncementClient()
    events = fetch_akshare_announcement_events(
        symbols=("000001.SZ",),
        start_date="2026-01-01",
        end_date="2026-01-31",
        akshare_client=client,
        content_cache_dir=tmp_path / "cache",
    )
    report = write_announcement_ingestion_artifacts(
        events,
        events_artifact_path=tmp_path / "latest_events.json",
        report_artifact_path=tmp_path / "latest_report.json",
    )

    events_payload = json.loads((tmp_path / "latest_events.json").read_text())
    report_payload = json.loads((tmp_path / "latest_report.json").read_text())
    assert isinstance(events_payload, list)
    assert isinstance(report_payload, dict)
    assert report_payload["events_artifact_path"].endswith("latest_events.json")
    assert report["run_status"] == "completed"
