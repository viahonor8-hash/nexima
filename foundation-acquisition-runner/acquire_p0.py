#!/usr/bin/env python3
import argparse, concurrent.futures, hashlib, html.parser, json, pathlib, re, subprocess, time, urllib.parse, urllib.request, zipfile
from collections import Counter
UA='ImportCost-Regulatory-Data-Foundation-SourceAcquisition/1.0 (+official-source-verification)'
RAR_MAGIC=(b'Rar!\x1a\x07\x00', b'Rar!\x1a\x07\x01\x00')
class Links(html.parser.HTMLParser):
    def __init__(self): super().__init__(); self.hrefs=[]
    def handle_starttag(self, tag, attrs):
        if tag.lower()=='a':
            h=dict(attrs).get('href')
            if h: self.hrefs.append(h)
def sha256_bytes(b): return hashlib.sha256(b).hexdigest()
def sha256_file(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()
def safe_name(s):
    s=urllib.parse.unquote(s or '').replace('\\','/').split('/')[-1]
    s=re.sub(r'[^0-9A-Za-z._()\-\u4e00-\u9fff]+','_',s).strip('._')
    return s[:180] or 'source.bin'
def validate_magic(data, expected):
    if not data: return False,'empty'
    e=(expected or '').lower()
    if 'pdf' in e: return (data.startswith(b'%PDF'), 'pdf')
    if 'rar' in e: return (any(data.startswith(x) for x in RAR_MAGIC), 'rar')
    if 'html' in e: return (b'<html' in data[:4096].lower() or b'<!doctype' in data[:4096].lower(), 'html')
    return True,'untyped'
def request_bytes(url, timeout=180):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'*/*','Accept-Encoding':'identity'})
    t0=time.time()
    with urllib.request.urlopen(req,timeout=timeout) as r:
        data=r.read(); hdr={k.lower():v for k,v in r.headers.items()}
        return data, {'requestedUrl':url,'finalUrl':r.geturl(),'httpStatus':getattr(r,'status',200),'headers':hdr,'elapsedSeconds':round(time.time()-t0,3)}
def discover_attachments(source):
    out=[]; evidence=[]; exts=[x.lower() for x in source.get('attachmentExtensions',[])]
    for page in source.get('attachmentDiscoveryPages',[]):
        try:
            data,meta=request_bytes(page,120); p=Links(); p.feed(data.decode('utf-8','ignore')); found=[]
            for h in p.hrefs:
                u=urllib.parse.urljoin(meta['finalUrl'],h); path=urllib.parse.urlparse(u).path.lower()
                if not exts or any(path.endswith(ext) for ext in exts): found.append(u)
            found=list(dict.fromkeys(found)); out.extend(found)
            evidence.append({'page':page,'status':'SUCCESS','finalUrl':meta['finalUrl'],'sha256':sha256_bytes(data),'discovered':found})
        except Exception as e: evidence.append({'page':page,'status':'FAILED','error':f'{type(e).__name__}: {e}'})
    return list(dict.fromkeys(out)), evidence
