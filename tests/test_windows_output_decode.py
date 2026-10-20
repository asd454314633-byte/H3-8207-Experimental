import ast,unittest
from pathlib import Path
SOURCE=Path(__file__).resolve().parents[1]/'custom_nodes/local_author/h3_six_compiler_bridge/__init__.py'
tree=ast.parse(SOURCE.read_text('utf-8'));fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_decode_windows_output')
scope={};exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),'decode','exec'),scope);decode=scope['_decode_windows_output']
class Decode(unittest.TestCase):
 def test_utf8_error_preserved(self):self.assertEqual(decode('启动失败：任务不可用'.encode('utf-8')),'启动失败：任务不可用')
 def test_gbk_error_preserved_and_old_replacement_reproduced(self):
  text='错误：该任务已禁用。';raw=text.encode('gb18030');self.assertNotEqual(raw.decode('utf-8',errors='replace'),text);self.assertEqual(decode(raw),text)
 def test_invalid_bytes_remain_diagnosable(self):self.assertIn('\\xff',decode(b'\xff'))
if __name__=='__main__':unittest.main()
