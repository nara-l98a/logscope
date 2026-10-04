import io,json,tempfile,unittest
import datetime as dt
from contextlib import redirect_stdout,redirect_stderr
from pathlib import Path
from logscope.app import parse_lines,filter_records,main,summary
SAMPLE="2024-01-02T03:04:05Z ERROR source=api failed login\n2024-01-02 03:05:00+00:00 INFO source=worker started\n坏行\n"
class Tests(unittest.TestCase):
 def test_parse(self):
  r,b=parse_lines(SAMPLE.splitlines(True));self.assertEqual(len(r),2);self.assertEqual(len(b),1);self.assertEqual(r[0].source,"api")
 def test_filter(self):
  r,_=parse_lines(SAMPLE.splitlines(True));self.assertEqual(len(filter_records(r,level="error")),1);self.assertEqual(len(filter_records(r,keyword="LOGIN")),1)
 def test_summary_tempfile(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"x.log";p.write_text(SAMPLE,encoding="utf-8");o=io.StringIO()
   with redirect_stdout(o):main(["--data",str(p),"summary"])
   self.assertIn("有效日志: 2 条",o.getvalue());self.assertIn("ERROR=1",o.getvalue())
 def test_filter_line_and_bad(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"x.log";p.write_text(SAMPLE,encoding="utf-8");o=io.StringIO();e=io.StringIO()
   with redirect_stdout(o),redirect_stderr(e):main(["--data",str(p),"filter","--level","ERROR"])
   self.assertIn("1:",o.getvalue());self.assertIn("格式错误: 1 行",e.getvalue())
 def test_errors(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"x.log";p.write_text(SAMPLE,encoding="utf-8");o=io.StringIO()
   with redirect_stdout(o):main(["--data",str(p),"errors"])
   self.assertIn("第 3 行",o.getvalue())
 def test_range_validation_and_timezone_awareness(self):
  r,_=parse_lines(SAMPLE.splitlines(True))
  with self.assertRaisesRegex(ValueError,"不能晚于"):
   filter_records(r,start=dt.datetime(2024,1,3,tzinfo=dt.timezone.utc),end=dt.datetime(2024,1,2,tzinfo=dt.timezone.utc))
  with self.assertRaisesRegex(ValueError,"带或不带时区"):
   filter_records(r,start=dt.datetime(2024,1,2,0,0,0),end=None)
 def test_summary_keeps_distinct_offsets(self):
  lines=["2024-01-02T03:00:00+02:00 INFO source=a one\n","2024-01-02T03:00:00Z INFO source=b two\n"]
  r,b=parse_lines(lines);o=io.StringIO()
  with redirect_stdout(o):summary(r,b)
  self.assertIn("+0200",o.getvalue());self.assertIn("+0000",o.getvalue())
 def test_json_summary_and_filter(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"x.log";p.write_text(SAMPLE,encoding="utf-8")
   o=io.StringIO()
   with redirect_stdout(o):main(["--data",str(p),"--json","summary"])
   result=json.loads(o.getvalue())
   self.assertEqual(result["valid_count"],2);self.assertEqual(result["levels"]["ERROR"],1)
   o=io.StringIO()
   with redirect_stdout(o),redirect_stderr(io.StringIO()):
    main(["--data",str(p),"--json","filter","--level","ERROR"])
   result=json.loads(o.getvalue())
   self.assertEqual(result["matched_count"],1);self.assertEqual(result["records"][0]["source"],"api")
if __name__=="__main__":unittest.main()
