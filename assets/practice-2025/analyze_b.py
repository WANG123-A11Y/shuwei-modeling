"""Eight-class, closed-subset image baseline. NOT the 61-class contest solution.

Uses exact provided list labels only. Quarantines cross-split exact duplicates.
No pretrained model, CNN, additional data, or manual severity labels.
"""
from pathlib import Path
from collections import defaultdict, Counter
import argparse, hashlib, json, time, sys
import numpy as np
from PIL import Image, ImageOps
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def features(path):
    with Image.open(path) as im:
        im=ImageOps.exif_transpose(im).convert('RGB').resize((64,64),Image.Resampling.BILINEAR)
        rgb=np.asarray(im,dtype=float)/255.; hsv=np.asarray(im.convert('HSV'),dtype=float)/255.
    parts=[rgb.mean((0,1)),rgb.std((0,1)),hsv.mean((0,1)),hsv.std((0,1))]
    for arr,bins in [(rgb,8),(hsv,16)]:
        for ch in range(3): parts.append(np.histogram(arr[:,:,ch],bins=bins,range=(0,1))[0]/4096)
    return np.concatenate(parts)

def metrics(y,pred,classes):
    cm=np.array([[int(np.sum((y==a)&(pred==b))) for b in classes] for a in classes])
    tp=np.diag(cm); recall=tp/np.maximum(cm.sum(axis=1),1);precision=tp/np.maximum(cm.sum(axis=0),1)
    f1=2*precision*recall/np.maximum(precision+recall,1e-15)
    return {'accuracy':float(np.mean(y==pred)), 'macro_f1':float(f1.mean()),'macro_recall':float(recall.mean()),
        'per_class_recall':dict(zip(map(str,classes),map(float,recall))),'confusion_matrix':cm.tolist()}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path('.'))
    args=ap.parse_args();root=next(args.root.glob('*B_Problem'));out=HERE/'results';out.mkdir(exist_ok=True);fig=HERE/'figures';fig.mkdir(exist_ok=True)
    begin=time.perf_counter();label_maps={};list_stats={};sources=[]
    for split,n in [('train','train_list.txt'),('validation','ttest_list.txt')]:
        p=next(root.rglob(n)); sources.append({'path':str(p),'sha256':sha(p)})
        labels=defaultdict(set);rows=0
        for line in p.read_text('utf-8-sig').splitlines():
            path,label=line.rsplit(maxsplit=1);name=path.replace('\\','/').split('/')[-1];labels[name].add(int(label));rows+=1
        label_maps[split]=labels;list_stats[split]={'rows':rows,'unique_names':len(labels),'ambiguous_names':sum(len(v)>1 for v in labels.values())}
    records=[]; groups=defaultdict(list)
    for p in sorted(root.rglob('*.jpg')):
        split='train' if 'trainingset' in str(p) else 'validation'
        labels=label_maps[split].get(p.name,set());r={'path':str(p),'relative_path':str(p.relative_to(root)),'split':split,
            'label':next(iter(labels)) if len(labels)==1 else None,'sha256':sha(p)}
        records.append(r);groups[r['sha256']].append(r)
    decisions=[]; kept=[]; excluded=Counter()
    for digest,rs in groups.items():
        has_cross=len({r['split'] for r in rs})>1
        conflict=len({r['label'] for r in rs if r['label'] is not None})>1
        eligible=sorted([r for r in rs if r['label'] is not None],key=lambda x:x['relative_path'])
        if has_cross or conflict:
            reason='cross_split_duplicate' if has_cross else 'conflicting_labels'
            excluded[reason]+=len(rs)
        elif not eligible:
            reason='no_exact_list_label';excluded[reason]+=len(rs)
        else:
            reason='keep_one_exact_labeled_file';kept.append(eligible[0]);excluded['within_group_redundant_or_unlabeled']+=len(rs)-1
        decisions.append({'sha256':digest,'decision':reason,'files':rs})
    train=[r for r in kept if r['split']=='train'];valid_all=[r for r in kept if r['split']=='validation']
    classes=sorted({r['label'] for r in train}&{r['label'] for r in valid_all})
    train=[r for r in train if r['label'] in classes]; valid=[r for r in valid_all if r['label'] in classes]
    assert len(classes)==8, f'Review scope changed: {classes}'
    assert not ({r['sha256'] for r in train}&{r['sha256'] for r in valid})
    X=np.stack([features(r['path']) for r in train]);V=np.stack([features(r['path']) for r in valid])
    y=np.array([r['label'] for r in train]);v=np.array([r['label'] for r in valid]); d=X.shape[1]
    feature_seconds=time.perf_counter()-begin
    def fit_predict(indices):
        xx=X[indices]; yy=y[indices]; mu=xx.mean(0);sd=xx.std(0);sd[sd<1e-8]=1.
        xx=(xx-mu)/sd; vv=(V-mu)/sd
        centroids=np.stack([xx[yy==c].mean(0) for c in classes])
        pred=np.array(classes)[np.sum((vv[:,None,:]-centroids[None,:,:])**2,axis=2).argmin(1)]
        return pred,{'mean':mu.tolist(),'std':sd.tolist(),'centroids':centroids.tolist()}
    pred,model=fit_predict(np.arange(len(y)));full=metrics(v,pred,classes)
    (out/'b_full_model.json').write_text(json.dumps(model,indent=2),encoding='utf-8')
    majority=Counter(map(int,y)).most_common(1)[0][0];majority_result=metrics(v,np.full_like(v,majority),classes)
    few=[]
    for seed in [2025,2026,2027]:
        rng=np.random.default_rng(seed); indices=np.concatenate([rng.choice(np.flatnonzero(y==c),10,replace=False) for c in classes]);pp,mm=fit_predict(indices)
        row={'seed':seed,'train_size':len(indices),'metrics':metrics(v,pp,classes),
            'selected_train_files':[train[i]['relative_path'] for i in indices]};few.append(row)
        (out/f'b_10shot_seed_{seed}_model.json').write_text(json.dumps(mm,indent=2),encoding='utf-8')
    figu,ax=plt.subplots(figsize=(6.3,5.4),constrained_layout=True);cm=np.array(full['confusion_matrix']);im=ax.imshow(cm,cmap='Blues')
    ax.set_xticks(range(len(classes)),classes);ax.set_yticks(range(len(classes)),classes);ax.set_xlabel('Predicted class ID');ax.set_ylabel('Provided-list class ID')
    ax.set_title('Closed 8-class subset; exact duplicates quarantined',fontsize=10)
    for i in range(len(classes)):
        for j in range(len(classes)): ax.text(j,i,str(cm[i,j]),ha='center',va='center',color='white' if cm[i,j]>cm.max()/2 else 'black',fontsize=8)
    figu.colorbar(im,ax=ax,shrink=.8);figu.savefig(fig/'b_confusion.png',dpi=150);plt.close(figu)
    predictions=[{'relative_path':r['relative_path'],'sha256':r['sha256'],'provided_label':int(label),'predicted_label':int(p)} for r,label,p in zip(valid,v,pred)]
    (out/'b_predictions.json').write_text(json.dumps(predictions,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'b_split_manifest.json').write_text(json.dumps({'decisions':decisions,'train':train,'validation':valid},ensure_ascii=False,indent=2),encoding='utf-8')
    annotation_stats={}
    for p in root.rglob('*annotations.json'):
        sources.append({'path':str(p),'sha256':sha(p)}); ann=json.loads(p.read_text('utf-8-sig'))
        labels=Counter(int(r['disease_class']) for r in ann)
        annotation_stats[p.name]={'rows':len(ann),'classes':len(labels),'classes_with_fewer_than_10':{str(k):n for k,n in labels.items() if n<10}}
    results={'scope':'8-class CLOSED subset practice; NOT a 61-class solution or formal few-shot benchmark; list labels not semantically verified',
        'classes':classes,'list_stats':list_stats,'annotation_stats':annotation_stats,'sources':sources,
        'input_images':len(records),'exact_unique_hashes':len(groups),'cross_split_groups_quarantined':sum(len({r['split'] for r in rs})>1 for rs in groups.values()),
        'excluded_counts':dict(excluded),'train_counts':dict(sorted(Counter(map(int,y)).items())),
        'validation_counts':dict(sorted(Counter(map(int,v)).items())),'validation_other_classes_excluded':len(valid_all)-len(valid),
        'feature_definition':'84 features: RGB/HSV mean/std (12), RGB 8-bin normalized histograms (24), HSV 16-bin normalized histograms (48); RGB64x64',
        'normalization':'Training subset only; refit using selected 80 images for every 10-shot seed',
        'feature_dimension':d,'learned_scalar_count':int((2+len(classes))*d),'majority_class':majority,
        'majority_baseline':majority_result,'full_train_nearest_centroid':full,'ten_shot_practice':few,
        'ten_shot_summary':{key:{'mean':float(np.mean([r['metrics'][key] for r in few])), 'std_population':float(np.std([r['metrics'][key] for r in few]))} for key in ['accuracy','macro_f1']},
        'timing_seconds':{'audit_and_features':feature_seconds,'total':time.perf_counter()-begin},
        'limits':['No near-duplicate or acquisition-group audit','No semantic/visual ground-truth confirmation','No severity training labels created','No claim of task1/task2/task3/task4 completion','No test-driven hyperparameter selection'],
        'runtime':{'python':sys.version,'numpy':np.__version__,'script_sha256':sha(__file__)}}
    (out/'b_results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:results[k] for k in ['classes','input_images','train_counts','validation_counts','validation_other_classes_excluded','full_train_nearest_centroid','majority_baseline','ten_shot_summary','timing_seconds']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
