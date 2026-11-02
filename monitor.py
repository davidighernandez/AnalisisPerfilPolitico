import json, os, re, time, unicodedata, urllib.parse as up, urllib.request as ur, xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
cfg = json.load(open("config.json", encoding="utf-8")); now = datetime.now(timezone.utc)
def get(u): return ur.urlopen(ur.Request(u, headers={"User-Agent": "perfil-politico/1.0"}), timeout=30).read()
def norm(s): return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")
POS = "gana logro avanz apoy inaugur impuls propon respald exito benefic entreg mejor crece aprueb reconoc celebr lider fortalec".split()
NEG = "denunc acus corrup fraud critic escand investig imput polemi rechaz crisis violen desvi opac protest demand renunc detenid amenaz cuestion".split()
THEMES = {"seguridad": ["segur", "crimen", "violen", "polic"], "corrupción": ["corrup", "fraud", "desvi", "opac"],
 "economía": ["econom", "empleo", "salari", "inversi"], "salud": ["salud", "hospital"], "educación": ["educa", "escuela", "beca"],
 "agua y obras": ["agua", "obra", "bache", "carretera"], "campo": ["campo", "agric", "product"], "elecciones": ["elecc", "candidat", "encuesta", "campa", "voto"]}
STOP = set("de la el en y a los las del un una por con para que se su al lo como mas es no sus sobre entre ante tras ser fue ha han este esta tambien pero sin desde hasta ya nos o u e le les si hoy dice va".split())
def tono(t):
    w = norm(t).split(); s = sum(any(x.startswith(p) for p in POS) for x in w) - sum(any(x.startswith(p) for p in NEG) for x in w)
    return (s > 0) - (s < 0)
def nivel(medio, dom=""):
    k = norm(medio + " " + dom)
    for m, l in cfg["medios"].items():
        if norm(m) in k: return l
    return 4
def consulta(p): return "(" + " OR ".join('"%s"' % x for x in [p["nombre"]] + p["alias"]) + ")"
def gnews(p):
    u = "https://news.google.com/rss/search?" + up.urlencode({"q": consulta(p) + " when:14d", "hl": "es-419", "gl": "MX", "ceid": "MX:es-419"})
    out = []
    for it in ET.fromstring(get(u)).iter("item"):
        s = it.find("source"); m = s.text if s is not None else ""
        out.append((it.findtext("title").rsplit(" - ", 1)[0], it.findtext("link"), m, "", parsedate_to_datetime(it.findtext("pubDate")), 0))
    return out
def gdelt(p):
    u = "https://api.gdeltproject.org/api/v2/doc/doc?" + up.urlencode({"query": consulta(p) + " sourcelang:spanish", "mode": "ArtList", "maxrecords": 250, "format": "json", "timespan": "14d", "sort": "DateDesc"})
    out = []
    for a in json.loads(get(u)).get("articles", []):
        d = datetime.strptime(a["seendate"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        out.append((a["title"], a["url"], a.get("domain", ""), a.get("domain", ""), d, 1 if a.get("sourcecountry") not in ("", cfg["pais_gdelt"]) else 0))
    return out
def ficha(p):
    try:
        t = p.get("wikipedia") or json.loads(get("https://es.wikipedia.org/w/api.php?" + up.urlencode({"action": "opensearch", "search": p["nombre"], "limit": 1, "format": "json"})))[1][0]
        j = json.loads(get("https://es.wikipedia.org/api/rest_v1/page/summary/" + up.quote(t.replace(" ", "_"))))
        return {"t": j.get("title"), "x": j.get("extract", "")[:600], "u": j["content_urls"]["desktop"]["page"]}
    except Exception as e: print("sin ficha:", p["nombre"], e); return None
P = []
for p in cfg["personas"]:
    raw = []
    for f in (gnews, gdelt):
        try: raw += f(p)
        except Exception as e: print("fuente falló:", f.__name__, p["nombre"], e)
        time.sleep(6)
    nombres = [norm(x) for x in [p["nombre"]] + p["alias"]]; vistos, N = set(), []
    for t, u, m, dom, d, ext in sorted(raw, key=lambda r: r[4], reverse=True):
        k = norm(t)[:60]
        if k in vistos or not any(n in norm(t) for n in nombres): continue
        vistos.add(k); dias = (now - d).days
        if dias < 14: N.append([dias, 3 if ext else nivel(m, dom), m or dom, t, tono(t), u])
    sem = [n for n in N if n[0] < 7]; w, co, th = {}, Counter(), Counter()
    quitar = set(x for n in nombres for x in n.split())
    for n in sem:
        tn = norm(n[3])
        for x in set(re.findall(r"[a-zñ]{4,}", tn)):
            if x not in STOP and x not in quitar: a = w.setdefault(x, [0, 0]); a[0] += 1; a[1] += n[4]
        for g, ks in THEMES.items():
            if any(k in tn for k in ks): th[g] += 1
        for c in set(re.findall(r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?: [A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)+", n[3])):
            if norm(c) not in nombres and not any(norm(c) in x or x in norm(c) for x in nombres): co[c] += 1
    P.append({"nombre": p["nombre"], "alias": p["alias"], "ficha": ficha(p), "N": N,
      "w": [[k, v[0], round(v[1] / v[0], 2)] for k, v in sorted(w.items(), key=lambda i: -i[1][0])[:40] if v[0] > 1],
      "th": th.most_common(8), "co": [c for c in co.most_common(8) if c[1] > 1]})
os.makedirs("site", exist_ok=True)
open("site/data.js", "w", encoding="utf-8").write("var UPDATED=%s;var P=%s;" % (json.dumps(now.strftime("%d/%m/%Y %H:%M UTC")), json.dumps(P, ensure_ascii=False)))
import shutil; shutil.copy("template.html", "site/index.html"); print([(q["nombre"], len(q["N"])) for q in P])
