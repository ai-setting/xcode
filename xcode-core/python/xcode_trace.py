"""
Xcode Python Trace Runner - 无侵入 trace 工具

用法：
  python xcode_trace.py <target.py> [args...]

设计：
  1. 不修改目标项目
  2. 自动记录所有函数调用的栈 + 入参出参
  3. 记录函数定义位置 + 调用方位置
  4. 输出标准 JSON 格式给 IDE 端

修复要点（相对路径 → 绝对路径）：
  - 所有 file 字段用绝对路径，避免 wsPath filter 失效
  - 默认 exclude stdlib / site-packages / dist-packages
  - filter 同时匹配 file 和 func name
"""

import sys
import os
import json
import time
import argparse
import importlib.util
from collections import defaultdict


# 判定 stdlib 路径集合
def _is_stdlib_path(abs_path: str) -> bool:
    """判定是否是 stdlib / 第三方包路径（默认排除）"""
    if not abs_path:
        return False
    if 'site-packages' in abs_path or 'dist-packages' in abs_path:
        return True
    if '/usr/lib/python' in abs_path:
        return True
    if '/usr/local/lib/python' in abs_path:
        return True
    return False


class XcodeTracer:
    """核心 tracer，扩展 sys.settrace 能力"""

    def __init__(self, options):
        self.options = options
        self.entries = []
        self.depth = 0
        self.start_time = time.time()
        self.call_id = 0
        self.call_stack = []
        self.call_count = defaultdict(int)
        self.total_time = defaultdict(float)
        self.last_enter = {}

    def should_trace(self, frame):
        """决定是否追踪这一帧"""
        co = frame.f_code
        # 绝对路径
        abs_path = os.path.abspath(co.co_filename)

        # 排除 <...> 形式（exec / eval / REPL）
        if co.co_filename.startswith('<') and co.co_filename.endswith('>'):
            return False
        # 排除 generator / comprehension
        if co.co_name in ('<genexpr>', '<listcomp>', '<dictcomp>', '<setcomp>'):
            return False
        # 默认排除 stdlib
        if not self.options.include_stdlib and _is_stdlib_path(abs_path):
            return False

        # 应用 --filter：任意关键字命中 file 或 qualname 即通过（白名单语义）
        if self.options.filter:
            tokens = [t for t in self.options.filter if t]
            if tokens:
                qualname_hint = co.co_qualname if hasattr(co, 'co_qualname') else co.co_name
                hit = any(t in abs_path or t in co.co_name or t in qualname_hint for t in tokens)
                if not hit:
                    return False

        # 应用 --exclude：任意关键字命中即排除
        if self.options.exclude:
            qualname_hint = co.co_qualname if hasattr(co, 'co_qualname') else co.co_name
            if any(e in abs_path or e in co.co_name or e in qualname_hint for e in self.options.exclude):
                return False

        # 深度限制
        if self.depth >= self.options.max_depth:
            return False

        return True

    def serialize_arg(self, value, max_len=500):
        try:
            s = repr(value)
            if len(s) > max_len:
                return s[:max_len] + '...'
            return s
        except Exception:
            return '<unserializable>'

    def _get_qualname(self, frame):
        co = frame.f_code
        qualname = co.co_qualname if hasattr(co, 'co_qualname') else co.co_name
        if 'self' in frame.f_locals:
            self_obj = frame.f_locals['self']
            if hasattr(self_obj, '__class__'):
                qualname = f"{self_obj.__class__.__name__}.{co.co_name}"
        return qualname

    def _extract_args(self, frame):
        args = {}
        co = frame.f_code
        locals_dict = frame.f_locals
        if 'self' in locals_dict and co.co_varnames[0] == 'self':
            self_obj = locals_dict['self']
            args['self'] = f"<{type(self_obj).__name__} object>"
        elif 'cls' in locals_dict and co.co_varnames[0] == 'cls':
            args['cls'] = locals_dict['cls'].__name__
        for var_name in co.co_varnames:
            if var_name in ('self', 'cls') or var_name.startswith('.'):
                continue
            if var_name in locals_dict:
                args[var_name] = self.serialize_arg(locals_dict[var_name])
        return args

    def __call__(self, frame, event, arg):
        co = frame.f_code
        if not self.should_trace(frame):
            return None

        if event == 'call':
            self.call_id += 1
            call_id = self.call_id

            # 调用方信息（从 frame.f_back 拿）— 用绝对路径
            caller_info = None
            if frame.f_back:
                caller_co = frame.f_back.f_code
                caller_info = {
                    'caller_id': self.call_stack[-1] if self.call_stack else None,
                    'caller_file': os.path.abspath(caller_co.co_filename),
                    'caller_line': frame.f_back.f_lineno,
                    'caller_func': self._get_qualname(frame.f_back),
                }

            entry = {
                'id': call_id,
                'type': 'call',
                'depth': self.depth,
                'func': co.co_name,
                'qualname': self._get_qualname(frame),
                # 函数定义位置（绝对路径）
                'file': os.path.abspath(co.co_filename),
                'line': co.co_firstlineno,
                # 当前执行位置
                'current_line': frame.f_lineno,
                # 入参
                'args': self._extract_args(frame) if not self.options.no_args else {},
                # 调用方位置（关键！）
                'caller': caller_info,
                'timestamp': time.time() - self.start_time,
            }
            self.entries.append(entry)
            self.call_count[entry['qualname']] += 1
            self.last_enter[entry['qualname']] = entry['timestamp']
            self.call_stack.append(call_id)
            self.depth += 1

        elif event == 'return':
            self.depth -= 1
            qualname = self._get_qualname(frame)
            call_id = self.call_stack.pop() if self.call_stack else None

            entry = {
                'id': call_id,
                'type': 'return',
                'depth': self.depth,
                'func': co.co_name,
                'qualname': qualname,
                'result': self.serialize_arg(arg),
                'timestamp': time.time() - self.start_time,
            }
            self.entries.append(entry)

            if qualname in self.last_enter:
                duration = entry['timestamp'] - self.last_enter[qualname]
                self.total_time[qualname] += duration

        elif event == 'exception':
            self.depth -= 1
            exc_type, exc_value, exc_tb = arg
            call_id = self.call_stack.pop() if self.call_stack else None
            entry = {
                'id': call_id,
                'type': 'exception',
                'depth': self.depth,
                'func': co.co_name,
                'qualname': self._get_qualname(frame),
                'exception': f"{exc_type.__name__}: {exc_value}",
                'timestamp': time.time() - self.start_time,
            }
            self.entries.append(entry)

        return self

    def save(self, output_path):
        calls = sum(1 for e in self.entries if e['type'] == 'call')
        returns = sum(1 for e in self.entries if e['type'] == 'return')
        exceptions = sum(1 for e in self.entries if e['type'] == 'exception')

        result = {
            'tool': 'xcode-trace',
            'version': '0.1.0',
            'target': self.options.script,
            'filter': self.options.filter,
            'exclude': self.options.exclude,
            'total_calls': calls,
            'total_returns': returns,
            'total_exceptions': exceptions,
            'duration_ms': int((time.time() - self.start_time) * 1000),
            'entries': self.entries,
            'summary': {
                'top_called': sorted(
                    [{'func': k, 'count': v, 'total_ms': self.total_time[k] * 1000}
                     for k, v in self.call_count.items()],
                    key=lambda x: -x['count']
                )[:20]
            }
        }
        with open(output_path, 'w') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"Saved {len(self.entries)} entries to {output_path}")
        print(f"  Calls: {result['total_calls']}, "
              f"Returns: {result['total_returns']}, "
              f"Exceptions: {result['total_exceptions']}")


