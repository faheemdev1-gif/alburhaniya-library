"""
Shell + styling for the server-rendered pages.

These pages exist for everything that cannot run JavaScript — a URL-fetch
tool, a crawler, curl. They now use the same design tokens, the same class
names and the same markup as the React reader (see frontend/src/index.css),
so a bayt looks like a bayt whichever door you came in through.
"""
from html import escape

CSS = """
:root{
  --paper:#f7f3ea; --paper-raised:#fffdf8; --paper-edge:#e6dcc6; --paper-sunk:#efe7d5;
  --ink:#211a11; --ink-muted:#6b5c47; --ink-faint:#9c8d76;
  --rubric:#9d3520; --gold:#b8922a; --gold-soft:#d9bf7a; --sage:#4c6b46;
  --hit:#f2d98a; --hit-ink:#4a3607;
}
@media (prefers-color-scheme: dark){
  :root{
    --paper:#171310; --paper-raised:#1f1a15; --paper-edge:#33291f; --paper-sunk:#120f0c;
    --ink:#ece2d0; --ink-muted:#a2917a; --ink-faint:#6f6252;
    --rubric:#e08a70; --gold:#d2ad4d; --gold-soft:#8a7133; --sage:#8fae87;
    --hit:#6a5216; --hit-ink:#ffeab8;
  }
}
*{box-sizing:border-box}
body{font-family:'Amiri','Noto Naskh Arabic','Traditional Arabic',serif;
  max-width:44rem;margin:0 auto;padding:24px 20px 72px;
  background:var(--paper);color:var(--ink);font-size:1.25rem;line-height:2.15}
a{color:var(--rubric)}
h1{font-size:1.45em;margin:0 0 .15em;line-height:1.5}
h2{font-size:1em;color:var(--ink-faint);font-weight:400;margin:0 0 1.5em}
p.meta{color:var(--ink-muted);font-size:.8em}
mark{background:var(--hit);color:var(--hit-ink);border-radius:2px;padding:0 .12em;font-weight:600}

nav.crumbs{font-size:.72em;color:var(--ink-faint);margin:1em 0;
  padding-bottom:.6em;border-bottom:1px solid var(--paper-edge)}
nav.crumbs a{margin:0 .4em;text-decoration:none}
nav.crumbs a:hover{text-decoration:underline}

/* search */
form.searchbox{margin:1.4em 0;display:flex;gap:.5em}
form.searchbox input[type=text]{flex:1;font:inherit;font-size:.85em;padding:.5em .7em;
  background:var(--paper-raised);color:var(--ink);
  border:1px solid var(--paper-edge);border-radius:4px}
form.searchbox input:focus{outline:2px solid var(--rubric);outline-offset:1px}
form.searchbox button{font:inherit;font-size:.85em;padding:.5em 1.2em;cursor:pointer;
  background:var(--gold);color:#211a11;border:0;border-radius:4px}
.result{border-bottom:1px solid var(--paper-edge);padding:1em 0}
.result h3{margin:0 0 .2em;font-size:.9em;font-weight:600}
.result h3 a{text-decoration:none}
.result .snippet{margin:.3em 0 0;text-align:justify;font-size:.85em;color:var(--ink-muted)}
.result .occ{color:var(--ink-faint);font-size:.7em;margin:0}

/* the text block */
article.page-text{max-width:64ch;margin-inline:auto}
.blk + .blk{margin-top:1.15em}
.blk-para{text-align:justify;margin:0}
.blk-para + .blk-para{text-indent:1.6em;margin-top:.5em}
.blk-para.empty{text-align:center;color:var(--ink-faint)}

.blk-heading{font-family:'Reem Kufi','Noto Naskh Arabic',sans-serif;
  font-size:.8em;font-weight:500;color:var(--rubric);line-height:1.6;
  margin:2em 0 0;display:flex;align-items:center;gap:.7em}
.blk-heading::after{content:'';flex:1;height:1px;
  background:linear-gradient(to left,transparent,var(--gold-soft))}

.blk-quote{border-inline-start:2px solid var(--gold-soft);
  padding-inline-start:1em;color:var(--sage);margin:0}

.blk-folio{text-align:center;font-family:system-ui,sans-serif;font-size:.62em;
  letter-spacing:.18em;color:var(--ink-faint);margin-top:2em}

.blk-divider{margin:2.2em auto;width:min(60%,18rem);height:1px;position:relative;
  background:linear-gradient(to left,transparent,var(--gold-soft),transparent)}
.blk-divider::after{content:'\\2741';position:absolute;top:50%;left:50%;
  transform:translate(-50%,-50%);background:var(--paper);color:var(--gold);
  font-size:.6rem;padding:0 .5rem;line-height:1}

/* the bayt — two balanced hemistichs meeting at a rosette, the way a diwan
   prints it */
.bayt{display:grid;grid-template-columns:1fr auto 1fr;align-items:baseline;
  gap:0 1.1em;margin:1.5em 0;line-height:1.95}
.bayt__sadr{text-align:left}
.bayt__ajuz{text-align:right}
.bayt__rosette{color:var(--gold);font-size:.7em;line-height:1;align-self:center;
  user-select:none}
.bayt__num,.bayt__ref{font-family:system-ui,sans-serif;font-size:.55em;
  color:var(--ink-faint);letter-spacing:.04em;white-space:nowrap;
  direction:ltr;unicode-bidi:isolate}
.bayt__meta{grid-column:1/-1;display:flex;justify-content:space-between;
  gap:1em;margin-top:-.35em}
.bayt--single{grid-template-columns:1fr}
.bayt--single .bayt__sadr,.bayt--single .bayt__ajuz{text-align:center}
@media (max-width:640px){
  .bayt{grid-template-columns:1fr;gap:.15em;margin:1.3em 0}
  .bayt__sadr,.bayt__ajuz{text-align:center}
  .bayt__rosette{display:none}
}

/* quotation inside running text */
.q-ayah{font-family:'Amiri Quran','Amiri',serif;color:var(--sage)}
.q-ayah::before{content:'\\FD3F';margin-inline-start:.15em;color:var(--gold)}
.q-ayah::after{content:'\\FD3E';margin-inline-end:.15em;color:var(--gold)}
.q-ref{font-family:system-ui,sans-serif;font-size:.6em;color:var(--ink-faint);
  margin-inline:.25em}
.q-hadith{color:var(--rubric)}
.q-hadith::before{content:'\\00AB'}
.q-hadith::after{content:'\\00BB'}
"""

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    "family=Amiri:wght@400;700&family=Amiri+Quran&family=Noto+Naskh+Arabic:wght@400;600"
    '&family=Reem+Kufi:wght@400;500&display=swap">'
)


def page_shell(title: str, body: str, description: str = "") -> str:
    desc = escape(description or title)
    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{desc}">
<meta name="color-scheme" content="light dark">
<title>{escape(title)}</title>
{FONTS}
<style>{CSS}</style>
</head>
<body>
{body}
</body>
</html>
"""


def nav_bar(links: list[tuple[str, str]]) -> str:
    items = " · ".join(f'<a href="{href}">{escape(label)}</a>' for label, href in links)
    return f'<nav class="crumbs">{items}</nav>'


def search_form(q: str = "") -> str:
    return f"""<form class="searchbox" method="get" action="/search.html">
<input type="text" name="q" value="{escape(q)}" placeholder="اكتب كلمة للبحث…">
<button type="submit">بحث</button>
</form>"""
