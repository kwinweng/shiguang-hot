import sys, time
src=open('perf.py').read().split('out = {}')[0].replace("BASE = sys.argv[1]; LABEL = sys.argv[2]; RUNS = int(sys.argv[3]) if len(sys.argv) > 3 else 3","BASE=sys.argv[1]")
exec(src)
with sync_playwright() as pw:
    b = pw.chromium.launch(channel='chrome', args=['--disable-features=OverscrollHistoryNavigation'])
    for run in range(2):
        c = b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=3, is_mobile=True, has_touch=True)
        c.add_init_script(INIT); page = c.new_page(); cdp = c.new_cdp_session(page)
        page.goto(BASE); page.wait_for_selector('#app:not([aria-busy])'); time.sleep(1.5)
        cdp.send('Emulation.setCPUThrottlingRate', {'rate': 4})
        for v in ('blogger', 'hot', 'favorites', 'channels', 'blogger', 'hot', 'channels'):
            start(page); t0 = time.time()
            page.locator(f'.tabbar button[data-view={v}]').tap(); time.sleep(0.8)
            print(run, v, stop(page))
        c.close()
