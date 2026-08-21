#!/usr/bin/env python3
from __future__ import annotations
import concurrent.futures, hashlib, html, json, pathlib, re, time, urllib.request, urllib.parse, zipfile

INDEX='https://markirovka.ru/knowledge/tovarnye-gruppy/obschie-voprosy-gis/vnesenie-izmeneniy-v-atributy-kartochek-tovarov-v-kmt'
ROOT=pathlib.Path('honest-sign-attributes-output'); RAW=ROOT/'raw'
ROOT.mkdir(parents=True,exist_ok=True); RAW.mkdir(parents=True,exist_ok=True)
UA='Mozilla/5.0 (X11; Linux x86_64) ImportCost-Regulatory-Foundation/1.1'

def fetch(url, attempts=2, timeout=20):
    hist=[]
    for i in range(1,attempts+1):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'*/*'})
            with urllib.request.urlopen(req,timeout=timeout) as r:
                data=r.read(); hdr={k.lower():v for k,v in r.headers.items()}
                return data, getattr(r,'status',200), r.geturl(), hdr, hist+[{'attempt':i,'ok':True,'status':getattr(r,'status',200),'bytes':len(data)}]
        except Exception as e:
            hist.append({'attempt':i,'ok':False,'error':type(e).__name__+': '+str(e)[:500]})
            if i<attempts: time.sleep(i)
    return None,None,None,{},hist

page,status,final,hdr,idx_attempts=fetch(INDEX,attempts=3,timeout=30)
if not page: raise SystemExit('INDEX_FETCH_FAILED:'+json.dumps(idx_attempts,ensure_ascii=False))
text=page.decode('utf-8','replace')
links=[]
for m in re.finditer(r'href=["\']([^"\']+\.xlsx(?:\?[^"\']*)?)["\']',text,re.I):
    u=html.unescape(m.group(1)); u=urllib.parse.urljoin(INDEX,u)
    if '/upload/knowledge/' in u and u not in links: links.append(u)

def acquire(item):
    n,url=item
    data,status,final,hdr,attempts=fetch(url)
    fname=pathlib.Path(urllib.parse.unquote(urllib.parse.urlparse(url).path)).name or f'attribute_{n:02d}.xlsx'
    safe=f'{n:02d}__{fname}'.replace('/','_')
    media_ok=bool(data and data[:2]==b'PK' and len(data)>1000)
    sha=None
    if data:
        (RAW/safe).write_bytes(data); sha=hashlib.sha256(data).hexdigest()
    return {'ordinal':n,'url':url,'finalUrl':final,'httpStatus':status,'contentType':hdr.get('content-type'),
      'etag':hdr.get('etag'),'lastModified':hdr.get('last-modified'),'filename':safe if data else None,'bytes':len(data) if data else 0,
      'sha256':sha,'xlsxMagicValid':media_ok,'attempts':attempts,'acquired':media_ok}

with concurrent.futures.ThreadPoolExecutor(max_workers=min(12,max(1,len(links)))) as ex:
    results=list(ex.map(acquire,enumerate(links,1)))
results.sort(key=lambda r:r['ordinal'])
summary={'authority':'CRPT / GIS MT','sourceRole':'OFFICIAL_OPERATIONAL_SOURCE','indexUrl':INDEX,
 'indexHttpStatus':status,'indexSha256':hashlib.sha256(page).hexdigest(),'discovered':len(links),
 'acquired':sum(1 for r in results if r['acquired']),'failed':sum(1 for r in results if not r['acquired']),
 'expectedByFoundation':44,'allFetched':len(links)>=40 and all(r['acquired'] for r in results),'records':results}
(ROOT/'HONEST_SIGN_ATTRIBUTE_ACQUISITION.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
with zipfile.ZipFile(ROOT/'HONEST_SIGN_ATTRIBUTE_RAW_BUNDLE.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
    for p in sorted(RAW.glob('*')): z.write(p,p.relative_to(ROOT))
    z.write(ROOT/'HONEST_SIGN_ATTRIBUTE_ACQUISITION.json','HONEST_SIGN_ATTRIBUTE_ACQUISITION.json')
zb=ROOT/'HONEST_SIGN_ATTRIBUTE_RAW_BUNDLE.zip'; sha=hashlib.sha256(zb.read_bytes()).hexdigest()
(ROOT/'HONEST_SIGN_ATTRIBUTE_RAW_BUNDLE.zip.sha256').write_text(sha+'  HONEST_SIGN_ATTRIBUTE_RAW_BUNDLE.zip\n',encoding='utf-8')
print(json.dumps({k:summary[k] for k in ['discovered','acquired','failed','allFetched']},ensure_ascii=False))
