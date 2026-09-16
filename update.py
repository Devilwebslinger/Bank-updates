import json, re, hashlib, html as htmlmod
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
UPDATES = DATA / 'updates.json'
SOURCES = DATA / 'sources.json'
HEALTH = DATA / 'source-health.json'
LAST_NEW = DATA / 'last-new.json'

TODAY = date.today()
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; BankExamUpdatesBot/1.0; +GitHub Actions)'}
TIMEOUT = 25
KEYWORDS = re.compile(r'notification|corrigendum|vacanc|recruit|application|apply|call letter|admit|result|score|cut.?off|exam date|schedule|interview|shortlist|short.list|reserve list|wait list|addendum', re.I)
EXCLUDE = re.compile(r'fraud|tender|vendor|procurement|purchase|auction|holiday|press release', re.I)
DATE_RE = re.compile(r'\b(?:0?[1-9]|[12]\d|3[01])\s*[./-]\s*(?:0?[1-9]|1[0-2])\s*[./-]\s*(?:20)?\d{2}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+20\d{2}\b|\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+20\d{2}\b', re.I)

MONTHS = {m.lower(): i for i,m in enumerate(['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],1)}

def parse_date(s):
    if not s: return None
    s = re.sub(r'\s+', ' ', s.strip())
    for fmt in ('%d %b %Y','%d %B %Y','%d-%m-%Y','%d/%m/%Y','%d.%m.%Y','%b %d %Y','%B %d %Y'):
        try: return datetime.strptime(s.replace(',',''), fmt).date()
        except ValueError: pass
    m = re.search(r'(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20\d{2})', s, re.I)
    if m:
        return date(int(m.group(3)), MONTHS[m.group(2).lower()[:3]], int(m.group(1)))
    return None

def dates_from(text):
    out=[]
    for m in DATE_RE.findall(text or ''):
        d=parse_date(m)
        if d: out.append(d)
    return out

def fetch(url):
    r=requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
    r.raise_for_status()
    return r.text, r.url

def clean(s):
    return re.sub(r'\s+', ' ', htmlmod.unescape(s or '')).strip()

def classify(title):
    t=title.lower()
    if 'call letter' in t or 'admit card' in t or 'hall ticket' in t: return 'call'
    if 'result' in t or 'score card' in t or 'scorecard' in t: return 'result'
    if 'corrigendum' in t or 'addendum' in t or 'updated vacanc' in t: return 'new'
    if 'apply' in t or 'application' in t or 'recruitment' in t or 'notification' in t: return 'upcoming'
    return 'new'

def infer_exam(org, title):
    t=title.lower()
    patterns=[
      ('RRB XV','rrb'),('CSA-XV','csa'),('PO 2026','probationary officer'),('PO/MT XVI','po/mt'),
      ('SBI CBO','circle based officer'),('Junior Associates','junior associate'),('Local Bank Officer 2026','local bank officer'),
      ('Officer Recruitment 2026–27','officer'),('AO Scale I 2026','administrative officer'),('Grade B','grade b'),('Assistant','assistant'),
      ('Grade A','grade a')]
    for name,pat in patterns:
        if pat in t: return name
    return title[:90]

def make_candidate(source, title, url, context):
    org=source['name']; title=clean(title); context=clean(context)
    if not title or len(title)<6 or EXCLUDE.search(title): return None
    if not KEYWORDS.search(title + ' ' + context): return None
    ds=dates_from(title+' '+context)
    recent=[d for d in ds if d >= TODAY-timedelta(days=21)]
    detected=max(recent) if recent else None
    # Only publish automatically if it has a recent explicit date; this prevents old page archives flooding the feed.
    if not detected: return None
    exam=infer_exam(org,title)
    stage=title[:90]
    kind=classify(title)
    return {
      'org': org if org!='Bank of Baroda' else 'BOB',
      'exam': exam,
      'stage': stage,
      'date': detected.strftime('%d %b %Y'),
      'kind': kind,
      'text': f"{org} published: {title}.",
      'why': 'New dated official-source item detected during the daily check. Open the official source to verify the document and current instructions.',
      'url': url,
      'source': org,
      '_detected': detected.isoformat(),
      '_auto': True
    }

def parse_page(source, url, html):
    soup=BeautifulSoup(html,'html.parser')
    candidates=[]
    # Prefer actual anchors; include nearby parent text for dates.
    for a in soup.find_all('a', href=True):
        title=clean(a.get_text(' ', strip=True))
        href=urljoin(url,a.get('href'))
        if not title or href.startswith('javascript:') or href.startswith('#'): continue
        parent=a.parent
        context=clean(parent.get_text(' ', strip=True) if parent else '')
        # A little larger context for table/list rows.
        if len(context)<80 and parent and parent.parent:
            context=clean(parent.parent.get_text(' ', strip=True))
        c=make_candidate(source,title,href,context)
        if c: candidates.append(c)
    # IBPS pages sometimes expose dated text outside the link label; scan visible rows.
    if source['id']=='ibps':
        for row in soup.find_all(['tr','li','p']):
            txt=clean(row.get_text(' ',strip=True))
            if KEYWORDS.search(txt) and dates_from(txt):
                link=row.find('a',href=True)
                if link:
                    c=make_candidate(source,clean(link.get_text(' ',strip=True)),urljoin(url,link['href']),txt)
                    if c: candidates.append(c)
    return candidates

def check_source(source):
    results=[]; errors=[]; ok=False
    for url in source.get('pages',[]):
        try:
            raw, final=fetch(url); ok=True
            results.extend(parse_page(source,final,raw))
        except Exception as e:
            errors.append(f'{url}: {type(e).__name__}: {e}')
    return source, results, ok, errors

def main():
    old=json.loads(UPDATES.read_text()) if UPDATES.exists() else []
    sources=json.loads(SOURCES.read_text())
    bykey={hashlib.sha1((x.get('org','')+'|'+x.get('exam','')+'|'+x.get('stage','')+'|'+x.get('url','')).encode()).hexdigest():x for x in old}
    health=[]; new=[]
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures=[pool.submit(check_source,src) for src in sources]
        for fut in as_completed(futures):
            source, candidates, ok, errors=fut.result()
            health.append({'id':source['id'],'name':source['name'],'ok':ok,'candidates':len(candidates),'errors':errors,'checked_at':datetime.now(timezone.utc).isoformat()})
            for c in candidates:
                k=hashlib.sha1((c['org']+'|'+c['exam']+'|'+c['stage']+'|'+c['url']).encode()).hexdigest()
                if k not in bykey:
                    bykey[k]=c; new.append(c)
    cutoff=TODAY-timedelta(days=30)
    final=[]
    for x in bykey.values():
        if x.get('_auto'):
            try:
                if date.fromisoformat(x['_detected']) < cutoff: continue
            except Exception: continue
        final.append(x)
    def sort_key(x):
        d=x.get('_detected') or None
        if not d:
            pd=parse_date(x.get('date',''))
            d=pd.isoformat() if pd else '1970-01-01'
        rank={'urgent':0,'new':1,'call':1,'result':1,'upcoming':2}
        return (d, -rank.get(x.get('kind','new'),9))
    final.sort(key=sort_key, reverse=True)
    for x in final:
        x.pop('_detected',None); x.pop('_auto',None)
    UPDATES.write_text(json.dumps(final[:80],ensure_ascii=False,indent=2),encoding='utf-8')
    health.sort(key=lambda x:x['name'])
    HEALTH.write_text(json.dumps({'checked_at':datetime.now(timezone.utc).isoformat(),'sources':health,'new_candidates':len(new)},ensure_ascii=False,indent=2),encoding='utf-8')
    LAST_NEW.write_text(json.dumps(new[:30],ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Checked {len(sources)} sources; discovered {len(new)} new dated candidates; retained {len(final)} updates.')
    print('Healthy sources:', sum(1 for x in health if x['ok']), '/', len(health))

if __name__=='__main__': main()
