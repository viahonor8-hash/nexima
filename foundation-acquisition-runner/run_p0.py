#!/usr/bin/env python3
import concurrent.futures, hashlib, html.parser, json, pathlib, re, subprocess, time, urllib.parse, urllib.request, zipfile
from collections import Counter,defaultdict
UA='ImportCost-Regulatory-Data-Foundation-SourceAcquisition/1.1'
EXPECTED_GROUPS=[f'{i:02d}' for i in range(1,98) if i!=77]
EEC_INDEXES=['https://eec.eaeunion.org/comission/department/catr/ett/','https://eec.eaeunion.org/comission/department/catr/ett/ru.2022/']
CN=[
 ('cn-2026-mof-tariff','PRIMARY_AUTHORITY','https://gss.mof.gov.cn/gzdt/zhengcefabu/202512/P020251231607833453633.pdf','PDF'),
 ('cn-2026-mof-tariff-replica','OFFICIAL_REPLICA','https://segg.sh.gov.cn/zxfw/zcfg/kjssfw/20260105/3bdf14b248c44bc1b1011841b68539f0/5dc15413ae7c47d092c582a2b095f194.pdf','PDF'),
 ('cn-2026-gacc-declaration-directory','OFFICIAL_OPERATIONAL_SOURCE','https://www.customs.gov.cn/customs/fileDir/resource/cms/article/302272/6916622/2025123118295487346.pdf','PDF'),
 ('cn-cmcode2026b-shanghai','OFFICIAL_REPLICA','https://shanghai.chinatax.gov.cn/bsfw/xzzx/rjxz/202606/P020260610346902416014.rar','RAR_DBF'),
 ('cn-cmcode2026b-guangdong','OFFICIAL_REPLICA','https://guangdong.chinatax.gov.cn/gdsw/rjxz/2026-06/10/74590f1479d3463abce2133e703d22b1/files/e7ada51460e741b8ac7b84eec49f43cb.rar','RAR_DBF'),
]
DISCOVERY=[
 ('cn-cmcode2026b-jiangsu','OFFICIAL_REPLICA','https://jiangsu.chinatax.gov.cn/art/2026/6/9/art_15956_1748230.html'),
 ('cn-cmcode2026b-guangxi','OFFICIAL_REPLICA','https://guangxi.chinatax.gov.cn/nsfw/xzzx/qtxz/202606/t20260608_434181.html'),
]
class Links(html.parser.HTMLParser):
 def __init__(self): super().__init__(); self.hrefs=[]
 def handle_starttag(self,t,a):
  if t.lower()=='a':
   h=dict(a).get('href')
   if h:self.hrefs.append(h)
def H(b):return hashlib.sha256(b).hexdigest()
def HF(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for c in iter(lambda:f.read(1<<20),b''):h.update(c)
 return h.hexdigest()
def get(url,timeout=240):
 q=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'*/*','Accept-Encoding':'identity'}); t=time.time()
 with urllib.request.urlopen(q,timeout=timeout) as r:return r.read(),{'url':url,'finalUrl':r.geturl(),'status':getattr(r,'status',200),'headers':dict(r.headers.items()),'elapsed':round(time.time()-t,3)}
def links(url):
 b,m=get(url,120); p=Links();p.feed(b.decode('utf-8','ignore'));return [urllib.parse.urljoin(m['finalUrl'],x) for x in p.hrefs],{'url':url,'sha256':H(b),'finalUrl':m['finalUrl']}
def discover_eaeu():
 found={}; evidence=[]
 for page in EEC_INDEXES:
  try:
   ls,ev=links(page); evidence.append(ev)
   for u in ls:
    if not urllib.parse.urlparse(u).path.lower().endswith('.pdf'):continue
    m=re.search(r'ru\.(\d{2})_2022',u,re.I)
    if not m:continue
    g=m.group(1)
    if g in EXPECTED_GROUPS:found.setdefault(g,u)
  except Exception as e:evidence.append({'url':page,'error':f'{type(e).__name__}:{e}'})
 return found,evidence
