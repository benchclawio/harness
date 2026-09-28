import json,re,collections,math
def parse_orig(o):
    m=re.search(r"^ ?([\d\.]+)",o)
    if m:
        try: return float(m.group(1))
        except: return 0
    return 0
def parse_fixed(o):
    m=re.search(r"^\s*([1-5](?:\.\d+)?)",o)
    return float(m.group(1)) if m else None
def ranks(x):
    s=sorted(range(len(x)),key=lambda i:x[i]); r=[0]*len(x); i=0
    while i<len(s):
        j=i
        while j+1<len(s) and x[s[j+1]]==x[s[i]]: j+=1
        for k in range(i,j+1): r[s[k]]=(i+j)/2+1
        i=j+1
    return r
def pearson(a,b):
    ma,mb=sum(a)/len(a),sum(b)/len(b)
    num=sum((x-ma)*(y-mb) for x,y in zip(a,b)); den=math.sqrt(sum((x-ma)**2 for x in a)*sum((y-mb)**2 for y in b))
    return num/den
def spearman(a,b): return pearson(ranks(a),ranks(b))
def kendall_b(a,b):
    n=len(a); c=d=ta=tb=0
    for i in range(n):
        for j in range(i+1,n):
            da=a[i]-a[j]; db=b[i]-b[j]
            if da==0 and db==0: continue
            if da==0: ta+=1
            elif db==0: tb+=1
            elif da*db>0: c+=1
            else: d+=1
    return (c-d)/math.sqrt((c+d+ta)*(c+d+tb))
def meta(J,dim,parser,drop_none=False):
    P=collections.defaultdict(list);H=collections.defaultdict(list)
    for it in J:
        s=[parser(r) for r in it['all_responses']]
        if drop_none: s=[x for x in s if x is not None]
        P[it['doc_id']].append(sum(s)/len(s)); H[it['doc_id']].append(it['scores'][dim])
    rs=[];ts=[]
    for d in P:
        if len(set(H[d]))<=1 or len(set(P[d]))<=1: continue
        rs.append(spearman(P[d],H[d])); ts.append(kendall_b(P[d],H[d]))
    return sum(rs)/len(rs), sum(ts)/len(ts), len(rs)
res={}
for f,dim in [('coh','coherence'),('con','consistency'),('flu','fluency'),('rel','relevance')]:
    J=json.load(open(f'gpt4_{f}.json'))
    resp=[r for it in J for r in it['all_responses']]
    z=[r for r in resp if parse_orig(r)==0]
    mis=[r for r in z if parse_fixed(r) is not None]
    o=meta(J,dim,parse_orig); fx=meta(J,dim,parse_fixed,True)
    res[f]=(o,fx)
    print(f"{dim}: zero-scored {len(z)}, of which contain a valid 1-5 score {len(mis)} | orig rho={o[0]:.3f} tau={o[1]:.3f} docs={o[2]} | fixed rho={fx[0]:.3f} tau={fx[1]:.3f}")
print('AVG orig rho %.3f tau %.3f | fixed rho %.3f tau %.3f'%(sum(v[0][0] for v in res.values())/4,sum(v[0][1] for v in res.values())/4,sum(v[1][0] for v in res.values())/4,sum(v[1][1] for v in res.values())/4))
