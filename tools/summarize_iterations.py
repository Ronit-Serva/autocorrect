#!/usr/bin/env python3
"""Summarize saved paired measurements; never rerun or alter the algorithm."""
import json
from pathlib import Path

def main():
    directory=Path('results/iterations')
    rows=[]
    for p in sorted(directory.glob('hackathon-*.json')):
        d=json.loads(p.read_text());bp=p.with_name(p.name.replace('hackathon-','birkbeck-',1))
        if 'accuracy_A' not in d or not bp.exists():continue
        b=json.loads(bp.read_text())
        rows.append({'name':p.stem[len('hackathon-'):],'hackathon_matches':d['matches'],'hackathon_accuracy':d['accuracy_A'],'birkbeck_matches':b['matches'],'birkbeck_accuracy':b['accuracy_A'],'hackathon_seconds':d['wall_seconds_T'],'birkbeck_seconds':b['wall_seconds_T'],'hackathon_clean_preservation':d['correct_word_preservation'],'hackathon_report':str(p),'birkbeck_report':str(bp),'command':d.get('command')})
    summary={'selection':'Prioritize hackathon accuracy and require improvement over original Birkbeck baseline. submission is the shipped default; final is the previous release.','evaluation_warning':'Both supplied datasets were repeatedly inspected and used for iteration. These are development measurements, not held-out estimates. Times are single-run observations, not a controlled latency comparison.','baseline':{'hackathon_matches':1452,'hackathon_words':2000,'hackathon_accuracy':.726,'birkbeck_matches':13999,'birkbeck_words':35267,'birkbeck_accuracy':13999/35267},'configurations':sorted(rows,key=lambda x:(x['hackathon_accuracy'],x['birkbeck_accuracy']),reverse=True)}
    (directory/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(f'Summarized {len(rows)} paired configurations')
if __name__=='__main__':main()
