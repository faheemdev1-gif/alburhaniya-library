from html import escape

CSS = """
body{font-family:'Traditional Arabic','Noto Naskh Arabic',Tahoma,sans-serif;
  max-width:820px;margin:0 auto;padding:24px 20px 60px;line-height:2;
  font-size:19px;color:#1c1c1c;background:#fdfaf3;}
h1{font-size:1.5em;margin-bottom:.2em;}
h2{font-size:1.05em;color:#6b4b1e;font-weight:normal;margin-top:0;}
p.meta{color:#666;}
mark{background:#ffe08a;padding:0 2px;}
.result{border-bottom:1px solid #e6ddc4;padding:14px 0;}
.result h3{margin:0 0 4px;font-size:1em;}
.result h3 a{color:#0a5c8a;text-decoration:none;}
.result .snippet{margin:6px 0 0;text-align:justify;}
.result .occ{color:#8a6d1d;font-size:.85em;}
nav.crumbs{font-size:.85em;color:#555;margin:14px 0;}
nav.crumbs a{color:#0a5c8a;text-decoration:none;margin:0 4px;}
article.page-text p{margin:0 0 1em;text-align:justify;}
form.searchbox{margin:18px 0;}
form.searchbox input[type=text]{font-size:1.1em;padding:8px;width:60%;}
form.searchbox button{font-size:1.1em;padding:8px 16px;}
"""


def page_shell(title: str, body: str, description: str = "") -> str:
    desc = escape(description or title)
    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{desc}">
<title>{escape(title)}</title>
<style>{CSS}</style>
</head>
<body>
{body}
</body>
</html>
"""


def nav_bar(links: list[tuple[str, str]]) -> str:
    items = " | ".join(f'<a href="{href}">{escape(label)}</a>' for label, href in links)
    return f'<nav class="crumbs">{items}</nav>'


def search_form(q: str = "") -> str:
    return f"""<form class="searchbox" method="get" action="/search.html">
<input type="text" name="q" value="{escape(q)}" placeholder="اكتب كلمة للبحث...">
<button type="submit">بحث</button>
</form>"""
