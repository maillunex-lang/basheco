"""Deterministic visual-only pilot for stage 1.3. No player-owned or server plots."""
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CATALOG=json.loads((ROOT/'client/data/admin_navigation.json').read_text())
ID='S80652440101'
matches=[s for d in CATALOG['districts'] for s in d['locations'] if s['id']==ID]
assert len(matches)==1 and matches[0]['cell'] is not None
cx,cy=matches[0]['cell']
# Each footprint is an integer number of 6m cells. Roads are one cell wide.
# Seeded arithmetic, no Python random or system-dependent hash.
seed=13042026
objects=[]
for y in range(-12,13):
    objects.append({'kind':'road','cell':[cx,cy+y],'size':[1,1]})
for x in range(-18,19):
    objects.append({'kind':'road','cell':[cx+x,cy],'size':[1,1]})
for row in range(3):
    for col in range(5):
        v=(seed+row*37+col*71)%7
        w,h=([1,1],[1,2],[2,2])[v%3]
        x=cx-17+col*7
        y=cy-10+row*7
        # ensure footprints do not intersect road cross
        assert x+w<=cx or x>=cx+1
        assert y+h<=cy or y>=cy+1
        objects.append({'kind':'house','cell':[x,y],'size':[w,h],'residents_hint':w*h*4})
output={'schema':'basheco.pilot_location/1','version':1,'settlement_id':ID,'seed':seed,'cell_size_m':6,'objects':objects}
assert any(o['kind']=='house' for o in objects)
target=ROOT/'client/data/generated_locations.json'
target.write_text(json.dumps({'schema':'basheco.generated_locations/1','locations':[output]},ensure_ascii=False,separators=(',',':'))+'\n')
print('PILOT_OK',ID,'roads',sum(o['kind']=='road' for o in objects),'houses',sum(o['kind']=='house' for o in objects))