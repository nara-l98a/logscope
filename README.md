# logscope

`logscope` 是一个**离线、只读**的中文 CLI 文本日志解析器：识别常见 ISO 8601 时间戳与 `ERROR/WARN/INFO/DEBUG/TRACE` 等级，统计小时段和等级，按等级/关键字/时间范围过滤，展示高频 `source=` 来源及原始行号，并逐行报告格式错误。

## 功能边界

仅读取本地 UTF-8 文本；不跟踪目录、不联网、不写入日志文件、不解析 JSON/多行堆栈，也不推断缺失时间戳。小时统计保留每条记录的时区偏移，不将不同偏移静默合并。使用 `--start/--end` 筛选时，范围与日志时间戳必须同时带时区或同时不带时区，否则会返回清晰错误。解析失败行不会阻塞其他行。

## 要求与安装

需要 Python 3.10+，运行依赖仅 Python 标准库。

```bash
python -m pip install .
logscope --help
# 开发安装可用 python -m pip install -e .
```

## 数据格式

每行格式为 `YYYY-MM-DDTHH:MM:SS[.微秒](Z|±HH:MM) LEVEL message`，日期和时间也可用空格分隔；时间戳可带时区，若不带则保持无时区。`message` 中可选 `source=api`、`logger=worker` 或 `module=service`（无则显示 `(unknown)`）。

## CLI 完整示例

```bash
logscope --data examples/sample.log summary
logscope --data examples/sample.log filter --level ERROR
logscope --data examples/sample.log filter --keyword queue --start 2024-01-02T00:00:00Z --end 2024-01-02T23:59:59Z
logscope --data examples/sample.log sources --limit 2
logscope --data examples/sample.log errors
```

`summary` 示例输出：

```text
有效日志: 4 条
级别统计: DEBUG=1, ERROR=1, INFO=1, WARN=1
时间段统计:
  2024-01-02 03:00 +0000: 4
格式错误: 1 行
```

全局参数：`--data PATH`（必需；或环境变量 `LOGSCOPE_DATA`）。子命令：

- `summary`：有效记录的级别/小时统计和错误行数。
- `filter`：`--level ERROR|WARN|INFO|DEBUG|TRACE`、`--keyword TEXT`、`--start ISO`、`--end ISO`；输出匹配行号。
- `sources`：`--limit N`，默认 10，必须为正整数。
- `errors`：错误行号、原因和原文。

数据路径也可写作 `LOGSCOPE_DATA=/path/app.log logscope summary`。不存在文件、目录、非 UTF-8、非法时间、倒置范围、时区标记不匹配或无效 limit 会明确报错并返回非零状态。

## 隐私与安全

程序不会联网、上传或保存输入内容；只读打开用户指定文件，不执行日志中的文本。输出可能包含敏感原文，勿在公共终端或 CI 日志中运行。项目不包含个人数据、凭据或 token。

## 开发与测试

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

测试使用 `tempfile` 创建临时日志，不接触真实用户数据；GitHub Actions 在 Python 3.11 上安装并测试。

## 许可证

MIT，详见 [LICENSE](LICENSE)。
