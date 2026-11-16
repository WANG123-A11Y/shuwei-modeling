"""Independent, bounded analysis of 2025 A Q1. Original inputs stay read-only.

Python 3; numpy scipy openpyxl matplotlib. No optimization/Q2/Q3 claims.
"""
from pathlib import Path
import argparse, hashlib, json, math, platform, sys
import numpy as np
import openpyxl
from scipy.interpolate import CubicSpline, PchipInterpolator
from check_a_feasibility import bounded_interpolant, continuous_acceleration_lower_bound
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path('.'))
    args=ap.parse_args(); out=HERE/'results';out.mkdir(exist_ok=True);fig=HERE/'figures';fig.mkdir(exist_ok=True)
    xlsx=next(args.root.rglob('Problem A：Data.xlsx'))
    pdf=next(xlsx.parent.glob('*.pdf'))
    wb=openpyxl.load_workbook(xlsx,read_only=True,data_only=True)
    a=np.array([r[:6] for r in list(wb['场景1'].values)[2:] if isinstance(r[0],(int,float))],float)
    b=np.array([r[:2] for r in list(wb['场景2'].values)[2:] if isinstance(r[0],(int,float))],float)
    params=[list(r) for r in wb['系统参数'].values]
    t,q=a[:,0],a[:,2:]; h=float(t[1]-t[0]); assert np.allclose(np.diff(t),h)
    mass,radius,M,K,C=100.,.2,2800.,7225200.,3600.
    # y-coordinate of group 2 is negative in Figure 2. Each group has TWO masses.
    signs=np.array([1.,-1.,1.,-1.]); factor=2*mass*radius
    quad, feasibility=bounded_interpolant(t,q,subdivisions=4)
    certificate=continuous_acceleration_lower_bound(t,q)
    interpolants={'minimax_quadratic_4sub':quad}
    for name,cls in [('cubic_spline',CubicSpline),('pchip',PchipInterpolator)]:
        spl=cls(t,q,axis=0)
        def ev(idx,tau,side='right',spl=spl):
            x=t[idx]+tau
            if side=='left':x=np.nextafter(x,-np.inf)
            return spl(x),spl(x,1),spl(x,2)
        interpolants[name]=ev
    spline_constraints={}
    td=np.linspace(t[0],t[-1],19981);idx=np.clip(np.searchsorted(t,td,side='right')-1,0,len(t)-2)
    for name,ev in interpolants.items():
        _,w,al=ev(idx,td-t[idx]);spline_constraints[name]={'sampled_max_abs_omega':np.max(abs(w),axis=0).tolist(),
            'sampled_max_abs_alpha':np.max(abs(al),axis=0).tolist(),
            'dense_points_over_alpha_limit':np.sum(abs(al)>5000+1e-6,axis=0).tolist()}

    def forces(nsub,interp,scenario):
        assert nsub%4==0, 'Integration steps must align with refined angle-fit intervals'
        # Each source interval is integrated separately. End stages use that
        # interval's one-sided acceleration; acceleration can jump at its boundary.
        dt=h/nsub; n=(len(t)-1)*nsub+nsub
        ts=np.arange(n)*dt; ids=np.minimum((np.arange(n)//nsub),len(t)-2)
        tau=ts-t[ids]; F=[]
        ev=interpolants[interp]
        qend,wend,_=ev(np.array([len(t)-2]),np.array([h]))
        for offset in (0,dt/2,dt):
            x=ts+offset; local=tau+offset
            qq,ww,aa=ev(ids,local,side='left' if offset==dt else 'right')
            end=x>t[-1]+1e-10
            qq[end]=qend+wend*(x[end,None]-t[-1]);ww[end]=wend;aa[end]=0
            # Final source point belongs to the continuation on the new interval.
            newend=ts>=t[-1]-1e-10
            qq[newend]=qend+wend*(x[newend,None]-t[-1]);ww[newend]=wend;aa[newend]=0
            fc=factor*np.sum(signs*ww**2*np.sin(qq),axis=1)
            ft=factor*np.sum(signs*(-aa*np.cos(qq)),axis=1)
            src=a if scenario==1 else b
            fd=np.interp(x,src[:,0],src[:,1]) # hold last F for 9.99--10 s
            F.append((fd,fc,ft))
        return dt,ts,F

    def simulate(nsub=20,interp='minimax_quadratic_4sub',scenario=1,kfactor=1,mode='off',zero=False):
        dt,ts,Fs=forces(nsub,interp,scenario); n=len(ts)
        force=[]
        for fd,fc,ft in Fs:
            force.append(np.zeros(n) if zero else fd+(fc if mode in ['cf','full'] else 0)+(ft if mode=='full' else 0))
        k,c=K*kfactor,C*kfactor
        state=np.array([.01,0.,0.]); states=np.empty((n+1,3));states[0]=state
        def rhs(z,f):
            acceleration=(f-c*z[1]-k*z[0])/M
            return np.array([z[1],acceleration,acceleration**2])
        for i in range(n):
            k1=rhs(state,force[0][i]);k2=rhs(state+dt*k1/2,force[1][i]);k3=rhs(state+dt*k2/2,force[1][i]);k4=rhs(state+dt*k3,force[2][i])
            state=state+dt*(k1+2*k2+2*k3+k4)/6;states[i+1]=state
        times=np.arange(n+1)*dt
        f_nodes=np.r_[force[0],force[2][-1]]
        acc=(f_nodes-c*states[:,1]-k*states[:,0])/M
        jshort=int(round(t[-1]/dt))
        summary={'I_0_10_m2_s4':float(states[-1,2]/times[-1]),'I_0_9p99_m2_s4':float(states[jshort,2]/t[-1]),
                 'RMS_acceleration_m_s2':float(np.sqrt(states[-1,2]/times[-1])),
                 'max_abs_displacement_m':float(np.max(abs(states[:,0]))),'max_abs_acceleration_m_s2':float(np.max(abs(acc))),
                 'dt':dt,'kfactor':kfactor,'force_model':mode,'angle_interpolation':interp,'scenario':scenario}
        return times,states,acc,summary

    results={};curves={}
    for name,mode,scenario in [('scene1_off','off',1),('scene1_cf','cf',1),('scene1_full','full',1),('scene2_off','off',2)]:
        ti,st,ac,s=simulate(mode=mode,scenario=scenario);results[name]=s;curves[name]=(ti,st,ac)
    convergence={}
    for name,mode in [('scene1_off','off'),('scene1_cf','cf'),('scene1_full','full')]:
        _,_,_,fine=simulate(nsub=40,mode=mode)
        convergence[name]={'dt_0p0005_I':results[name]['I_0_10_m2_s4'],'dt_0p00025_I':fine['I_0_10_m2_s4'],
            'relative_difference':abs(fine['I_0_10_m2_s4']-results[name]['I_0_10_m2_s4'])/fine['I_0_10_m2_s4']}
    sensitivity={}
    for name in ('cubic_spline','pchip'):
        for mode in ('cf','full'):
            sensitivity[f'{name}_{mode}']=simulate(interp=name,mode=mode)[3]
    for mode in ('off','cf','full'):
        sensitivity[f'four_times_kc_{mode}']=simulate(kfactor=4,mode=mode)[3]
    ti,st,ac,_=simulate(zero=True,nsub=20)
    beta=C/(2*M); wn=np.sqrt(K/M);wd=np.sqrt(wn**2-beta**2)
    exact=.01*np.exp(-beta*ti)*(np.cos(wd*ti)+(beta/wd)*np.sin(wd*ti))
    verification={'unforced_max_y_error_m':float(np.max(abs(exact-st[:,0]))), 'time_step_convergence':convergence,
        'finite_difference_necessary_speed_bound':np.max(abs(np.diff(q,axis=0)/h),axis=0).tolist(),
        'finite_difference_necessary_accel_bound':np.max(abs(np.diff(q,n=2,axis=0)/h**2),axis=0).tolist()}
    assert verification['unforced_max_y_error_m']<1e-8
    assert max(x['relative_difference'] for x in convergence.values())<1e-4
    # Do not falsely declare source angles feasible when the refined LP exceeds limits.
    assert feasibility['max_reconstruction_error']<1e-6
    for mode in ('cf','full'):
        results['scene1_'+mode]['relative_I_reduction_vs_off']=1-results['scene1_'+mode]['I_0_10_m2_s4']/results['scene1_off']['I_0_10_m2_s4']
    figu,axs=plt.subplots(3,1,figsize=(10,7.5),sharex=True,constrained_layout=True)
    for name,label in [('scene1_off','Actuators off'),('scene1_cf','Centrifugal-only diagnostic')]:
        ti,st,ac=curves[name];axs[0].plot(ti,st[:,0]*1000,label=label,lw=.8);axs[1].plot(ti,ac,label=label,lw=.8)
    ti,st,ac=curves['scene1_full'];axs[2].plot(ti,ac,color='#a73330',lw=.7)
    axs[0].set_ylabel('Displacement (mm)');axs[1].set_ylabel('Acceleration (m/s²)');axs[2].set_ylabel('Full reaction (m/s²)');axs[2].set_xlabel('Time (s)');axs[0].legend(ncol=2,fontsize=8)
    axs[2].set_title('Infeasible supplied-angle fit: full-reaction diagnostic only',fontsize=9,color='#a73330')
    for ax in axs: ax.grid(alpha=.2)
    figu.savefig(fig/'a_scene1.png',dpi=150);plt.close(figu)
    for name,(ti,st,ac) in curves.items():
        np.savetxt(out/f'a_{name}.csv',np.column_stack([ti,st[:,0],st[:,1],ac,st[:,2]]),delimiter=',',header='time_s,displacement_m,velocity_m_s,acceleration_m_s2,integrated_acceleration_squared',comments='')
    report={'scope':'Q1 off executed; supplied-angle fits simulated diagnostically but violate acceleration feasibility. Q2/Q3 design only, no optimized/controller result claimed',
        'sources':[{'path':str(p),'sha256':sha(p)} for p in [xlsx,pdf]],'parameters_raw':params,
        'assumptions':{'M_kg':M,'moving_mass_derivation':'2000 + 2 actuators * 4 masses * 100 = 2800',
            'K_N_m':K,'C_N_s_m':C,'kc_interpretation':'Use tabulated equivalent vehicle coefficients; 4x sensitivity is alternative interpretation, not an established fact',
            'group_y_signs':signs.tolist(),'force_models':'cf=2mr sum(s*w^2 sin(q)); full=cf-2mr sum(s*alpha*cos(q))',
            'end_extension':'F held, angles extended with final velocity and zero acceleration over 9.99--10 s',
            'initial_angular_velocities':'Selected within feasible intervals; not specified by source'},
        'data_end_s':float(t[-1]),'angle_fit_NOT_feasible':feasibility,'continuous_feasibility_certificate':certificate,'interpolation_constraints':spline_constraints,
        'main_results':results,'model_sensitivity':sensitivity,'verification':verification,
        'runtime':{'python':sys.version,'numpy':np.__version__,'platform':platform.platform(),'script_sha256':sha(__file__)}}
    (out/'a_results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'main_results':results,'feasibility':feasibility,'verification':verification,'spline_constraints':spline_constraints},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
