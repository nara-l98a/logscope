"""Offline parser and analyzer for timestamped text logs."""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

LEVELS = ("ERROR", "WARN", "WARNING", "INFO", "DEBUG", "TRACE")
LOG_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\s+"
    r"(?P<level>ERROR|WARN(?:ING)?|INFO|DEBUG|TRACE)\s+(?P<body>.*)$",
    re.I,
)
SOURCE_RE = re.compile(r"(?:source|logger|module)=([^\s]+)", re.I)


@dataclass(frozen=True)
class Record:
    line: int
    timestamp: dt.datetime
    level: str
    message: str
    source: str


@dataclass(frozen=True)
class Malformed:
    line: int
    text: str
    reason: str


def parse_timestamp(value: str) -> dt.datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return dt.datetime.fromisoformat(value)


def parse_lines(lines: Iterable[str]) -> tuple[list[Record], list[Malformed]]:
    records: list[Record] = []
    malformed: list[Malformed] = []
    for number, raw in enumerate(lines, 1):
        text = raw.rstrip("\r\n")
        if not text.strip():
            continue
        match = LOG_RE.match(text)
        if not match:
            malformed.append(Malformed(number, text, "未匹配 ISO 时间戳 + 级别格式"))
            continue
        try:
            timestamp = parse_timestamp(match.group("timestamp"))
        except ValueError as exc:
            malformed.append(Malformed(number, text, f"时间戳无效: {exc}"))
            continue
        level = match.group("level").upper().replace("WARNING", "WARN")
        body = match.group("body")
        source_match = SOURCE_RE.search(body)
        source = source_match.group(1) if source_match else "(unknown)"
        records.append(Record(number, timestamp, level, body, source))
    return records, malformed


def _aware(value: dt.datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def filter_records(
    records: list[Record],
    level: str | None = None,
    keyword: str | None = None,
    start: dt.datetime | None = None,
    end: dt.datetime | None = None,
) -> list[Record]:
    level = level.upper() if level else None
    keyword = keyword.casefold() if keyword else None
    if start and end and _aware(start) != _aware(end):
        raise ValueError("--start 和 --end 必须同时带时区或同时不带时区")
    if start and end and start > end:
        raise ValueError("--start 不能晚于 --end")
    bounds = [value for value in (start, end) if value is not None]
    if bounds and any(_aware(record.timestamp) != _aware(bounds[0]) for record in records):
        raise ValueError("时间筛选范围与日志必须一致地带或不带时区")
    return [
        record
        for record in records
        if (not level or record.level == level)
        and (not keyword or keyword in record.message.casefold())
        and (not start or record.timestamp >= start)
        and (not end or record.timestamp <= end)
    ]


def load(path: Path) -> tuple[list[Record], list[Malformed]]:
    try:
        with path.open("r", encoding="utf-8") as file:
            return parse_lines(file)
    except FileNotFoundError as exc:
        raise ValueError(f"数据文件不存在: {path}") from exc
    except IsADirectoryError as exc:
        raise ValueError(f"数据路径是目录而非文件: {path}") from exc
    except UnicodeDecodeError as exc:
        raise ValueError(f"数据文件不是有效 UTF-8: {exc}") from exc


def bound(value: str, label: str) -> dt.datetime:
    try:
        return parse_timestamp(value)
    except ValueError as exc:
        raise ValueError(f"{label} 必须是 ISO 时间戳: {exc}") from exc


def summary(records: list[Record], bad: list[Malformed]) -> None:
    levels = collections.Counter(record.level for record in records)
    hours = collections.Counter(
        record.timestamp.strftime("%Y-%m-%d %H:00 ")
        + (record.timestamp.strftime("%z") if _aware(record.timestamp) else "(无时区)")
        for record in records
    )
    print(f"有效日志: {len(records)} 条")
    print("级别统计: " + (", ".join(f"{key}={value}" for key, value in sorted(levels.items())) or "无"))
    print("时间段统计:")
    for hour, count in sorted(hours.items()):
        print(f"  {hour}: {count}")
    print(f"格式错误: {len(bad)} 行")


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="logscope", description="离线解析并统计文本日志")
    parser.add_argument("--data", default=os.environ.get("LOGSCOPE_DATA"), help="UTF-8 日志文件（或设置 LOGSCOPE_DATA）")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("summary", help="统计级别、小时与格式错误")
    filter_parser = subparsers.add_parser("filter", help="按级别、关键字或时间范围筛选")
    filter_parser.add_argument("--level", choices=[level for level in LEVELS if level != "WARNING"], type=str.upper)
    filter_parser.add_argument("--keyword")
    filter_parser.add_argument("--start")
    filter_parser.add_argument("--end")
    sources_parser = subparsers.add_parser("sources", help="列出高频来源字段")
    sources_parser.add_argument("--limit", type=int, default=10)
    subparsers.add_parser("errors", help="列出无法解析的行")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)
    if not args.data:
        parser.error("必须提供 --data 或设置 LOGSCOPE_DATA")
    path = Path(args.data)
    if not path.is_file():
        parser.error(f"数据文件不可读或不存在: {args.data}")
    if getattr(args, "limit", 1) < 1:
        parser.error("--limit 必须为正整数")
    try:
        records, malformed = load(path)
    except ValueError as exc:
        parser.error(str(exc))
    if args.command == "summary":
        summary(records, malformed)
    elif args.command == "filter":
        try:
            selected = filter_records(
                records,
                args.level,
                args.keyword,
                bound(args.start, "--start") if args.start else None,
                bound(args.end, "--end") if args.end else None,
            )
        except ValueError as exc:
            parser.error(str(exc))
        for record in selected:
            print(f"{record.line}: {record.timestamp.isoformat()} {record.level} {record.message}")
        print(f"匹配: {len(selected)} 条；格式错误: {len(malformed)} 行", file=sys.stderr)
    elif args.command == "sources":
        for source, count in collections.Counter(record.source for record in records).most_common(args.limit):
            print(f"{source}: {count}")
        if malformed:
            print(f"格式错误: {len(malformed)} 行", file=sys.stderr)
    else:
        for item in malformed:
            print(f"第 {item.line} 行: {item.reason} | {item.text}")
        print(f"格式错误共 {len(malformed)} 行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
