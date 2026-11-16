"""Find a bounded C1, piecewise-quadratic interpolant by sparse LP.

A failed restricted-interpolant LP is not a general impossibility certificate.
"""
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

def bounded_interpolant(t, q, subdivisions=4, speed_limit=100., accel_limit=5000.):
    h=float(t[1]-t[0]);dt=h/subdivisions;n=(len(t)-1)*subdivisions;nv=n+1
    rows=[];cols=[];vals=[]
    for i in range(len(t)-1):
        for j in range(subdivisions+1):
            rows.append(i);cols.append(i*subdivisions+j);vals.append(dt*(.5 if j in [0,subdivisions] else 1.))
    eq=coo_matrix((vals,(rows,cols)),shape=(len(t)-1,nv+1)).tocsr()
    rr=[];cc=[];vv=[]
    for i in range(n):
        for sg,k in [(1.,2*i),(-1.,2*i+1)]:
            rr.extend([k,k,k]);cc.extend([i,i+1,nv]);vv.extend([-sg,sg,-dt])
    ub=coo_matrix((vv,(rr,cc)),shape=(2*n,nv+1)).tocsr()
    c=np.zeros(nv+1);c[-1]=1
    bounds=[(-speed_limit,speed_limit)]*nv+[(0,None)]
    v=[];records=[]
    for j in range(q.shape[1]):
        res=linprog(c,A_ub=ub,b_ub=np.zeros(2*n),A_eq=eq,b_eq=np.diff(q[:,j]),bounds=bounds,method='highs',
                    options={'primal_feasibility_tolerance':1e-8,'dual_feasibility_tolerance':1e-8})
        if not res.success:raise RuntimeError(res.message)
        v.append(res.x[:nv]);records.append({'group':j,'minimum_max_acceleration_in_this_interpolant_class':float(res.x[-1]),'solver_message':res.message})
    v=np.stack(v,axis=1);acc=np.diff(v,axis=0)/dt
    qq=np.zeros_like(v);qq[0]=q[0]
    qq[1:]=q[0]+np.cumsum(dt*(v[:-1]+v[1:])/2,axis=0)
    err=float(np.max(abs(qq[::subdivisions]-q)))
    def evaluate(idx,tau,side='right'):
        # idx/tau refer to original source intervals. Preserve one-sided endpoint.
        shift=-1e-7 if side=='left' else 1e-7
        sub=np.clip(np.floor(tau/dt+shift).astype(int),0,subdivisions-1)
        k=idx*subdivisions+sub;local=tau-sub*dt
        return qq[k]+v[k]*local[:,None]+.5*acc[k]*local[:,None]**2,v[k]+acc[k]*local[:,None],acc[k]
    info={'interpolant':'minimax acceleration, piecewise constant on refined intervals; source angles exactly constrained',
        'subdivisions_per_source_interval':subdivisions,'chosen_v0':v[0].tolist(),
        'max_abs_omega':np.max(abs(v),axis=0).tolist(),'max_abs_alpha':np.max(abs(acc),axis=0).tolist(),
        'max_reconstruction_error':err,'within_given_limits':bool(np.max(abs(acc))<=accel_limit+1e-3 and np.max(abs(v))<=speed_limit+1e-5),
        'optimization_records':records,'warning':'Minimum is over this interpolation class, not a proof for all continuous trajectories; initial angular velocity unprovided'}
    return evaluate,info

def continuous_acceleration_lower_bound(t,q):
    """Necessary for ANY C1 trajectory with essentially bounded acceleration.

    A centered second difference is a triangular-kernel integral of q''.
    The L1 norm of the difference of adjacent triangular kernels is 1.5*h**2.
    Thus |third difference|/(1.5*h**2) <= ||q''||_infinity.
    This is stronger than checking each centered second difference separately.
    """
    h=float(t[1]-t[0]);assert np.allclose(np.diff(t),h)
    d3=np.diff(q,n=3,axis=0);bound=abs(d3)/(1.5*h*h);records=[]
    for j in range(q.shape[1]):
        i=int(np.argmax(bound[:,j]));records.append({'group':j,'source_row_indices_zero_based':list(range(i,i+4)),
            'times_s':t[i:i+4].tolist(),'angles_rad':q[i:i+4,j].tolist(),'third_difference_rad':float(d3[i,j]),
            'continuous_acceleration_necessary_lower_bound_rad_s2':float(bound[i,j])})
    return {'derivation':'D2_i = integral triangular_kernel_i(t)*alpha(t) dt; ||kernel_(i+1)-kernel_i||_1 = 1.5*h^2; |D3| <= 1.5*h^2*amax',
        'step_s':h,'records':records,'all_groups_contradict_5000':all(r['continuous_acceleration_necessary_lower_bound_rad_s2']>5000+1e-6 for r in records),
        'scope':'Exact angle samples in radians on uniform time grid; approximate/noisy-angle interpretation would require an explicit error tolerance'}
