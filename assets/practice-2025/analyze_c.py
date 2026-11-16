"""Local GIS readiness audit and explicitly SYNTHETIC mechanism tests for C.
No city risk, ten-year probability, monetary loss, or optimal plan is fabricated.
"""
from pathlib import Path
from collections import deque
import argparse, hashlib, json, struct
from PIL import Image
Image.MAX_IMAGE_PIXELS=None # metadata only; no raster pixels are decoded/allocated
import openpyxl
import numpy as np

HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def serial(v):
    if isinstance(v,bytes):return v.decode('utf-8','replace')
    if isinstance(v,(tuple,list)):return [serial(x) for x in v]
    if isinstance(v,(int,float,str,bool)) or v is None:return v
    return str(v)
def geokeys(raw):
    if not raw:return {}
    a=list(raw);result={}
    for i in range(a[3]):
        key,location,count,value=a[4+4*i:8+4*i];result[str(key)]={'location':location,'count':count,'value_or_offset':value}
    return result
def connected_inundation(elevation,level,sea_seeds):
    eligible=elevation<=level; wet=np.zeros_like(eligible,bool);todo=deque()
    for y,x in sea_seeds:
        if eligible[y,x]:wet[y,x]=True;todo.append((y,x))
    while todo:
        y,x=todo.popleft()
        for yy,xx in [(y-1,x),(y+1,x),(y,x-1),(y,x+1)]:
            if 0<=yy<len(wet) and 0<=xx<wet.shape[1] and eligible[yy,xx] and not wet[yy,xx]:wet[yy,xx]=True;todo.append((yy,xx))
    return wet
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path('.'));args=ap.parse_args()
    root=next(args.root.glob('*C_Problem'));out=HERE/'results';out.mkdir(exist_ok=True)
    rasters=[]
    for p in sorted(root.rglob('*.tif')):
        with Image.open(p) as im:
            tags={str(k):serial(im.tag_v2[k]) for k in [256,257,258,259,277,339,33550,33922,34735,34737,42112,42113] if k in im.tag_v2}
        rasters.append({'path':str(p),'file_size':p.stat().st_size,'content_hash_status':'NOT_COMPUTED; metadata-only audit, no pixel calculations',
            'tags':tags,'geokeys':geokeys(tags.get('34735')),
            'metadata_sha256':hashlib.sha256(json.dumps(tags,sort_keys=True,ensure_ascii=False).encode()).hexdigest()})
    shapes=[]
    for p in sorted(root.rglob('*.shp')):
        with p.open('rb') as f: header=f.read(100)
        prj=p.with_suffix('.prj');dbf=p.with_suffix('.dbf');count=None
        if dbf.exists():
            with dbf.open('rb') as f: dh=f.read(32)
            count=struct.unpack('<I',dh[4:8])[0]
        shapes.append({'path':str(p),'file_size':p.stat().st_size,'header_bbox_Xmin_Ymin_Xmax_Ymax':list(struct.unpack('<4d',header[36:68])),
            'shape_type':struct.unpack('<I',header[32:36])[0],'dbf_record_count':count,
            'prj':prj.read_text('utf-8-sig',errors='replace') if prj.exists() else None,'prj_sha256':sha(prj) if prj.exists() else None,
            'header_sha256':hashlib.sha256(header).hexdigest(),'full_geometry_read':False})
    links=[]
    for p in sorted(root.rglob('*.txt')):
        links.append({'path':str(p),'sha256':sha(p),'text':p.read_text('utf-8-sig',errors='replace'),'web_content_verified':False})
    tables=[]
    for p in sorted(root.rglob('*.xlsx')):
        w=openpyxl.load_workbook(p,read_only=True,data_only=True)
        tables.append({'path':str(p),'sha256':sha(p),'sheets':{s.title:[list(row) for row in s.values] for s in w}})
    # Explicitly synthetic: a low inland cell behind a high rim is NOT connected.
    dem=np.array([[0,0,3,3,3],[0,1,3,1,3],[0,1,3,3,3]],float)
    connected=connected_inundation(dem,1,[(0,0)]);bathtub=dem<=1
    assert bathtub[1,3] and not connected[1,3]
    assert int(bathtub.sum())==7 and int(connected.sum())==6
    pannual=.1;p10=1-(1-pannual)**10
    # Synthetic event distribution, probabilities sum to one, each event exclusive.
    probs=np.array([.8,.15,.05]); losses=np.array([0.,10.,100.]);expected=float(probs@losses)
    assert np.isclose(probs.sum(),1) and expected==6.5
    synthetic={'label':'SYNTHETIC unit tests only; no values represent a real city',
        'connectivity':{'elevation_grid':dem.tolist(),'level':1,'bathtub_cells':int(bathtub.sum()),'sea_connected_cells':int(connected.sum()),'isolated_low_cell':[1,3]},
        'ten_year_probability':{'synthetic_annual_p':pannual,'stationary_independent_assumption_required':True,'result':p10},
        'expected_loss':{'exclusive_event_probabilities':probs.tolist(),'synthetic_loss_units':losses.tolist(),'expected_loss':expected}}
    results={'scope':'Metadata/readiness audit plus synthetic consistency checks; no real-city numerical risk output',
        'pdf_sources':[{'path':str(p),'sha256':sha(p)} for p in root.glob('*.pdf')],
        'rasters':rasters,'shapefiles':shapes,'link_files':links,'tables':tables,'synthetic_tests':synthetic,
        'blockers':['Datasets 1--3 are local links only; actual dated sea-level, storm and loss series not downloaded/verified',
            'Raster vertical datum and compatibility with tide gauge/sea-level datum unconfirmed',
            'Geographic/projected CRS differ across layers; harmonization not performed',
            'No pixel-level NoData mask, coastline/levee/river connectivity or geometry validity audit yet',
            'POI is not money: asset values, depth-duration-salinity damage functions and discounting assumptions missing',
            'No calibrated city probabilities, threshold-loss curves, construction costs, or relocation costs; cannot select highest-risk city numerically'],
        'script_sha256':sha(__file__)}
    (out/'c_results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'rasters':[{k:r[k] for k in ['path','file_size','geokeys']} for r in rasters], 'shapefile_crs':list(dict.fromkeys(s['prj'] for s in shapes)),
        'tables':tables,'synthetic_tests':synthetic,'blockers':results['blockers']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
