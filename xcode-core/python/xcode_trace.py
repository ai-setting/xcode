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
        # 兼容 dict / argparse.Namespace / SimpleNamespace
        # 自动补全缺失字段（避免用户传 dict 时缺字段崩溃）
        from types import SimpleNamespace
        defaults = {
            "filter": [],
            "exclude": [],
            "include_stdlib": False,
            "include_dunders": False,
            "max_depth": 999,
            "no_args": False,
        }
        if isinstance(options, dict):
            merged = {**defaults, **options}
            options = SimpleNamespace(**merged)
        else:
            # argparse.Namespace：补全缺失属性
            for k, v in defaults.items():
                if not hasattr(options, k):
                    setattr(options, k, v)
        self.options = options
        self.entries = []
        self.depth = 0
        self.start_time = time.time()
        self.call_id = 0
        self.call_stack = []
        self.call_count = defaultdict(int)
        self.total_time = defaultdict(float)
        self.last_enter = {}
        # v0.2.0 — react-fix support: count exceptions for non-zero exit.
        self.exception_count = 0

    def should_trace(self, frame):
        """决定是否追踪这一帧"""
        co = frame.f_code
        # 绝对路径
        abs_path = os.path.abspath(co.co_filename)

        # 排除 <...> 形式（exec / eval / REPL / 模块顶层）
        if co.co_filename.startswith('<') and co.co_filename.endswith('>'):
            return False
        # 排除 generator / comprehension
        if co.co_name in ('<genexpr>', '<listcomp>', '<dictcomp>', '<setcomp>'):
            return False
        # 排除模块顶层（<module> 不是函数调用，只是 import）
        if co.co_name == '<module>':
            return False
        # 排除 @dataclass 自动生成的 __init__ 模式
        # Python @dataclass 生成的 __init__ 在 trace 里特征：
        #   - co_qualname == co_name（不带 .）
        #   - co_argcount == 0（没有显示参数）
        #   - f_locals 为空
        #   - co_firstlineno 在文件 < 100 行
        #   - **函数名大写开头**（Python 约定：class PascalCase，function snake_case）
        #   - **f_back 也在同一个文件**（class 定义过程）
        # 这是 Python 3.10+ 的 dataclass 行为
        qualname_check = co.co_qualname if hasattr(co, 'co_qualname') else co.co_name
        if qualname_check == co.co_name:
            is_pascal_case = co.co_name and co.co_name[0].isupper()
            same_file = (frame.f_back and 
                        os.path.abspath(frame.f_back.f_code.co_filename) == abs_path)
            if (is_pascal_case and
                co.co_argcount == 0 and
                not frame.f_locals and
                co.co_firstlineno > 0 and
                co.co_firstlineno < 100 and
                same_file):
                return False
        # 排除 dataclass / namedtuple 自动生成的方法
        if co.co_name in ('__init__', '__init_subclass__', '__class_getitem__', '__repr__', '__eq__', '__hash__'):
            return False
        # 排除常见 dunder（除非 include_dunders=True）
        if not getattr(self.options, 'include_dunders', False):
            if co.co_name.startswith('__') and co.co_name.endswith('__'):
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

    def _unwrap_frame(self, frame):
        """跳过 functools.wraps wrapper，找到真实调用点。
        
        tongagents.logtrace 用 @functools.wraps(fn) 包装函数（sync_wrapper / async_wrapper）。
        当用户调用被装饰的函数时，Python frame 链是：
            caller_code → sync_wrapper → wrapped_fn
        
        但 caller 在 sync_wrapper 里面调用 fn，frame.f_back 是 sync_wrapper 的 caller
        （也是 wrapper 内部），所以会跳到 wrapper 里面。
        
        这个 helper 检查 wrapper 名字，跳到 caller 的 caller。
        """
        co = frame.f_code
        if co.co_name in ('sync_wrapper', 'async_wrapper'):
            if frame.f_back:
                # 递归：检查上一级是不是 wrapper
                if frame.f_back.f_code.co_name in ('sync_wrapper', 'async_wrapper'):
                    return self._unwrap_frame(frame.f_back)
                return frame.f_back
        return frame
    
    def _get_qualname(self, frame):
        co = frame.f_code
        # 默认用 co_qualname（如 OntologyNode.__init__，包含完整限定名）
        qualname = co.co_qualname if hasattr(co, 'co_qualname') else co.co_name
        # 如果有 self，加类名前缀（但通常 co_qualname 已经包含）
        if 'self' in frame.f_locals and '.<' not in qualname:
            self_obj = frame.f_locals['self']
            if hasattr(self_obj, '__class__'):
                qualname = f"{self_obj.__class__.__name__}.{co.co_name}"
        # 跳过模块顶层执行（<module>）
        if qualname == '<module>':
            return None
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
                back_frame = self._unwrap_frame(frame.f_back)
                caller_co = back_frame.f_code
                caller_info = {
                    'caller_id': self.call_stack[-1] if self.call_stack else None,
                    'caller_file': os.path.abspath(caller_co.co_filename),
                    'caller_line': back_frame.f_lineno,
                    'caller_func': self._get_qualname(back_frame),
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
            self.exception_count += 1

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
        # v0.2.0 — exit non-zero if any exception was traced so the
        # TS runner can classify the failure and react-fix the scenario.
        sys.exit(2 if tracer.exception_count > 0 else 0)


if __name__ == '__main__':
    main()