import sys,math
from playwright.sync_api import sync_playwright
url,prefix=sys.argv[1],sys.argv[2]; MAX=30000
with sync_playwright() as p:
  b=p.chromium.launch(); pg=b.new_page(viewport={"width":390,"height":844},device_scale_factor=2,is_mobile=True,has_touch=True)
  pg.goto(url,wait_until="networkidle")
  info=pg.evaluate("()=>({sw:document.documentElement.scrollWidth,h:document.documentElement.scrollHeight,n:document.querySelectorAll('.it').length,side:getComputedStyle(document.querySelector('.side')).position})")
  print("INFO",info,file=sys.stderr)
  h=info["h"]; k=max(1,math.ceil(h/MAX)); seg=math.ceil(h/k)
  for i in range(k):
    out=f"{prefix}.png" if k==1 else f"{prefix}-{i+1}.png"
    pg.screenshot(path=out,full_page=True,clip={"x":0,"y":i*seg,"width":390,"height":min(seg,h-i*seg)}); print(out)
