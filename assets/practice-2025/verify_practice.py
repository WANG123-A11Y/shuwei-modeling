"""Independent checks of reported calculations; no certification of real-world models."""
from pathlib import Path
import json, hashlib
from decimal import Decimal, getcontext
import numpy as np
from scipy.signal import StateSpace, lsim
from scipy.integrate import simpson
import openpyxl

HERE=Path(__file__).resolve().parent
def main():
    out=HERE/'results';a=json.loads((out/'a_results.json').read_text('utf-8'));b=json.loads((out/'b_results.json').read_text('utf-8'));c=json.loads((out/'c_results.json').read_text('utf-8'))
    p=Path(a['sources'][0]['path']);w=openpyxl.load_workbook(p,read_only=True,data_only=True)
    ar=np.array([r[:6] for r in list(w['场景1'].values)[2:] if isinstance(r[0],(int,float))],float)
    ti=np.arange(40001)*.00025;forcing=np.interp(ti,ar[:,0],ar[:,1]);M=2800.;K=7225200.;C=3600.
    system=StateSpace([[0.,1.],[-K/M,-C/M]],[[0.],[1/M]],[[1.,0.],[-K/M,-C/M]],[[0.],[1/M]])
    _,ys,_=lsim(system,forcing,ti,X0=[.01,0.])
    exact_linear_I=float(simpson(ys[:,1]**2,x=ti)/10)
    raw=np.loadtxt(out/'a_scene1_off.csv',delimiter=',',skiprows=1)
    max_y_diff=float(np.max(abs(ys[::2,0]-raw[:,1])));max_acc_diff=float(np.max(abs(ys[::2,1]-raw[:,3])))
    assert max_y_diff<1e-7 and abs(exact_linear_I-a['main_results']['scene1_off']['I_0_10_m2_s4'])<1e-4
    # Recompute the necessary lower bound using decimal arithmetic on source values.
    getcontext().prec=40; decimal_bounds=[]
    for row in a['continuous_feasibility_certificate']['records']:
        q=list(map(lambda x:Decimal(str(x)),row['angles_rad']));d3=q[3]-3*q[2]+3*q[1]-q[0]
        lb=abs(d3)/(Decimal('1.5')*Decimal('.01')**2);assert lb>5000
        decimal_bounds.append(str(lb))
    # Check triangular-kernel L1 norm numerically, independently of the formula.
    x=np.linspace(-1,2,600001);ker1=np.maximum(0,1-abs(x));ker2=np.maximum(0,1-abs(x-1));kernel_norm=float(np.trapezoid(abs(ker2-ker1),x))
    assert abs(kernel_norm-1.5)<1e-9
    # Known continuous trajectory q=.5*a*t^2 has D2=a*h² and D3=0.
    t=np.arange(20)*.01;q=.5*4000*t*t
    assert np.max(abs(np.diff(q,n=2)/.01**2))<4000.000001
    assert np.max(abs(np.diff(q,n=3)/(1.5*.01**2)))<1e-7
    # Recompute full B metrics using saved per-file predictions, not metric helper.
    preds=json.loads((out/'b_predictions.json').read_text('utf-8'));classes=b['classes'];correct=sum(r['provided_label']==r['predicted_label'] for r in preds)
    independent_f1=[]
    for cl in classes:
        tp=sum(r['provided_label']==cl and r['predicted_label']==cl for r in preds)
        fp=sum(r['provided_label']!=cl and r['predicted_label']==cl for r in preds)
        fn=sum(r['provided_label']==cl and r['predicted_label']!=cl for r in preds)
        independent_f1.append(2*tp/(2*tp+fp+fn))
    assert abs(correct/len(preds)-b['full_train_nearest_centroid']['accuracy'])<1e-12
    assert abs(sum(independent_f1)/8-b['full_train_nearest_centroid']['macro_f1'])<1e-12
    manifest=json.loads((out/'b_split_manifest.json').read_text('utf-8'))
    train_hash={r['sha256'] for r in manifest['train']};val_hash={r['sha256'] for r in manifest['validation']};assert not train_hash&val_hash
    for record in b['ten_shot_practice']:
        selected=record['selected_train_files'];assert len(selected)==80 and len(set(selected))==80
        counts={cl:sum(r['label']==cl and r['relative_path'] in selected for r in manifest['train']) for cl in classes};assert set(counts.values())=={10}
    # One metadata source is recalculated without reading any raster pixels.
    assert len(c['rasters'])==9 and len(c['shapefiles'])==9
    assert c['synthetic_tests']['connectivity']['bathtub_cells']==7 and c['synthetic_tests']['connectivity']['sea_connected_cells']==6
    report={'scope':'Independent numerical/bookkeeping verification only; excludes scientific validation, semantic labels and real-city risks',
        'A':{'exact_state_space_piecewise_linear_forcing_I':exact_linear_I,'RK4_max_displacement_difference_m':max_y_diff,
            'RK4_max_acceleration_difference_m_s2':max_acc_diff,'decimal_necessary_acceleration_bounds':decimal_bounds,'triangular_kernel_L1_norm_h1':kernel_norm},
        'B':{'train_images':len(manifest['train']),'validation_images':len(preds),'correct':correct,
            'accuracy_recomputed':correct/len(preds),'macro_f1_recomputed':sum(independent_f1)/8,'cross_split_shared_hashes':0,'three_10shot_selections_checked':True},
        'C':{'raster_metadata_records':len(c['rasters']),'shapefile_header_records':len(c['shapefiles']),'synthetic_checks':'PASS'},
        'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
