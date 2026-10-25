import json
from playwright.sync_api import sync_playwright
B="http://127.0.0.1:8741"; D="/workspace/zorgzoeker-mobilecheck/"
METRICS="""() => {const de=document.documentElement; const vw=window.innerWidth;
 const wide=[...document.querySelectorAll('body *')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&(r.right>vw+1)}).slice(0,8).map(e=>e.tagName+'.'+e.className+' r='+Math.round(e.getBoundingClientRect().right));
 const small=[...document.querySelectorAll('a,button,input,select,label.kies,summary')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&(r.height<44||r.width<44)}).slice(0,12).map(e=>e.tagName+'.'+e.className+' '+Math.round(e.getBoundingClientRect().width)+'x'+Math.round(e.getBoundingClientRect().height)+' "'+(e.innerText||e.value||'').trim().slice(0,25)+'"');
 const fs=[...document.querySelectorAll('p,td,th,li,span,label')].map(e=>parseFloat(getComputedStyle(e).fontSize)).filter(x=>x<14);
 return {scrollW:de.scrollWidth, vw, docH:de.scrollHeight, overflow:wide, smallTaps:small, tinyFontCount:fs.length, minFont:fs.length?Math.min(...fs):null};}"""
out={}
with sync_playwright() as p:
    br=p.chromium.launch(executable_path="/usr/bin/google-chrome",headless=True)
    ctx=br.new_context(viewport={"width":390,"height":844},device_scale_factor=3,is_mobile=True,has_touch=True,
      user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1")
    pg=ctx.new_page()
    def shot(n,full=False):
        pg.screenshot(path=D+n,full_page=full); out[n]=pg.evaluate(METRICS)
    pg.goto(B); shot("01_start.png"); shot("01_start_full.png",True)
    pg.fill("#q","smetvrees"); pg.click("button[type=submit]"); pg.wait_for_load_state()
    shot("02_smetvrees.png"); shot("02_smetvrees_full.png",True)
    pg.goto(B); pg.fill("#q","kind 9 jaar autisme Berg en Dal"); pg.click("button[type=submit]"); pg.wait_for_load_state()
    shot("03_berg_en_dal.png"); shot("03_berg_en_dal_full.png",True)
    # filters
    sels=pg.query_selector_all("form.zoekform select"); out["selects"]=[s.get_attribute("name") for s in sels]
    pg.select_option("select[name=gecontracteerd]","ja"); pg.click("button[type=submit]"); pg.wait_for_load_state()
    shot("04_filter_gecontracteerd.png",True)
    # result card
    k=pg.query_selector("article.kaart")
    if k: k.scroll_into_view_if_needed(); k.screenshot(path=D+"05_kaart.png")
    # compare
    pg.goto(B+"/?q=autisme+en+angst"); pg.wait_for_load_state()
    boxes=pg.query_selector_all("label.kies input"); out["n_kaarten"]=len(boxes)
    for b in boxes[:3]: b.scroll_into_view_if_needed(); b.tap()
    shot("06_selectie.png")
    pg.evaluate("document.getElementById('vergelijk').scrollIntoView()"); shot("06b_vergelijkbalk.png")
    btn=pg.query_selector("#vergelijk button, #vergelijk [type=submit]")
    pg.evaluate("document.getElementById('vergelijk').scrollIntoView()")
    btn.tap(); pg.wait_for_url("**/vergelijken**"); pg.wait_for_load_state("networkidle"); out["compare_url"]=pg.url
    shot("07_vergelijken.png")
    pg.evaluate("window.scrollTo(0,600)"); pg.screenshot(path=D+"07b_vergelijken_scroll.png")
    try: pg.screenshot(path=D+"07_vergelijken_full.png",full_page=True,timeout=60000)
    except Exception as e: out["fullerr"]=str(e)[:200]
    br.close()
print(json.dumps(out,indent=1))
