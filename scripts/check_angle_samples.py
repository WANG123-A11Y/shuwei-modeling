"""Necessary checks for uniformly sampled angular trajectories, standard library only.

Input JSON: {"time_s":[...],"angles_rad":[[...],...],
             "speed_limit_rad_s":100,"accel_limit_rad_s2":5000}
A PASS of these necessary inequalities never proves feasibility.
"""
import argparse, json, math
from pathlib import Path

def analyze(data):
    t=data['time_s'];q=data['angles_rad'];wlim=data['speed_limit_rad_s'];alim=data['accel_limit_rad_s2']
    if len(t)<4 or len(q)!=len(t) or not q or not q[0]:raise ValueError('At least four time-aligned samples required')
    width=len(q[0])
    if any(len(row)!=width for row in q):raise ValueError('Ragged angle rows')
    values=list(t)+[v for row in q for v in row]+[wlim,alim]
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in values):raise ValueError('Finite numeric values required')
    h=t[1]-t[0]
    if h<=0 or any(t[i+1]<=t[i] or abs((t[i+1]-t[i])-h)>abs(h)*1e-8 for i in range(len(t)-1)):raise ValueError('Strictly increasing uniform time grid required')
    if wlim<=0 or alim<=0:raise ValueError('Positive limits required')
    groups=[]
    for j in range(width):
        x=[row[j] for row in q];d1=[x[i+1]-x[i] for i in range(len(x)-1)]
        d2=[d1[i+1]-d1[i] for i in range(len(d1)-1)];d3=[d2[i+1]-d2[i] for i in range(len(d2)-1)]
        b1=max(map(abs,d1))/h;b2=max(map(abs,d2))/h**2;b3=max(map(abs,d3))/(1.5*h**2)
        idx=max(range(len(d3)),key=lambda i:abs(d3[i]))
        conflict=b1>wlim*(1+1e-9) or max(b2,b3)>alim*(1+1e-9)
        groups.append({'group_zero_based':j,'necessary_speed_lower_bound_rad_s':b1,'second_difference_accel_lower_bound_rad_s2':b2,
            'adjacent_kernel_accel_lower_bound_rad_s2':b3,'witness_indices':list(range(idx,idx+4)),
            'witness_times_s':t[idx:idx+4],'witness_angles_rad':x[idx:idx+4],
            'status':'CONTRADICTS_LIMITS' if conflict else 'NO_CONTRADICTION_FOUND'})
    return {'scope':'Necessary conditions for exact samples and C1 motion with bounded acceleration; not a sufficiency test',
        'derivation':'D2 is an acceleration integral against a triangular kernel; L1 norm of adjacent-kernel difference is 1.5*h^2',
        'sampling_step_s':h,'groups':groups,'any_contradiction':any(g['status']=='CONTRADICTS_LIMITS' for g in groups),
        'uncertainty_note':'If angles are noisy/rounded, quantify their admissible errors before declaring physical inconsistency'}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('input',type=Path);ap.add_argument('--out',type=Path);args=ap.parse_args()
    result=analyze(json.loads(args.input.read_text('utf-8-sig')));s=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)
    if args.out:args.out.write_text(s+'\n',encoding='utf-8')
    print(s)
if __name__=='__main__':main()
