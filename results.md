# Results

Model `codestral-2508` for every agent. Cost is **estimated at paid prices**; the free tier cost $0.

| task | mode | status | evidence /3 | accuracy /4 | false pos. /2 | priority /1 | total /10 | findings | seconds | steps | tokens | est. cost USD | run | detail |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fixture_repo | multi | COMPLETE | 3.0 | 3.0 | 1.8 | 1.0 | 8.8 | 8 | 65 | 58 | 49111 | 0.0166 | `20261016-220223-fixture_repo-multi` | found 6/8, 1 unmatched, 0 invalid snippets |
| fixture_repo | single | COMPLETE | 2.6 | 3.5 | 2.0 | 1.0 | 9.1 | 7 | 15 | 9 | 9033 | 0.0032 | `20261016-220338-fixture_repo-single` | found 7/8, 0 unmatched, 1 invalid snippets |
| public_repo | multi | COMPLETE | 3.0 | manual | 2.0 | manual | manual | 10 | 31 | 22 | 63116 | 0.0198 | `20261016-220403-public_repo-multi` | 0 invalid snippets; accuracy checked by hand |
| public_repo | single | COMPLETE | 3.0 | manual | 2.0 | manual | manual | 19 | 18 | 6 | 40088 | 0.0129 | `20261016-220443-public_repo-single` | 0 invalid snippets; accuracy checked by hand |
| triage_inbox | multi | COMPLETE | 3.0 | 3.6 | 2.0 | 1.0 | 9.6 | 21 | 61 | 53 | 59253 | 0.0196 | `20261016-220511-triage_inbox-multi` | 18/20 labels right, 0 invalid snippets |
| triage_inbox | single | COMPLETE | 3.0 | 4.0 | 2.0 | 1.0 | 10.0 | 30 | 30 | 12 | 14773 | 0.0060 | `20261016-220622-triage_inbox-single` | 20/20 labels right, 0 invalid snippets |

## Manual check: public repo (added by hand after `evaluate.py`; every finding checked against `records.py` and `setup.py` at commit `ea42736`)

| mode | findings | correct | accuracy (manual, /4) | notes |
|---|---|---|---|---|
| multi | 10 | 3 | 1.2 | Correct: the bare `except:` that swallows the error after rollback (records.py:344, cited as 345), and the missing docstrings on `cli` and `print_bytes`. False: two `os.system` calls on constant strings reported as shell injection, `except ImportError` called bare, docstrings "missing" on `isexception` and `_reduce_datetimes` (both have them), and `stdout` called unused (used at line 555). |
| single | 19 | 7 | 1.5 | All 19 findings are docstring claims. 7 are right (`Connection.__init__`, `close`, `__enter__`, `__exit__`, `__repr__`, `cli`, `print_bytes`); 12 functions already have docstrings. No security or quality findings. |

Both runs scored 3.0/3 on evidence because every quoted snippet exists. **The evidence check proves a quote is real, not that the claim is true.**
