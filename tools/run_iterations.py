#!/usr/bin/env python3
"""Run explicit configurations on both datasets and retain complete predictions."""
import argparse,json,subprocess
from pathlib import Path

def run(name,exe,index,options):
    reports=[]
    for ds,folder in [('hackathon','hackathon_test'),('birkbeck','my_dataset')]:
        prefix=Path('results/iterations')/(ds+'-'+name)
        args=['python3','tools/evaluate.py','--input',folder+'/input.txt','--expected',folder+'/expected.txt','--executable',exe,'--program-arg=--index','--program-arg='+index,'--report',str(prefix)+'.json','--output',str(prefix)+'-output.txt','--all-errors','--label',name]
        args+=['--program-arg='+x for x in options]
        r=subprocess.run(args,capture_output=True,text=True)
        if r.returncode: raise RuntimeError(r.stdout+r.stderr)
        d=json.loads(r.stdout); reports.append(d)
        print(name,ds,d['matches'],round(d['accuracy_A']*100,3),'clean',d['correct_word_preservation'],'time',round(d['wall_seconds_T'],3),flush=True)
    return reports
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('name');p.add_argument('--exe',default='./autocorrect');p.add_argument('--index',required=True)
    a,options=p.parse_known_args();run(a.name,a.exe,a.index,[x for x in options if x!='--'])
