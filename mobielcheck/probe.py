from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    br=p.chromium.launch(executable_path="/usr/bin/google-chrome",headless=True)
    ctx=br.new_context(viewport={"width":390,"height":844},device_scale_factor=3,is_mobile=True,has_touch=True,user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Version/17.5 Mobile/15E148 Safari/604.1")
    pg=ctx.new_page()
    pg.goto("http://127.0.0.1:8741/?q=autisme+en+angst")
    print(pg.evaluate("""()=>[...document.querySelectorAll("a,span,p,code,dd")].filter(e=>e.scrollWidth>e.clientWidth+2 || e.getBoundingClientRect().width>395).slice(0,5).map(e=>e.tagName+"."+e.className+" w="+Math.round(e.getBoundingClientRect().width)+" sw="+e.scrollWidth+" "+(e.innerText||"").slice(0,80))"""))
    print(pg.evaluate("()=>{const b=document.getElementById('vergelijk');const s=getComputedStyle(b);return [s.position,s.display,s.bottom,s.top]}"))
    pg.goto("http://127.0.0.1:8741/vergelijken?ids=psycholoog-groesbeek&ids=0-tot-18&ids=rebis-kinder-psychiatrisch-centrum-cooperatie-vjggz")
    print(pg.evaluate("()=>{const t=document.querySelector('table');const w=t.parentElement;const s=getComputedStyle(w);return [w.tagName,w.className,s.overflowX,t.offsetWidth,getComputedStyle(t.querySelector('th')).position]}"))
    br.close()