def normalize_dbf(dbf_paths):
    try: from dbfread import DBF
    except Exception as e: return {'status':'FAILED','error':f'dbfread unavailable: {e}'}
    all_tables=[]; combined=[]
    for p in sorted(dbf_paths):
        last=None; rows=None; fields=None; encoding=None
        for enc in (None,'gb18030','gbk','cp936'):
            try:
                kwargs={'load':True,'char_decode_errors':'strict'}
                if enc: kwargs['encoding']=enc
                table=DBF(str(p),**kwargs); rows=[dict(r) for r in table]; fields=list(table.field_names); encoding=getattr(table,'encoding',enc); break
            except Exception as e: last=e
        if rows is None: return {'status':'FAILED','error':f'{p.name}: {type(last).__name__}: {last}'}
        norm=[]
        for r in rows:
            rr={}
            for k,v in r.items():
                if v is None: vv=None
                elif hasattr(v,'isoformat'): vv=v.isoformat()
                elif isinstance(v,(int,float,bool,str)): vv=v
                else: vv=str(v)
                rr[str(k)]=vv
            norm.append(rr)
        norm.sort(key=lambda x: json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')))
        table_hash=sha256_bytes(json.dumps(norm,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8'))
        all_tables.append({'filename':p.name,'sha256':sha256_file(p),'encoding':encoding,'fields':fields,'rowCount':len(norm),'semanticHash':table_hash})
        combined.extend({'table':p.name,'row':x} for x in norm)
    combined.sort(key=lambda x: json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')))
    return {'status':'SUCCESS','tables':all_tables,'normalizedRecordCount':len(combined),'semanticHash':sha256_bytes(json.dumps(combined,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8'))}
def acquire_one(source, outroot):
    sid=source['sourceId']; sdir=outroot/'raw'/sid; sdir.mkdir(parents=True,exist_ok=True)
    result={'sourceId':sid,'trustClass':source.get('trustClass'),'expectedAuthority':source.get('expectedAuthority'),'expectedDocumentNumber':source.get('expectedDocumentNumber'),'expectedTitle':source.get('expectedTitle'),'expectedVersion':source.get('expectedVersion'),'expectedMediaType':source.get('expectedMediaType'),'extractionType':source.get('extractionType'),'status':'FAILED','attempts':[]}
    candidates=list(source.get('primaryUrls',[]))+list(source.get('officialMirrorUrls',[])); discovered,disc_evidence=discover_attachments(source) if source.get('attachmentDiscoveryPages') else ([],[])
    result['attachmentDiscovery']=disc_evidence; candidates+=discovered; candidates=list(dict.fromkeys(candidates))
    if not candidates: result['error']='NO_CANDIDATE_URL'; return result
    for url in candidates[:6]:
        attempt={'url':url}
        try:
            data,meta=request_bytes(url); ok,kind=validate_magic(data,source.get('expectedMediaType')); attempt.update(meta); attempt['bytes']=len(data); attempt['sha256']=sha256_bytes(data); attempt['magicType']=kind; attempt['magicValid']=ok; result['attempts'].append(attempt)
            if not ok: continue
            cd=meta['headers'].get('content-disposition',''); m=re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)',cd,re.I); fn=safe_name(m.group(1) if m else urllib.parse.urlparse(meta['finalUrl']).path); ext=pathlib.Path(urllib.parse.urlparse(meta['finalUrl']).path).suffix
            if not pathlib.Path(fn).suffix and ext: fn+=ext
            raw=sdir/fn; raw.write_bytes(data); result.update({'status':'SUCCESS','selectedUrl':url,'finalUrl':meta['finalUrl'],'httpStatus':meta['httpStatus'],'httpHeaders':meta['headers'],'rawPath':str(raw.relative_to(outroot)),'rawFilename':fn,'rawBytes':len(data),'rawSha256':attempt['sha256'],'retrievedAt':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())})
            if source.get('extractionType')=='RAR_DBF':
                edir=outroot/'extracted'/sid; edir.mkdir(parents=True,exist_ok=True); proc=subprocess.run(['7z','x','-y',f'-o{edir}',str(raw)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True); result['extractExitCode']=proc.returncode; result['extractLogTail']=proc.stdout[-4000:]
                if proc.returncode!=0: result['status']='FAILED_EXTRACTION'; return result
                files=[]
                for p in sorted(edir.rglob('*')):
                    if p.is_file(): files.append({'path':str(p.relative_to(outroot)),'bytes':p.stat().st_size,'sha256':sha256_file(p)})
                result['extractedFiles']=files; dbfs=[p for p in edir.rglob('*') if p.is_file() and p.suffix.lower()=='.dbf']; result['dbfNormalization']=normalize_dbf(dbfs) if dbfs else {'status':'FAILED','error':'NO_DBF_AFTER_EXTRACTION'}
            return result
        except Exception as e: attempt['error']=f'{type(e).__name__}: {e}'; result['attempts'].append(attempt)
    result['error']='ALL_URLS_FAILED'; return result
def deterministic_zip(root, outzip):
    files=[p for p in root.rglob('*') if p.is_file() and p.resolve()!=outzip.resolve()]
    with zipfile.ZipFile(outzip,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(files,key=lambda x:str(x.relative_to(root))):
            rel=str(p.relative_to(root)); info=zipfile.ZipInfo(rel,(2026,1,1,0,0,0)); info.compress_type=zipfile.ZIP_DEFLATED; info.external_attr=(0o100644 & 0xFFFF)<<16; z.writestr(info,p.read_bytes())
def build_quorums(results):
    by={r['sourceId']:r for r in results}; e=[r for r in results if r['sourceId'].startswith('eaeu-ett-group-')]; es=[r for r in e if r['status']=='SUCCESS']
    q_e={'schemaVersion':'eaeu-tnved-source-quorum-v1','expectedGroupSources':96,'acquiredGroupSources':len(es),'missingSourceIds':[r['sourceId'] for r in e if r['status']!='SUCCESS'],'allGroupRawAcquired':len(es)==96,'sourceHashes':{r['sourceId']:r.get('rawSha256') for r in es},'publicationReady':False,'publicationGate':'RAW acquisition only; semantic comparison against NSI and amendment-reconstructed candidate still required'}
    cnids=['cn-2026-mof-tariff','cn-2026-mof-tariff-replica','cn-2026-gacc-declaration-directory']; q_cn={'schemaVersion':'cn-2026-nomenclature-source-quorum-v1','sources':{x:{'status':by.get(x,{}).get('status'),'sha256':by.get(x,{}).get('rawSha256'),'bytes':by.get(x,{}).get('rawBytes')} for x in cnids},'mofPrimaryAcquired':by.get(cnids[0],{}).get('status')=='SUCCESS','officialReplicaAcquired':by.get(cnids[1],{}).get('status')=='SUCCESS','gaccOperationalDirectoryAcquired':by.get(cnids[2],{}).get('status')=='SUCCESS','publicationReady':False,'publicationGate':'Parse 8-digit MOF + 10-digit GACC, validate parent integrity, units, 2025→2026 changes, and semantic reconciliation'}
    cms=[r for r in results if r['sourceId'].startswith('cn-cmcode2026b-') and r.get('status')=='SUCCESS' and r.get('dbfNormalization',{}).get('status')=='SUCCESS']; groups={}
    for r in cms: groups.setdefault(r['dbfNormalization']['semanticHash'],[]).append(r['sourceId'])
    best=max(groups.values(),key=len) if groups else []; q_cm={'schemaVersion':'cn-cmcode2026b-source-quorum-v1','officialReplicasAcquired':len(cms),'replicas':[{'sourceId':r['sourceId'],'rarSha256':r.get('rawSha256'),'semanticHash':r['dbfNormalization']['semanticHash'],'normalizedRecordCount':r['dbfNormalization']['normalizedRecordCount'],'tables':r['dbfNormalization'].get('tables',[])} for r in cms],'semanticGroups':groups,'semanticQuorumSatisfied':len(best)>=2,'matchingOfficialReplicas':best,'publicationReady':False,'publicationGate':'At least 2 official replicas semantic-equal, then reconcile against 2026A + cancellation + battery transition amendments'}
    return q_e,q_cn,q_cm
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--manifest',required=True); ap.add_argument('--output',default='runner-output'); ap.add_argument('--workers',type=int,default=12); a=ap.parse_args(); out=pathlib.Path(a.output); out.mkdir(parents=True,exist_ok=True); manifest=json.loads(pathlib.Path(a.manifest).read_text(encoding='utf-8')); sources=manifest['sources']
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as ex:
        fut={ex.submit(acquire_one,s,out):s['sourceId'] for s in sources}; results=[]
        for f in concurrent.futures.as_completed(fut):
            try: results.append(f.result())
            except Exception as e: results.append({'sourceId':fut[f],'status':'INTERNAL_ERROR','error':f'{type(e).__name__}: {e}'})
    results.sort(key=lambda x:x['sourceId']); normalized={'schemaVersion':'normalized-source-acquisition-v1','generatedAt':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'sourceCount':len(results),'statusCounts':dict(Counter(r['status'] for r in results)),'sources':results}; (out/'NORMALIZED_SOURCE_MANIFEST.json').write_text(json.dumps(normalized,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); qe,qc,qm=build_quorums(results)
    (out/'EAEU_TNVED_SOURCE_QUORUM.json').write_text(json.dumps(qe,ensure_ascii=False,indent=2)+'\n'); (out/'CN_2026_NOMENCLATURE_SOURCE_QUORUM.json').write_text(json.dumps(qc,ensure_ascii=False,indent=2)+'\n'); (out/'CN_CMCODE2026B_SOURCE_QUORUM.json').write_text(json.dumps(qm,ensure_ascii=False,indent=2)+'\n')
    report=['# P0 SOURCE ACQUISITION REPORT','',f"Sources: {len(results)}",f"Status counts: {normalized['statusCounts']}",f"EAEU groups acquired: {qe['acquiredGroupSources']}/96",f"CN MOF primary: {qc['mofPrimaryAcquired']}; official replica: {qc['officialReplicaAcquired']}; GACC directory: {qc['gaccOperationalDirectoryAcquired']}",f"CMCODE official replicas normalized: {qm['officialReplicasAcquired']}; semantic quorum >=2: {qm['semanticQuorumSatisfied']}",'','No dataset is publication-ready from acquisition alone. Foundation parsers/reconciliation gates remain mandatory.']; (out/'SOURCE_ACQUISITION_REPORT.md').write_text('\n'.join(report)+'\n'); bundle=pathlib.Path('OFFICIAL_SOURCE_BUNDLE.zip'); deterministic_zip(out,bundle); pathlib.Path('OFFICIAL_SOURCE_BUNDLE.zip.sha256').write_text(f"{sha256_file(bundle)}  OFFICIAL_SOURCE_BUNDLE.zip\n"); gate={'eaeuRaw96':qe['allGroupRawAcquired'],'cnMof':qc['mofPrimaryAcquired'],'cnGacc':qc['gaccOperationalDirectoryAcquired'],'cmcodeSemantic2':qm['semanticQuorumSatisfied']}; (out/'ACQUISITION_GATE.json').write_text(json.dumps(gate,indent=2)+'\n'); print(json.dumps({'statusCounts':normalized['statusCounts'],'gate':gate},ensure_ascii=False))
if __name__=='__main__': main()
