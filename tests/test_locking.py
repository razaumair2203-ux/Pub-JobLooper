"""Single-writer and atomic text-store regressions."""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core import store


root = tempfile.mkdtemp(prefix='joblooper-lock-')
store.configure(root)

with store.writer_lock():
    try:
        with store.writer_lock():
            raise AssertionError('nested writer unexpectedly acquired the same data-root lock')
    except ValueError as error:
        assert 'another Joblooper write is active' in str(error)

target = os.path.join(root, 'work', 'atomic.txt')
store.write_text(target, 'complete')
assert store.read_text(target) == 'complete'
assert not os.path.exists(target + '.tmp')

print('locking and atomic store: 3/3 pass')