def main():
    parser = argparse.ArgumentParser(description='Xcode Python Trace Runner')
    parser.add_argument('script', help='Target Python script')
    parser.add_argument('args', nargs='*', help='Args for target script')
    parser.add_argument('--filter', nargs='*', default=[], help='Whitelist filter (any token match in file/func)')
    parser.add_argument('--exclude', nargs='*', default=[], help='Blacklist filter (any token match in file/func)')
    parser.add_argument('--output', '-o', default='xcode_trace.json')
    parser.add_argument('--max-depth', type=int, default=999)
    parser.add_argument('--no-args', action='store_true')
    parser.add_argument('--include-stdlib', action='store_true', help='Trace stdlib/site-packages too')
    parser.add_argument('--sys-path', nargs='*', default=[], help='Extra sys.path entries for target')

    options = parser.parse_args()

    if not os.path.exists(options.script):
        print(f"Script not found: {options.script}")
        sys.exit(1)

    # 将额外 sys.path 加入
    script_dir = os.path.dirname(os.path.abspath(options.script))
    for p in [script_dir] + list(options.sys_path):
        if p and p not in sys.path:
            sys.path.insert(0, p)

    print(f"Tracing: {options.script}")
    print(f"  filter:  {options.filter}")
    print(f"  exclude: {options.exclude}")
    print(f"  sys.path (head): {sys.path[:3]}")

    sys.argv = [options.script] + options.args

    tracer = XcodeTracer(options)
    sys.settrace(tracer)

    import runpy
    try:
        runpy.run_path(options.script, run_name='__main__')
    except SystemExit:
        pass
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        sys.settrace(None)
        tracer.save(options.output)


if __name__ == '__main__':
    main()