def discover_rar(page):
 ls,ev=links(page); rs=[u for u in ls if urllib.parse.urlparse(u).path.lower().endswith('.rar')]; return (rs[0] if rs else None),ev
def dbf_semantic(paths):
 from dbfread import DBF
 tables=[];allrows=[]
 for p in sorted(paths):
  rows=None;err=None;encused=None
  for enc in (None,'gb18030','gbk','cp936'):
   try:
    kw={'load':True,'char_decode_errors':'strict'}
    if enc:kw['encoding']=enc
    t=DBF(str(p),**kw); rows=[dict(r) for r in t]; encused=getattr(t,'encoding',enc); break
   except Exception as e:err=e
  if rows is None:return {'status':'FAILED','error':str(err)}
  n=[]
  for r in rows:
   rr={}
   for k,v in r.items():
    if v is None:x=None
    elif hasattr(v,'isoformat'):x=v.isoformat()
    elif isinstance(v,(str,int,float,bool)):x=v
    else:x=str(v)
    rr[str(k)]=x
   n.append(rr)
  n.sort(key=lambda x:json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')))
  sh=H(json.dumps(n,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()); tables.append({'file':p.name,'sha256':HF(p),'rows':len(n),'encoding':encused,'semanticHash':sh,'fields':list(n[0]) if n else []}); allrows.extend({'table':p.name,'row':x} for x in n)
 allrows.sort(key=lambda x:json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')))
 return {'status':'SUCCESS','tables':tables,'rows':len(allrows),'semanticHash':H(json.dumps(allrows,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())}
def acquire(src,out):
 sid,trust,url,kind=src; r={'sourceId':sid,'trustClass':trust,'url':url,'kind':kind,'status':'FAILED'}
 try:
  b,m=get(url); ok=b.startswith(b'%PDF') if kind=='PDF' else b.startswith(b'Rar!\x1a\x07')
  r.update(m);r['bytes']=len(b);r['sha256']=H(b);r['magicValid']=ok
  if not ok:return r
  ext='.pdf' if kind=='PDF' else '.rar'; d=out/'raw'/sid;d.mkdir(parents=True,exist_ok=True);p=d/(sid+ext);p.write_bytes(b);r['rawPath']=str(p.relative_to(out));r['status']='SUCCESS'
  if kind=='RAR_DBF':
   e=out/'extracted'/sid;e.mkdir(parents=True,exist_ok=True);q=subprocess.run(['7z','x','-y','-o'+str(e),str(p)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True);r['extractExit']=q.returncode;r['extractTail']=q.stdout[-2500:]
   if q.returncode!=0:r['status']='FAILED_EXTRACTION';return r
   fs=[x for x in e.rglob('*') if x.is_file()];r['extracted']=[{'path':str(x.relative_to(out)),'sha256':HF(x),'bytes':x.stat().st_size} for x in fs];r['dbf']=dbf_semantic([x for x in fs if x.suffix.lower()=='.dbf'])
  return r
 except Exception as e:r['error']=f'{type(e).__name__}:{e}';return r
def dzip(root,out):
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for p in sorted([x for x in root.rglob('*') if x.is_file()]):
   i=zipfile.ZipInfo(str(p.relative_to(root)),(2026,1,1,0,0,0));i.compress_type=zipfile.ZIP_DEFLATED;i.external_attr=(0o100644&0xffff)<<16;z.writestr(i,p.read_bytes())
def main():
 out=pathlib.Path('runner-output');out.mkdir(exist_ok=True); groups,ee=discover_eaeu(); src=[('eaeu-ett-group-'+g,'PRIMARY_AUTHORITY',u,'PDF') for g,u in groups.items()]+CN; disc=[]
 for sid,t,page in DISCOVERY:
  try:u,ev=discover_rar(page);disc.append({'sourceId':sid,'page':page,'evidence':ev,'discovered':u});
  except Exception as e:u=None;disc.append({'sourceId':sid,'page':page,'error':f'{type(e).__name__}:{e}'})
  if u:src.append((sid,t,u,'RAR_DBF'))
 with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:res=list(ex.map(lambda s:acquire(s,out),src))
 res.sort(key=lambda x:x['sourceId']); norm={'generatedAt':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'eaeuDiscovery':ee,'cmcodeDiscovery':disc,'expectedEaeuGroups':EXPECTED_GROUPS,'discoveredEaeuGroups':sorted(groups),'statusCounts':dict(Counter(x['status'] for x in res)),'sources':res};(out/'NORMALIZED_SOURCE_MANIFEST.json').write_text(json.dumps(norm,ensure_ascii=False,indent=2)+'\n')
 by={x['sourceId']:x for x in res};es=[x for x in res if x['sourceId'].startswith('eaeu-ett-group-') and x['status']=='SUCCESS']; qe={'expectedGroups':96,'discoveredGroups':len(groups),'acquiredGroups':len(es),'missing':[g for g in EXPECTED_GROUPS if 'eaeu-ett-group-'+g not in {x['sourceId'] for x in es}],'allRawAcquired':len(es)==96,'sourceHashes':{x['sourceId']:x.get('sha256') for x in es},'publicationReady':False,'nextGate':'semantic parse + NSI + amendments quorum'};(out/'EAEU_TNVED_SOURCE_QUORUM.json').write_text(json.dumps(qe,ensure_ascii=False,indent=2)+'\n')
 qc={'mofPrimary':{k:by.get('cn-2026-mof-tariff',{}).get(k) for k in ('status','sha256','bytes')},'mofReplica':{k:by.get('cn-2026-mof-tariff-replica',{}).get(k) for k in ('status','sha256','bytes')},'gacc10digit':{k:by.get('cn-2026-gacc-declaration-directory',{}).get(k) for k in ('status','sha256','bytes')},'publicationReady':False,'nextGate':'8-digit/10-digit parse + parent/units/change reconciliation'};(out/'CN_2026_NOMENCLATURE_SOURCE_QUORUM.json').write_text(json.dumps(qc,ensure_ascii=False,indent=2)+'\n')
 cms=[x for x in res if x['sourceId'].startswith('cn-cmcode2026b-') and x.get('dbf',{}).get('status')=='SUCCESS']; gr=defaultdict(list)
 for x in cms:gr[x['dbf']['semanticHash']].append(x['sourceId'])
 best=max(gr.values(),key=len) if gr else []; qm={'replicas':[{'sourceId':x['sourceId'],'rarSha256':x.get('sha256'),'semanticHash':x['dbf']['semanticHash'],'rows':x['dbf']['rows'],'tables':x['dbf']['tables']} for x in cms],'semanticGroups':dict(gr),'semanticQuorumSatisfied':len(best)>=2,'matchingReplicas':best,'publicationReady':False,'nextGate':'reconcile 2026A + cancellation + battery transitions'};(out/'CN_CMCODE2026B_SOURCE_QUORUM.json').write_text(json.dumps(qm,ensure_ascii=False,indent=2)+'\n')
 gate={'eaeuRaw96':qe['allRawAcquired'],'cnMof':qc['mofPrimary']['status']=='SUCCESS','cnGacc':qc['gacc10digit']['status']=='SUCCESS','cmcodeSemantic2':qm['semanticQuorumSatisfied']};(out/'ACQUISITION_GATE.json').write_text(json.dumps(gate,indent=2)+'\n');(out/'SOURCE_ACQUISITION_REPORT.md').write_text('# P0 SOURCE ACQUISITION REPORT\n\n'+json.dumps({'statusCounts':norm['statusCounts'],'gate':gate},ensure_ascii=False,indent=2)+'\n');dzip(out,pathlib.Path('OFFICIAL_SOURCE_BUNDLE.zip'));pathlib.Path('OFFICIAL_SOURCE_BUNDLE.zip.sha256').write_text(HF(pathlib.Path('OFFICIAL_SOURCE_BUNDLE.zip'))+'  OFFICIAL_SOURCE_BUNDLE.zip\n');print(json.dumps({'gate':gate,'statusCounts':norm['statusCounts']},ensure_ascii=False))
if __name__=='__main__':main()
