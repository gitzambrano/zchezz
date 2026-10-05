"""The CLI helper must stay optional and small."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'utils'))
from cliconf import override_from_cli
def spec(): return [('N','--n',int,'n'),('FLAG','--flag',bool,'flag'),('ITEMS','--item',list,'items')]
def test_bare_run_keeps_defaults():
    c={'N':3,'FLAG':True,'ITEMS':['default']}; override_from_cli(c,spec(),argv=[]); assert c=={'N':3,'FLAG':True,'ITEMS':['default']}
def test_overrides_are_optional_and_lists_replace():
    c={'N':3,'FLAG':True,'ITEMS':['default']}; override_from_cli(c,spec(),argv=['--n','5','--no-flag','--item','a','--item','b']); assert c=={'N':5,'FLAG':False,'ITEMS':['a','b']}
