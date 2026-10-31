#!/usr/bin/env python3
"""Offline screenshots and interaction checks. Run: python3 shot.py"""
from pathlib import Path
import json
import os
import re
import tempfile

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
CHROMIUM = "/home/box/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome"
ITEMS = {"live": ".story", "hot": ".hot-card", "review": ".review-item"}
FIRST_TITLE = {"live": ".story-title", "hot": ".hot-title", "review": ".review-title"}
CATEGORIES = ["全部", "新闻", "财经", "消费", "科技"]


def click(page, action, value=None):
    selector = f'[data-action="{action}"]'
    if value is not None:
        selector += f'[data-value="{value}"]'
    page.locator(selector).first.click()


def wait_render(page):
    page.wait_for_timeout(80)


def tint_parts(page):
    value = page.evaluate('getComputedStyle(document.documentElement).getPropertyValue("--tint")')
    return [float(n) for n in re.findall(r'[\d.]+', value)]


def assert_typography(page):
    heavy = page.evaluate('''() => [...document.querySelectorAll('body *')]
        .filter(e => !e.closest('svg'))
        .filter(e => parseInt(getComputedStyle(e).fontWeight, 10) >= 500)
        .filter(e => !e.closest('.brand h1'))
        .map(e => `${e.tagName}.${e.className}:${getComputedStyle(e).fontWeight}`)''')
    assert not heavy, heavy


def assert_red_tint_contrast(page):
    ratio = page.evaluate('''() => {
      const el = document.querySelector('.about-letter');
      const nums = s => s.match(/[\\d.]+/g).map(Number);
      const lin = c => { c /= 255; return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
      const lum = rgb => 0.2126 * lin(rgb[0]) + 0.7152 * lin(rgb[1]) + 0.0722 * lin(rgb[2]);
      const fg = lum(nums(getComputedStyle(el).color));
      const bg = nums(getComputedStyle(el).backgroundColor);
      const alpha = bg.length > 3 ? bg[3] : 1;
      const bgLum = lum([bg[0] * alpha + 255 * (1 - alpha), bg[1] * alpha + 255 * (1 - alpha), bg[2] * alpha + 255 * (1 - alpha)]);
      return (Math.max(fg, bgLum) + 0.05) / (Math.min(fg, bgLum) + 0.05);
    }''')
    assert ratio >= 4.5, ratio


def close_dialog(page):
    click(page, "close")
    page.locator('[role="dialog"]').wait_for(state="detached")


def open_about(page):
    click(page, "about", "bar")
    page.locator('[role="dialog"]').wait_for()


def choose_category(page, category):
    click(page, "category", category)
    assert page.locator('.category-rail > .on').inner_text().strip() == category
    assert page.locator('[role="dialog"]').count() == 0
    assert page.locator('.overlay').count() == 0
    wait_render(page)


def swipe(page, dx, dy=0, selector='.feed-scroll'):
    page.evaluate('''({dx, dy, selector}) => {
      const feed = document.querySelector(selector);
      const rect = feed.getBoundingClientRect();
      const startX = rect.left + rect.width / 2;
      const startY = rect.top + rect.height / 2;
      const send = (type, x, y) => {
        const touch = new Touch({ identifier: 1, target: feed, clientX: x, clientY: y });
        const active = type === 'touchend' ? [] : [touch];
        feed.dispatchEvent(new TouchEvent(type, {
          touches: active, targetTouches: active, changedTouches: [touch],
          bubbles: true, cancelable: true,
        }));
      };
      send('touchstart', startX, startY);
      send('touchmove', startX + dx, startY + dy);
      send('touchend', startX + dx, startY + dy);
    }''', {'dx': dx, 'dy': dy, 'selector': selector})
    wait_render(page)


def active_category(page):
    return page.locator('.category-rail > .on').inner_text().strip()


def assert_tab_underline(page, selector='.feed-tabs button.on'):
    styles = page.evaluate('''(selector) => {
      const tab = document.querySelector(selector);
      return [getComputedStyle(tab).color, getComputedStyle(tab, '::after').backgroundColor];
    }''', selector)
    assert styles[0] == styles[1], styles


def assert_icon_viewboxes(page):
    boxes = page.locator('#app svg').evaluate_all('(els) => els.map(e => e.getAttribute("viewBox"))')
    assert boxes and all(box == '0 0 256 256' for box in boxes), boxes
    assert page.locator('#app svg[viewBox="0 0 24 24"]').count() == 0
    assert page.locator('#app svg[stroke], #app svg *[stroke]').count() == 0


def assert_no_lucide(page):
    for path in sorted(ROOT.glob('*.js')) + [ROOT / 'index.html']:
        text = path.read_text(encoding='utf-8')
        assert 'lucide' not in text.lower(), path.name
        assert 'viewBox="0 0 24 24"' not in text, path.name
    assert 'lucide' not in page.content().lower()


def assert_icons(page):
    assert page.locator('.category-rail > button').all_text_contents() == CATEGORIES
    assert page.locator('.category-rail > button svg').count() == len(CATEGORIES)
    assert page.locator('.bottom-nav button svg').count() == 3
    assert_icon_viewboxes(page)


def assert_hot_badges(page):
    assert page.locator('.hot-channels').count() == 0
    assert '1 个频道在说' not in page.locator('.feed-scroll').inner_text()
    assert page.locator('.hot-card').evaluate_all('''(els) => els.every(e => {
      const event = EVENTS.find(x => x.id === e.dataset.event);
      return event.count === 1 && !e.querySelector('.hot-channels');
    })''')


def hot_items(page):
    return page.locator('.hot-card').evaluate_all('''(els) => els.map(e => {
      const barEl = e.querySelector('.hot-bar');
      const bar = barEl.getBoundingClientRect();
      const track = e.querySelector('.hot-heat').getBoundingClientRect();
      const style = getComputedStyle(e);
      const source = e.querySelector('.hot-source');
      const sourceStyle = source ? getComputedStyle(source) : null;
      return {
        rank: Number(e.querySelector('.hot-rank').textContent),
        heat: Number(e.dataset.heat),
        top: e.classList.contains('hot-top'),
        row: e.classList.contains('hot-row'),
        percent: parseFloat(barEl.style.width),
        width: bar.width,
        track: track.width,
        background: style.backgroundColor,
        border: style.borderTopWidth,
        source: source ? {
          text: source.textContent.trim(),
          whiteSpace: sourceStyle.whiteSpace,
          textOverflow: sourceStyle.textOverflow,
          rects: source.getClientRects().length,
          height: source.getBoundingClientRect().height,
          lineHeight: parseFloat(sourceStyle.lineHeight),
        } : null,
      };
    })''')


def assert_hot_card_details(page):
    cards = page.locator('.hot-card').evaluate_all('''(els) => els.map(e => {
      const titleEl = e.querySelector('.hot-title');
      const titleStyle = getComputedStyle(titleEl);
      const event = EVENTS.find(x => x.id === e.dataset.event);
      const barEl = e.querySelector('.hot-bar');
      return {
        heat: Number(e.dataset.heat),
        text: titleEl.textContent,
        eventTitle: event.title,
        lineClamp: titleStyle.webkitLineClamp,
        overflow: titleStyle.overflow,
        percent: parseFloat(barEl.style.width),
        bar: barEl.getBoundingClientRect().width,
        track: e.querySelector('.hot-heat').getBoundingClientRect().width,
      };
    })''')
    assert cards, 'hot list is empty'
    for card in cards:
        assert card['lineClamp'] == '3', card
        assert card['overflow'] == 'hidden', card
        assert card['text'] == card['eventTitle'], card
    top_heat = max(card['heat'] for card in cards)
    assert cards[0]['heat'] == top_heat, cards[0]
    for card in cards:
        assert abs(card['bar'] / card['track'] - card['heat'] / top_heat) <= 0.015, card
        assert card['bar'] <= card['track'] + 0.5, card
    assert abs(cards[0]['bar'] / cards[0]['track'] - 1) <= 0.015, cards[0]
    assert cards[0]['percent'] == 100, cards[0]
    if len(cards) > 1 and cards[1]['heat'] < cards[0]['heat']:
        assert cards[1]['bar'] < cards[0]['bar'], cards[:2]


def assert_hot_ranking(page):
    assert_hot_card_details(page)
    items = hot_items(page)
    assert items, 'hot list is empty'
    heats = [item['heat'] for item in items]
    assert heats == sorted(heats, reverse=True), heats
    assert items[0]['rank'] == 1, items[0]
    assert abs(items[0]['percent'] - 100) <= 0.5, items[0]
    assert abs(items[0]['width'] / items[0]['track'] - 1) <= 0.01, items[0]
    assert [item['rank'] for item in items] == list(range(1, len(items) + 1)), [item['rank'] for item in items]
    max_heat = heats[0]
    previous_ratio = None
    previous_percent = None
    for item in items:
        ratio = item['width'] / item['track']
        assert abs(ratio - item['heat'] / max_heat) <= 0.02, (item, ratio)
        assert item['width'] <= item['track'] + 0.5, item
        if previous_ratio is not None:
            assert ratio <= previous_ratio + 0.002, (item, previous_ratio)
            assert item['percent'] <= previous_percent + 0.01, (item, previous_percent)
        previous_ratio = ratio
        previous_percent = item['percent']
        if item['rank'] >= 4:
            assert item['row'] and not item['top'], item
            assert item['background'] in ('transparent', 'rgba(0, 0, 0, 0)'), item
            assert item['border'] == '0px', item
            source = item['source']
            assert source and source['text'], item
            assert source['whiteSpace'] == 'nowrap', item
            assert source['textOverflow'] == 'ellipsis', item
            assert source['rects'] == 1, item
            assert source['height'] <= source['lineHeight'] * 1.5, item
        else:
            assert item['top'] and not item['row'], item
            assert item['source'] is None, item
    assert sum(1 for item in items if item['row']) == max(0, len(items) - 3), items


def centered_target(page):
    return page.evaluate('() => window.__centered[window.__centered.length - 1] || null')


def assert_centered(page, category):
    target = centered_target(page)
    assert target, 'scrollIntoView was not called'
    assert target['action'] == 'category', target
    assert target['text'] == category and target['value'] == category, target
    assert target['options'] and target['options'].get('inline') == 'center', target


def data_stats(page):
    return page.evaluate('''() => {
      const byCat = {};
      EVENTS.forEach(e => { byCat[e.category] = (byCat[e.category] || 0) + 1; });
      const days = [];
      EVENTS.forEach(e => {
        let day = days.find(d => d.key === e.dateKey);
        if (!day) { day = { key: e.dateKey, date: e.date, weekday: e.weekday, count: 0 }; days.push(day); }
        day.count++;
      });
      days.sort((a, b) => b.key.localeCompare(a.key));
      days.forEach(day => {
        const picked = EVENTS.filter(e => e.dateKey === day.key)
          .sort((a, b) => b.heat - a.heat || b.stamp - a.stamp)
          .slice(0, 5)
          .sort((a, b) => b.stamp - a.stamp);
        day.ids = picked.map(e => e.id);
        day.firstTitle = picked[0] ? picked[0].title : null;
      });
      const newest = EVENTS[0];
      const oldest = EVENTS[EVENTS.length - 1];
      return {
        total: EVENTS.length,
        byCat,
        days,
        renderedDays: days.reduce((n, d) => n + d.ids.length, 0),
        newest: {
          id: newest.id, title: newest.title, summary: newest.summary,
          sourceId: newest.sourceId, sourceName: newest.sourceName,
          category: newest.category, image: newest.image, date: newest.date,
        },
        oldestDate: oldest.date,
        channels: [...new Set(EVENTS.map(e => e.sourceId))].length,
      };
    }''')


def category_stats(page, category):
    return page.evaluate('''(category) => {
      const list = EVENTS.filter(e => category === '全部' || e.category === category);
      const days = [];
      list.forEach(e => {
        if (!days.some(d => d.key === e.dateKey)) days.push({ key: e.dateKey });
      });
      days.sort((a, b) => b.key.localeCompare(a.key));
      days.forEach(day => {
        const picked = list.filter(e => e.dateKey === day.key)
          .sort((a, b) => b.heat - a.heat || b.stamp - a.stamp)
          .slice(0, 5)
          .sort((a, b) => b.stamp - a.stamp);
        day.ids = picked.map(e => e.id);
      });
      return { live: list.length, review: days.reduce((n, d) => n + d.ids.length, 0), days };
    }''', category)


def explore_stats(page):
    return page.evaluate('''() => {
      const KAN = ['剧', '电影', '小说', '展览'];
      const play = PLAY.filter(x => !KAN.includes(x.tag));
      const kan = PLAY.filter(x => KAN.includes(x.tag));
      const shape = list => {
        const byTag = {};
        list.forEach(x => { byTag[x.tag] = (byTag[x.tag] || 0) + 1; });
        return {
          count: list.length,
          tags: [...new Set(list.map(x => x.tag))],
          ids: list.map(x => x.id),
          images: list.filter(x => x.img).map(x => x.img),
          byTag,
        };
      };
      return { play: shape(play), kan: shape(kan), buy: shape(BUY) };
    }''')


def scroll_feed(page, selector='.feed-scroll'):
    feed = page.locator(selector)
    height = feed.evaluate('(e) => e.scrollHeight')
    for top in range(0, height, 480):
        feed.evaluate('(e, top) => e.scrollTop = top', top)
        page.wait_for_timeout(60)
    feed.evaluate('(e) => e.scrollTop = e.scrollHeight')
    page.wait_for_timeout(120)
    feed.evaluate('(e) => e.scrollTop = 0')
    page.wait_for_timeout(80)


def assert_initial_view_images(page):
    assert page.locator('.bottom-nav button.on').inner_text() == '资讯'
    assert page.locator('.feed-tabs button.on').inner_text() == '实时'
    assert page.locator('.filters .category-rail > .on').inner_text().strip() == '全部'
    feed = page.locator('.feed-scroll')
    assert feed.evaluate('(e) => e.scrollTop') == 0, 'initial view is not at the top'
    page.wait_for_function('''() => {
      const feed = document.querySelector('.feed-scroll');
      if (!feed) return false;
      const box = feed.getBoundingClientRect();
      return [...feed.querySelectorAll('.feed-img')].filter(img => {
        if (!img.complete || img.naturalWidth <= 0) return false;
        const r = img.getBoundingClientRect();
        return r.top >= box.top - 0.5 && r.bottom <= box.bottom + 0.5
          && r.left >= box.left - 0.5 && r.right <= box.right + 0.5;
      }).length >= 2;
    }''', timeout=10000)
    inside = page.evaluate('''() => {
      const feed = document.querySelector('.feed-scroll');
      const box = feed.getBoundingClientRect();
      return [...feed.querySelectorAll('.feed-img')].filter(img => {
        if (!img.complete || img.naturalWidth <= 0) return false;
        const r = img.getBoundingClientRect();
        return r.top >= box.top - 0.5 && r.bottom <= box.bottom + 0.5
          && r.left >= box.left - 0.5 && r.right <= box.right + 0.5;
      }).length;
    }''')
    assert inside >= 2, inside
    assert feed.evaluate('(e) => e.scrollTop') == 0, 'image check must not scroll'


def chip_styles(page, selector):
    return page.locator(selector).evaluate_all('''(els) => els.map(e => {
      const s = getComputedStyle(e);
      return {
        background: s.backgroundColor,
        radius: [s.borderTopLeftRadius, s.borderTopRightRadius,
                 s.borderBottomRightRadius, s.borderBottomLeftRadius].join(' '),
        border: [s.borderTopWidth, s.borderRightWidth,
                 s.borderBottomWidth, s.borderLeftWidth].join(' '),
      };
    })''')


def assert_chip_style_parity(page):
    transparent = ('rgba(0, 0, 0, 0)', 'transparent')
    news = chip_styles(page, '.filters .category-rail > button')
    assert news, 'news category chips not found'
    assert all(c['background'] in transparent for c in news), news
    assert all(c['radius'] == '0px 0px 0px 0px' for c in news), news
    assert all(c['border'] == '0px 0px 0px 0px' for c in news), news
    assert len({(c['background'], c['radius'], c['border']) for c in news}) == 1, news
    click(page, 'section', 'explore')
    wait_render(page)
    assert page.locator('.explore-tabs button.on').count() == 1
    explore = chip_styles(page, '.explore-chips > button')
    assert explore, 'explore chips not found'
    assert all(c['background'] in transparent for c in explore), explore
    assert len({(c['background'], c['radius'], c['border']) for c in explore}) == 1, explore
    assert {(c['background'], c['radius'], c['border']) for c in explore} == \
           {(c['background'], c['radius'], c['border']) for c in news}, (news, explore)
    assert all(c['border'] == '0px 0px 0px 0px' for c in explore), explore
    assert all(c['radius'] == '0px 0px 0px 0px' for c in explore), explore
    click(page, 'section', 'news')
    wait_render(page)


def assert_feed_images(page):
    image_total = page.evaluate('() => REAL_ITEMS.filter(x => x.image).length')
    assert image_total > 0, image_total
    scroll_feed(page)
    images = page.locator('.feed-img').evaluate_all('''(els) => els.map(e => ({
      attr: e.getAttribute('src'),
      abs: e.src,
      fit: getComputedStyle(e).objectFit,
      loading: e.loading,
    }))''')
    assert len(images) == image_total, (len(images), image_total)
    assert all(i['attr'].startswith('img/feed/') and i['abs'].startswith('file:') for i in images), images
    assert all(i['fit'] == 'cover' and i['loading'] == 'lazy' for i in images), images
    assert page.locator('.story').evaluate_all('''(els) => els.every(e => {
      const item = REAL_ITEMS.find(x => 'real-' + x.id === e.dataset.event);
      return !!e.querySelector('.feed-img') === !!item.image
        && e.classList.contains('has-img') === !!item.image;
    })''')
    # Only lazy-loading attributes were asserted above; decode every image so
    # the count check proves all files load, including offscreen ones.
    page.evaluate('() => Promise.all([...document.querySelectorAll(".feed-img")]'
                  '.map(i => i.decode().catch(() => null)))')
    page.wait_for_function('''(total) => {
      const imgs = [...document.querySelectorAll('.feed-img')];
      return imgs.length === total && imgs.every(i => i.complete && i.naturalWidth > 0);
    }''', arg=image_total, timeout=10000)
    loaded = page.locator('.feed-img').evaluate_all(
        '(els) => els.filter(e => e.complete && e.naturalWidth > 0).length')
    assert loaded == image_total, (loaded, image_total)
    assert page.locator('.feed-scroll').evaluate('(e) => e.scrollTop') == 0


def assert_category_feed_images(page):
    assert page.locator('.feed-tabs button.on').inner_text() == '实时'
    for category in ('新闻', '财经', '消费', '科技'):
        choose_category(page, category)
        info = page.evaluate('''(category) => {
          const list = REAL_ITEMS.filter(x => x.category === category);
          const withImage = list.filter(x => x.image);
          return {
            events: list.length,
            images: withImage.length,
            first: withImage.length ? 'real-' + withImage[0].id : null,
          };
        }''', category)
        assert info['events'] > 0 and info['images'] > 0, (category, info)
        assert page.locator('.story').count() == info['events'], (category, info)
        assert page.locator('.feed-img').count() == info['images'], (category, info)
        image = page.locator(f'[data-event="{info["first"]}"] .feed-img')
        assert image.count() == 1, (category, info)
        image.evaluate('(e) => e.scrollIntoView({ block: "center" })')
        page.wait_for_function('''(id) => {
          const img = document.querySelector(`[data-event="${id}"] .feed-img`);
          return !!img && img.complete && img.naturalWidth > 0;
        }''', arg=info['first'], timeout=3000)
        loaded = image.evaluate('''(e) => ({
          attr: e.getAttribute('src'), abs: e.src, width: e.naturalWidth,
          fit: getComputedStyle(e).objectFit, loading: e.loading,
        })''')
        assert loaded['loading'] == 'lazy', (category, loaded)
        assert loaded['attr'].startswith('img/feed/') and loaded['abs'].startswith('file:'), (category, loaded)
        assert loaded['fit'] == 'cover' and loaded['width'] > 0, (category, loaded)
    choose_category(page, '全部')


def assert_explore(page, explore):
    for tab, label in (('play', '好玩'), ('kan', '好看'), ('buy', '好买')):
        click(page, 'explore-tab', tab)
        wait_render(page)
        assert page.locator('.explore-tabs button.on').inner_text() == label
        assert page.locator('.explore-tabs [aria-pressed="true"]').count() == 1
        info = explore[tab]
        items = page.locator('.explore-item')
        assert items.count() == info['count'], (tab, items.count(), info['count'])
        ids = items.evaluate_all('(els) => els.map(e => e.dataset.value)')
        assert ids == info['ids'], (tab, ids, info['ids'])
        chip_tags = page.locator('.explore-chips button').evaluate_all('(els) => els.map(e => e.dataset.value)')
        assert chip_tags == ['全部'] + info['tags'], (tab, chip_tags, info['tags'])
        for tag in info['tags']:
            click(page, 'explore-tag', tag)
            wait_render(page)
            expected_ids = page.evaluate('''([kind, tag]) => {
              const KAN = ['剧', '电影', '小说', '展览'];
              const list = kind === 'buy' ? BUY : PLAY.filter(x => (kind === 'kan') === KAN.includes(x.tag));
              return list.filter(x => x.tag === tag).map(x => x.id);
            }''', [tab, tag])
            assert page.locator('.explore-item').evaluate_all('(els) => els.map(e => e.dataset.value)') == expected_ids, (tab, tag)
            assert page.locator('.explore-tabs button.on').inner_text() == label
        click(page, 'explore-tag', '全部')
        wait_render(page)
        assert page.locator('.explore-item').count() == info['count']
        assert page.locator('.explore-item.has-img').count() == len(info['images'])
        if info['images']:
            page.wait_for_timeout(150)
            imgs = page.locator('.explore-img').evaluate_all('''(els) => els.map(e => ({
              attr: e.getAttribute('src'), abs: e.src, complete: e.complete,
              width: e.naturalWidth, fit: getComputedStyle(e).objectFit,
            }))''')
            assert len(imgs) == len(info['images']), (tab, imgs)
            assert all(i['complete'] and i['width'] > 0 for i in imgs), imgs
            assert all(i['attr'].startswith('img/explore/') and i['abs'].startswith('file:') for i in imgs), imgs
            assert all(i['fit'] == 'cover' for i in imgs), imgs
        first_id = ids[0]
        click(page, 'explore', first_id)
        page.locator('[role="dialog"]').wait_for()
        assert page.locator('#dialog-title').inner_text() == '探索详情'
        expected_sources = page.evaluate('''([kind, id]) => {
          const all = kind === 'buy' ? BUY : PLAY;
          return all.find(x => x.id === id).src.length;
        }''', [tab, first_id])
        assert page.locator('.sheet-body .explore-source').count() == expected_sources
        assert page.locator('.sheet-body a[href^="http"]').count() == 0
        assert_typography(page)
        assert_icon_viewboxes(page)
        close_dialog(page)
        assert page.locator('.explore-tabs button.on').inner_text() == label


def channel_snapshot(page):
    return page.evaluate('''() => {
      const raw = localStorage.getItem('rebang.lastSeen');
      const seen = raw ? JSON.parse(raw) : null;
      const newest = {};
      REAL_ITEMS.forEach(item => {
        if (!newest[item.ch] || Date.parse(item.ts) > Date.parse(newest[item.ch])) newest[item.ch] = item.ts;
      });
      const counts = {};
      CHANNELS.forEach(channel => {
        const at = seen && seen[channel.id] ? Date.parse(seen[channel.id]) : NaN;
        counts[channel.id] = REAL_ITEMS.filter(item => item.ch === channel.id && Date.parse(item.ts) > at).length;
      });
      return { seen, newest, counts, channels: CHANNELS };
    }''')


def group_options(page):
    return page.locator('.group-sheet .group-option').evaluate_all('''els => els.map(e => ({
      ch: e.dataset.ch,
      name: e.querySelector('.group-option-name') ? e.querySelector('.group-option-name').textContent.trim() : '',
      on: e.classList.contains('on'),
      pressed: e.getAttribute('aria-pressed'),
      badge: e.querySelector('.unread-badge') ? e.querySelector('.unread-badge').textContent.trim() : null,
    }))''')


def assert_group_dot_layout(page):
    rects = page.evaluate('''() => {
      const dot = document.querySelector('.group-btn .group-dot');
      const label = document.querySelector('.group-btn .group-label');
      if (!dot || !label) return null;
      const box = el => { const r = el.getBoundingClientRect(); return { left: r.left, right: r.right, top: r.top, bottom: r.bottom }; };
      return { dot: box(dot), label: box(label) };
    }''')
    assert rects, 'group dot or label missing'
    dot, label = rects['dot'], rects['label']
    intersects = (dot['left'] < label['right'] and dot['right'] > label['left']
                  and dot['top'] < label['bottom'] and dot['bottom'] > label['top'])
    assert not intersects, rects


def assert_filter_row_layout(page):
    labels = page.locator('.filters .category-rail > button').evaluate_all('''els => els.map(e => {
      const label = [...e.children].find(c => c.tagName === 'SPAN' && !c.classList.contains('i'));
      return {
        text: e.textContent.trim(),
        button: { scrollWidth: e.scrollWidth, clientWidth: e.clientWidth },
        label: label ? { scrollWidth: label.scrollWidth, clientWidth: label.clientWidth } : null,
      };
    })''')
    assert labels, 'category rail buttons not found'
    for item in labels:
        assert item['button']['scrollWidth'] <= item['button']['clientWidth'], item
        if item['label'] is not None:
            assert item['label']['scrollWidth'] <= item['label']['clientWidth'], item
    group = page.locator('.filters .group-btn')
    assert group.count() == 1
    layout = page.evaluate('''() => {
      const group = document.querySelector('.filters .group-btn');
      if (!group) return null;
      const r = group.getBoundingClientRect();
      return {
        box: { left: r.left, right: r.right, top: r.top, bottom: r.bottom },
        viewport: { width: innerWidth, height: innerHeight },
      };
    }''')
    assert layout, 'group button has no box'
    box, viewport = layout['box'], layout['viewport']
    assert box['left'] >= -0.5 and box['right'] <= viewport['width'] + 0.5, layout
    assert box['top'] >= -0.5 and box['bottom'] <= viewport['height'] + 0.5, layout


def assert_selected_category_visible(page):
    boxes = page.evaluate('''() => {
      const strip = document.querySelector('.filters .category-rail');
      const button = strip ? strip.querySelector('button.on') : null;
      if (!strip || !button) return null;
      const s = strip.getBoundingClientRect();
      const b = button.getBoundingClientRect();
      return {
        strip: { left: s.left, right: s.right, fade: parseFloat(getComputedStyle(strip).getPropertyValue('--rail-fade')) },
        faded: strip.classList.contains('can-scroll-right'),
        button: { left: b.left, right: b.right, text: button.textContent.trim() },
      };
    }''')
    assert boxes, 'selected category or strip missing'
    strip, button, faded = boxes['strip'], boxes['button'], boxes['faded']
    assert button['left'] >= strip['left'] - 0.5, boxes
    right_limit = strip['right'] - strip['fade'] if faded else strip['right']
    assert button['right'] <= right_limit + 0.5, boxes


def assert_rail_right_fade(page):
    styles = page.evaluate('''() => {
      const strip = document.querySelector('.filters .category-rail');
      if (!strip) return null;
      const style = getComputedStyle(strip);
      return { mask: style.maskImage, webkit: style.webkitMaskImage };
    }''')
    assert styles, 'category strip missing'
    assert 'gradient' in (styles['mask'] or '') or 'gradient' in (styles['webkit'] or ''), styles


def assert_group_filters(page):
    snapshot = channel_snapshot(page)
    assert snapshot['seen'], 'rebang.lastSeen was not seeded'
    for channel in snapshot['channels']:
        value = snapshot['seen'].get(channel['id'])
        assert isinstance(value, str) and 'T' in value, (channel, snapshot['seen'])
    assert any(count > 0 for count in snapshot['counts'].values()), snapshot['counts']
    assert any(count == 0 for count in snapshot['counts'].values()), snapshot['counts']

    click(page, 'section', 'news')
    wait_render(page)
    click(page, 'tab', 'live')
    choose_category(page, '全部')
    assert page.locator('.group-btn').count() == 0
    assert page.locator('.channel-tag').count() == 0
    assert page.locator('.channel-row').count() == 0
    assert page.locator('.calendar-btn').count() == 0

    category = '新闻'
    choose_category(page, category)
    expected = [channel for channel in snapshot['channels'] if channel['category'] == category]
    assert expected
    group = page.locator('.group-btn')
    assert group.count() == 1
    expected_total = sum(snapshot['counts'][channel['id']] for channel in expected)
    assert expected_total > 0, (category, snapshot['counts'])
    expected_label = f'选择群组，{expected_total} 条未读' if expected_total else '选择群组'
    assert group.get_attribute('aria-label') == expected_label, group.get_attribute('aria-label')
    assert group.get_attribute('aria-expanded') == 'false'
    assert group.locator('svg').count() == 1
    assert '群组' in group.inner_text()
    dot = page.locator('.group-btn .group-dot')
    assert dot.count() == 1
    assert int(dot.inner_text()) == expected_total, (dot.inner_text(), expected_total)
    assert_group_dot_layout(page)
    assert_filter_row_layout(page)
    assert_touch_targets(page, ['.group-btn'])

    group.click()
    page.locator('[role="dialog"]').wait_for()
    assert group.get_attribute('aria-expanded') == 'true'
    assert page.locator('.group-sheet').count() == 1
    assert page.locator('.group-sheet .group-option[data-ch="liangjiahepost"]').count() == 0
    assert page.locator('#dialog-title').inner_text() == f'{category} · 群组'
    options = group_options(page)
    assert [option['ch'] for option in options] == [channel['id'] for channel in expected]
    assert [option['name'] for option in options] == [channel['name'] for channel in expected]
    expected_badges = [str(snapshot['counts'][channel['id']]) if snapshot['counts'][channel['id']] else None
                       for channel in expected]
    assert [option['badge'] for option in options] == expected_badges, (options, expected_badges)
    assert page.locator('.group-sheet .unread-badge').count() >= 1
    assert_typography(page)
    assert_touch_targets(page, ['.group-option'])

    badge = page.locator('.group-sheet .unread-badge').first
    style = badge.evaluate('''e => {
      const s = getComputedStyle(e);
      return { weight: s.fontWeight, size: parseFloat(s.fontSize), background: s.backgroundColor };
    }''')
    accent = page.evaluate('() => getComputedStyle(document.querySelector(".feed-tabs button.on")).color')
    assert style['weight'] == '400', style
    assert style['size'] <= 11, style
    assert style['background'] == accent, (style, accent)
    assert int(badge.inner_text()) >= 1

    target = next(channel for channel in expected if snapshot['counts'][channel['id']] > 0)
    page.locator(f'.group-sheet .group-option[data-ch="{target["id"]}"]').click()
    page.locator('[role="dialog"]').wait_for(state='detached')
    wait_render(page)
    assert page.locator('.channel-tag').count() == 1
    assert page.locator('.channel-tag-clear').count() == 1
    assert target['name'] in page.locator('.channel-tag').inner_text()
    assert page.locator('.filter-actions .channel-tag').count() == 1
    assert page.locator('.filter-actions .group-btn').count() == 1
    assert group.get_attribute('aria-expanded') == 'false'
    assert page.locator('.feed-scroll').evaluate('(e) => e.scrollTop') == 0
    assert_touch_targets(page, ['.channel-tag-clear'])
    assert_filter_row_layout(page)
    expected_ids = page.evaluate('(ch) => EVENTS.filter(e => e.sourceId === ch).map(e => e.id)', target['id'])
    assert page.locator('.story').evaluate_all('(els) => els.map(e => e.dataset.event)') == expected_ids
    assert page.locator('.story').evaluate_all('(els, ch) => els.every(e => e.dataset.ch === ch)', target['id'])
    stored = page.evaluate("() => JSON.parse(localStorage.getItem('rebang.lastSeen'))")
    assert stored[target['id']] == snapshot['newest'][target['id']], (stored, snapshot['newest'])
    remaining = expected_total - snapshot['counts'][target['id']]
    dots = page.locator('.group-btn .group-dot')
    assert dots.count() == (1 if remaining else 0), remaining
    if remaining:
        assert int(dots.inner_text()) == remaining
        assert_group_dot_layout(page)

    group.click()
    page.locator('[role="dialog"]').wait_for()
    reopened = group_options(page)
    viewed = next(option for option in reopened if option['ch'] == target['id'])
    assert viewed['badge'] is None, viewed
    close_dialog(page)

    page.locator('.channel-tag-clear').click()
    wait_render(page)
    assert page.locator('.channel-tag').count() == 0
    assert page.locator('.feed-scroll').evaluate('(e) => e.scrollTop') == 0
    assert page.evaluate('document.activeElement && document.activeElement.classList.contains("group-btn")')
    category_total = page.evaluate('(category) => EVENTS.filter(e => e.category === category).length', category)
    assert page.locator('.story').count() == category_total
    assert page.locator('.story').evaluate_all(
        '(els) => els.every(e => e.dataset.category === "新闻")')

    group.click()
    page.locator('[role="dialog"]').wait_for()
    page.locator(f'.group-sheet .group-option[data-ch="{expected[0]["id"]}"]').click()
    page.locator('[role="dialog"]').wait_for(state='detached')
    wait_render(page)
    assert page.locator('.channel-tag').count() == 1
    choose_category(page, '财经')
    assert page.locator('.channel-tag').count() == 0
    assert page.locator('.group-btn').count() == 1
    finance_total = page.evaluate('() => EVENTS.filter(e => e.category === "财经").length')
    assert page.locator('.story').count() == finance_total

    news_channels = [channel['id'] for channel in expected]
    for tab, selector in (('hot', '.hot-card'), ('review', '.review-item')):
        click(page, 'tab', tab)
        wait_render(page)
        choose_category(page, category)
        assert page.locator('.group-btn').count() == 1
        assert page.locator(f'{selector}[data-ch="liangjiahepost"]').count() == 0
        page.locator('.group-btn').click()
        page.locator('[role="dialog"]').wait_for()
        pick = news_channels[0]
        page.locator(f'.group-sheet .group-option[data-ch="{pick}"]').click()
        page.locator('[role="dialog"]').wait_for(state='detached')
        wait_render(page)
        assert page.locator('.channel-tag').count() == 1
        assert page.locator(selector).count() > 0, (tab, pick)
        assert page.locator(selector).evaluate_all('(els, ch) => els.every(e => e.dataset.ch === ch)', pick), tab
        page.locator('.channel-tag-clear').click()
        wait_render(page)
        assert page.locator('.channel-tag').count() == 0
        assert page.locator(selector).count() > 0, tab
        choose_category(page, '全部')

    click(page, 'tab', 'live')
    choose_category(page, '全部')

    # A pick made while the preview is in its error state must not mark the channel read.
    current = channel_snapshot(page)
    pending = next((channel for channel in current['channels'] if current['counts'][channel['id']] > 0), None)
    assert pending, current['counts']
    choose_category(page, pending['category'])
    before = page.evaluate("(ch) => JSON.parse(localStorage.getItem('rebang.lastSeen'))[ch]", pending['id'])
    open_about(page)
    click(page, "status", "error")
    page.locator('[role="dialog"]').wait_for(state='detached')
    page.get_by_text('加载失败', exact=True).wait_for()
    page.locator('.group-btn').click()
    page.locator('[role="dialog"]').wait_for()
    page.locator(f'.group-sheet .group-option[data-ch="{pending["id"]}"]').click()
    page.locator('[role="dialog"]').wait_for(state='detached')
    wait_render(page)
    after = page.evaluate("(ch) => JSON.parse(localStorage.getItem('rebang.lastSeen'))[ch]", pending['id'])
    assert after == before, (pending['id'], before, after)
    click(page, "retry")
    wait_render(page)
    choose_category(page, "全部")
    assert page.locator('[data-ch="liangjiahepost"]').count() == 0


def assert_explore_swipe(page, explore):
    click(page, 'section', 'explore')
    wait_render(page)
    click(page, 'explore-tab', 'play')
    wait_render(page)

    def item_ids():
        return page.locator('.explore-item').evaluate_all('(els) => els.map(e => e.dataset.value)')

    assert page.locator('.explore-tabs button.on').inner_text() == '好玩'
    assert item_ids() == explore['play']['ids']
    swipe(page, -90, selector='.explore-scroll')
    assert page.locator('.explore-tabs button.on').inner_text() == '好看'
    assert item_ids() == explore['kan']['ids']
    assert page.locator('.explore-chips > .on').inner_text() == '全部'
    assert page.locator('.ptr-indicator').count() == 0
    swipe(page, -90, selector='.explore-scroll')
    assert page.locator('.explore-tabs button.on').inner_text() == '好买'
    assert item_ids() == explore['buy']['ids']
    swipe(page, -90, selector='.explore-scroll')
    assert page.locator('.explore-tabs button.on').inner_text() == '好买'
    assert item_ids() == explore['buy']['ids']
    swipe(page, 90, selector='.explore-scroll')
    assert page.locator('.explore-tabs button.on').inner_text() == '好看'
    swipe(page, 90, selector='.explore-scroll')
    assert page.locator('.explore-tabs button.on').inner_text() == '好玩'
    swipe(page, 90, selector='.explore-scroll')
    assert page.locator('.explore-tabs button.on').inner_text() == '好玩'
    swipe(page, -40, selector='.explore-scroll')
    assert page.locator('.explore-tabs button.on').inner_text() == '好玩'
    assert page.locator('.ptr-indicator').count() == 0
    click(page, 'section', 'news')
    wait_render(page)


def assert_day_view(page, stats):
    click(page, 'section', 'news')
    wait_render(page)
    click(page, 'tab', 'review')
    wait_render(page)
    choose_category(page, '全部')
    calendar = page.locator('.calendar-btn')
    assert calendar.count() == 1
    assert calendar.get_attribute('aria-label') == '选择日期'
    for tab in ('live', 'hot'):
        click(page, 'tab', tab)
        wait_render(page)
        assert page.locator('.calendar-btn').count() == 0, tab
    click(page, 'tab', 'review')
    wait_render(page)
    assert page.locator('.calendar-btn').count() == 1

    calendar.click()
    page.locator('[role="dialog"]').wait_for()
    assert page.locator('#dialog-title').inner_text() == '选择日期'
    picker = page.locator('.date-picker')
    assert picker.count() == 1
    assert '90' in picker.inner_text(), picker.inner_text()
    days = page.evaluate('() => Object.keys(HOT_SNAPSHOTS).sort()')
    assert days
    all_days = picker.locator('[data-day]').evaluate_all(
        '(els) => els.map(e => ({ day: e.dataset.day, disabled: e.disabled }))')
    available = [day['day'] for day in all_days if not day['disabled']]
    disabled = [day['day'] for day in all_days if day['disabled']]
    assert available == days, (available, days)
    assert disabled, all_days
    assert any(day < days[0] for day in disabled), disabled
    assert any(day > days[-1] for day in disabled), disabled
    assert_touch_targets(page, ['.date-picker .date-day'])

    day = days[-2] if len(days) > 1 else days[0]
    assert day != days[-1]
    picker.locator(f'[data-day="{day}"]').click()
    page.locator('[role="dialog"]').wait_for(state='detached')
    wait_render(page)
    label = f"{int(day[5:7])}月{int(day[8:10])}日"
    assert page.locator('.day-title').inner_text() == f'{label} 热点'
    assert page.locator('.day-toggle button.on').inner_text() == '热点'
    assert page.locator('.filters, .group-btn, .channel-tag').count() == 0
    ranking = page.evaluate('(day) => HOT_SNAPSHOTS[day]', day)
    rendered = page.locator('.hot-card').evaluate_all('(els) => els.map(e => e.dataset.event)')
    assert rendered == [f'real-{item_id}' for item_id in ranking], (rendered, ranking)
    day_total = page.evaluate('(day) => EVENTS.filter(e => e.dateKey === day).length', day)
    assert len(rendered) == day_total, (len(rendered), day_total)
    assert page.locator('.hot-card').evaluate_all(
        '(els, day) => els.every(e => EVENTS.find(x => x.id === e.dataset.event).dateKey === day)', day)
    heats = page.locator('.hot-card').evaluate_all('(els) => els.map(e => Number(e.dataset.heat))')
    assert heats == sorted(heats, reverse=True), heats
    assert page.locator('.hot-card').evaluate_all('(els) => els.every(e => !!e.dataset.ch)')
    assert page.locator('.day-count').inner_text() == f'{len(rendered)} 件事'
    assert_hot_card_details(page)

    click(page, 'day-tab', 'review')
    wait_render(page)
    assert page.locator('.day-title').inner_text() == f'{label} 回顾'
    assert page.locator('.day-toggle button.on').inner_text() == '回顾'
    expected_ids = page.evaluate('(day) => EVENTS.filter(e => e.dateKey === day).map(e => e.id)', day)
    assert page.locator('.review-day').count() == 1
    assert page.locator('.review-day').get_attribute('data-day') == day
    assert page.locator('.review-item').evaluate_all('(els) => els.map(e => e.dataset.value)') == expected_ids
    assert page.locator('.review-item').count() == day_total
    assert page.locator('.review-date small').inner_text() == f'{day_total} 件事'
    assert page.locator('.day-count').inner_text() == f'{day_total} 件事'

    click(page, 'day-today')
    wait_render(page)
    assert page.locator('.day-title').count() == 0
    assert page.locator('.day-toggle').count() == 0
    assert page.locator('.filters .category-rail').count() == 1
    assert page.locator('.feed-tabs button.on').inner_text() == '回顾'
    assert page.locator('.category-rail > .on').inner_text().strip() == '全部'
    assert page.locator('.calendar-btn').count() == 1
    assert page.locator('.review-day').count() == len(stats['days'])


def capture_b4_shots(page):
    page.evaluate("localStorage.removeItem('rebang.lastSeen')")
    page.goto(f'{(ROOT / "index.html").as_uri()}?t=light')
    page.locator('.story').first.wait_for()
    page.evaluate('document.fonts.ready')

    click(page, 'section', 'explore')
    wait_render(page)
    click(page, 'explore-tab', 'play')
    wait_render(page)
    swipe(page, -90, selector='.explore-scroll')
    assert page.locator('.explore-tabs button.on').inner_text() == '好看'
    screenshot(page, 'explore-swipe-light.png')

    click(page, 'section', 'news')
    wait_render(page)
    click(page, 'tab', 'review')
    wait_render(page)
    choose_category(page, '全部')
    page.locator('.calendar-btn').click()
    page.locator('[role="dialog"]').wait_for()
    wait_render(page)
    screenshot(page, 'calendar-open-light.png')

    day = page.evaluate("() => { const keys = Object.keys(HOT_SNAPSHOTS).sort(); return keys.includes('2026-10-22') ? '2026-10-22' : keys[keys.length - 2]; }")
    page.locator(f'.date-picker [data-day="{day}"]').click()
    page.locator('[role="dialog"]').wait_for(state='detached')
    wait_render(page)
    assert page.locator('.day-title').count() == 1
    screenshot(page, 'day-hot-light.png')
    click(page, 'day-tab', 'review')
    wait_render(page)
    screenshot(page, 'day-review-light.png')
    click(page, 'day-today')
    wait_render(page)


def assert_logo(page, selector):
    logo = page.locator(selector)
    assert logo.count() == 1, selector
    info = logo.evaluate('''async (e) => {
      let decoded = false;
      try { await e.decode(); decoded = true; } catch (err) {}
      return { attr: e.getAttribute('src'), abs: e.src, complete: e.complete, width: e.naturalWidth, decoded };
    }''')
    assert info['attr'] == 'logo/d-tab.svg', (selector, info)
    assert info['abs'].startswith('file:'), (selector, info)
    assert info['complete'] and info['decoded'], (selector, info)


def assert_no_explore_src(page):
    for path in sorted(ROOT.glob('*.js')) + sorted(ROOT.glob('*.css')) + [ROOT / 'index.html']:
        text = path.read_text(encoding='utf-8')
        assert 'explore-src' not in text, path.name
    loaded = page.evaluate('''() => [
      ...performance.getEntriesByType('resource').map(entry => entry.name),
      ...[...document.images].map(image => image.src),
      ...[...document.querySelectorAll('[src], [href]')].map(el => el.getAttribute('src') || el.getAttribute('href') || ''),
    ].filter(Boolean)''')
    assert loaded, 'no loaded resources observed'
    offenders = [url for url in loaded if 'explore-src' in url]
    assert not offenders, offenders


def assert_touch_targets(page, selectors):
    for selector in selectors:
        boxes = page.locator(selector).evaluate_all('''(els) => els.map(e => {
          const r = e.getBoundingClientRect();
          return { w: r.width, h: r.height };
        })''')
        assert boxes, selector
        assert all(b['w'] >= 44 and b['h'] >= 44 for b in boxes), (selector, boxes)


def assert_nav_clearance(page):
    labels = page.evaluate('''() => {
      const indicator = document.querySelector('.home-indicator').getBoundingClientRect();
      return {
        indicator: { top: indicator.top, bottom: indicator.bottom, left: indicator.left, right: indicator.right },
        navPaddingBottom: parseFloat(getComputedStyle(document.querySelector('.bottom-nav')).paddingBottom),
        labels: [...document.querySelectorAll('.bottom-nav button > span:last-child')].map(el => {
          const r = el.getBoundingClientRect();
          return { text: el.textContent.trim(), top: r.top, bottom: r.bottom, left: r.left, right: r.right };
        }),
      };
    }''')
    assert labels['labels'] and len(labels['labels']) == 3, labels
    assert labels['navPaddingBottom'] >= 24, labels
    indicator = labels['indicator']
    for label in labels['labels']:
        intersects = (label['left'] < indicator['right'] and label['right'] > indicator['left']
                      and label['top'] < indicator['bottom'] and label['bottom'] > indicator['top'])
        assert not intersects, (label, indicator)
        assert label['bottom'] <= indicator['top'], (label, indicator)


def load_feed_images(page):
    scroll_feed(page)


def screenshot(page, name):
    page.wait_for_timeout(180)
    page.screenshot(path=str(ROOT / 'shots' / name))
    print(f'shots/{name}: 1206×2622')


def validate(page):
    stats = data_stats(page)
    explore = explore_stats(page)
    expected = CATEGORIES

    assert page.evaluate('document.documentElement.dataset.theme') == 'light'
    assert page.locator('.brand h1').inner_text() == '拾光热榜'
    assert page.locator('.feed-tabs button').all_text_contents() == ["实时", "热点", "回顾"]
    assert page.locator('.category-rail > button').all_text_contents() == expected
    assert page.locator('.bottom-nav button').all_text_contents() == ["资讯", "探索", "我的"]
    assert page.locator('.bottom-nav button.on').inner_text() == '资讯'
    assert page.locator('.bottom-nav button svg').count() == 3
    assert page.locator('.subcategory-rail, .channel-rail, .channel-wrap, .channel-row, .group-btn, .channel-tag, [data-action="sub"], [data-action="channel"]').count() == 0
    assert page.locator('.feed-scroll').evaluate('(e) => getComputedStyle(e).touchAction') == 'pan-y'
    assert_no_lucide(page)
    assert_icons(page)
    assert_nav_clearance(page)
    assert_logo(page, '.brand img')
    # At initial load two real images must already be loaded and fully visible.
    assert_initial_view_images(page)

    # Live is newest first and every row carries one real post.
    assert page.locator('.story').count() == stats['total']
    assert page.locator('.story').first.get_attribute('data-event') == stats['newest']['id']
    assert page.locator('.story-title').first.inner_text() == stats['newest']['title']
    assert page.locator('.story-meta').first.inner_text().startswith(stats['newest']['sourceName'])
    assert page.locator('.feed-heading .count').inner_text() == f"{stats['total']} 件事"

    titles = []
    for tab in ("live", "hot", "review"):
        click(page, "tab", tab)
        assert page.locator('[role="dialog"]').count() == 0
        assert page.locator('.overlay').count() == 0
        assert page.locator('.feed-tabs [aria-pressed="true"]').inner_text() == {"live": "实时", "hot": "热点", "review": "回顾"}[tab]
        choose_category(page, "全部")
        if tab == "live":
            assert page.locator('.story').count() == stats['total']
            assert page.locator('.hot-card').count() == 0 and page.locator('.review-day').count() == 0
        elif tab == "hot":
            assert page.locator('.hot-card').count() == stats['total']
            assert page.locator('.hot-top').count() == 3
            assert page.locator('.hot-bar').count() == stats['total']
            assert_hot_badges(page)
            widths = page.locator('.hot-bar').evaluate_all('(els) => els.map(e => parseFloat(e.style.width))')
            assert widths == sorted(widths, reverse=True), widths
            assert_hot_ranking(page)
            assert page.locator('.hot-rank').all_text_contents() == [f'{i:02d}' for i in range(1, stats['total'] + 1)]
            top_size = page.locator('.hot-top .hot-title').first.evaluate('(e) => parseFloat(getComputedStyle(e).fontSize)')
            row_size = page.locator('.hot-card:not(.hot-top) .hot-title').first.evaluate('(e) => parseFloat(getComputedStyle(e).fontSize)')
            assert top_size > row_size, (top_size, row_size)
            assert page.locator('.story').count() == 0 and page.locator('.review-day').count() == 0
        else:
            assert page.locator('.story').count() == 0 and page.locator('.hot-card').count() == 0
            assert page.locator('.review-day').count() == len(stats['days'])
            assert page.locator('.review-day .review-date h2').all_text_contents() == [day['date'] for day in stats['days']]
            days = page.locator('.review-day').evaluate_all('''(els) => els.map(e => ({
              day: e.dataset.day,
              ids: [...e.querySelectorAll('.review-item')].map(x => x.dataset.value),
              rows: e.querySelectorAll('.review-item').length,
              label: e.querySelector('.review-date small').textContent,
            }))''')
            for day, source in zip(days, stats['days']):
                assert day['day'] == source['key'], (day, source)
                assert day['ids'] == source['ids'], (day, source)
                assert day['rows'] == len(source['ids']), (day, source)
                assert day['label'] == f"{len(source['ids'])} 件事", day
            assert sum(day['rows'] for day in days) == stats['renderedDays']
            assert page.locator('.review-item').count() == stats['renderedDays']
            header = page.locator('.feed-heading .count').inner_text()
            assert header == f"{len(stats['days'])} 天 · {stats['renderedDays']} 件事", header
            for section in page.locator('.review-day').all():
                times = section.locator('.review-time').all_text_contents()
                assert times == sorted(times, reverse=True), (tab, times)
        titles.append(page.locator(FIRST_TITLE[tab]).first.inner_text())

        for category in expected:
            choose_category(page, category)
            numbers = category_stats(page, category)
            assert numbers['live'] > 0
            if tab == "live":
                assert page.locator('.story').count() == numbers['live']
            elif tab == "hot":
                assert page.locator('.hot-card').count() == numbers['live']
                assert page.locator('.hot-top').count() == min(3, numbers['live'])
                assert page.locator('.hot-bar').count() == numbers['live']
                assert_hot_badges(page)
                assert_hot_ranking(page)
            else:
                assert page.locator('.review-day').count() == len(numbers['days'])
                assert page.locator('.review-item').count() == numbers['review']
                rendered_days = page.locator('.review-day').evaluate_all('''(els) => els.map(e => ({
                  day: e.dataset.day,
                  ids: [...e.querySelectorAll('.review-item')].map(x => x.dataset.value),
                }))''')
                assert [d['day'] for d in rendered_days] == [d['key'] for d in numbers['days']], (tab, category, rendered_days)
                assert [d['ids'] for d in rendered_days] == [d['ids'] for d in numbers['days']], (tab, category, rendered_days)
                header = page.locator('.feed-heading .count').inner_text()
                assert header == f"{len(numbers['days'])} 天 · {numbers['review']} 件事", header
            if category != "全部":
                assert page.locator(ITEMS[tab]).evaluate_all('(els) => els.every(e => e.dataset.category === "' + category + '")')
        choose_category(page, "全部")
    title_by_tab = dict(zip(("live", "hot", "review"), titles))
    assert title_by_tab['live'] == stats['newest']['title'], title_by_tab
    assert title_by_tab['review'] == stats['days'][0]['firstTitle'], title_by_tab
    hottest_title = page.evaluate('''() => EVENTS.reduce((a, b) =>
      b.heat > a.heat || (b.heat === a.heat && b.stamp > a.stamp) ? b : a).title''')
    assert title_by_tab['hot'] == hottest_title, (title_by_tab, hottest_title)

    # Real local images, lazy loading and the compact no-image layout.
    click(page, "tab", "live")
    choose_category(page, "全部")
    assert_feed_images(page)
    assert_category_feed_images(page)

    # Bottom navigation switches the whole app.
    click(page, "section", "explore")
    wait_render(page)
    assert page.locator('.brand h1').inner_text() == '探索'
    assert page.locator('.bottom-nav button.on').inner_text() == '探索'
    assert page.locator('.explore-tabs').is_visible()
    assert page.locator('.filters, .category-rail[aria-label="一级分类"]').count() == 0
    assert page.locator('.bottom-nav button svg').count() == 3
    assert_icon_viewboxes(page)
    assert_typography(page)
    assert_explore(page, explore)
    assert_no_explore_src(page)

    click(page, "section", "mine")
    wait_render(page)
    assert page.locator('.brand h1').inner_text() == '我的'
    assert page.locator('.bottom-nav button.on').inner_text() == '我的'
    assert page.locator('.mine-scroll').is_visible()
    assert page.locator('.feed-tabs, .category-rail, .explore-tabs').count() == 0
    assert_logo(page, '.mine-profile img')
    numbers = page.locator('.mine-number').all_text_contents()
    assert numbers == [str(stats['total']), str(len(stats['days'])), str(stats['channels'])], numbers
    assert_typography(page)
    assert_touch_targets(page, ['.mine-row', '.bottom-nav button'])
    assert_icon_viewboxes(page)

    # The mine switch and the header button share one theme state.
    switch = page.locator('[role="switch"][data-action="theme"]')
    assert switch.get_attribute('aria-checked') == 'false'
    switch.click()
    wait_render(page)
    assert page.locator('html').get_attribute('data-theme') == 'dark'
    assert switch.get_attribute('aria-checked') == 'true'
    assert 'on' in switch.locator('.theme-switch').get_attribute('class')
    assert page.locator('.brand [data-action="theme"]').get_attribute('aria-label') == '切换到浅色模式'
    page.locator('.brand [data-action="theme"]').click()
    wait_render(page)
    assert page.locator('html').get_attribute('data-theme') == 'light'
    assert switch.get_attribute('aria-checked') == 'false'

    click(page, "section", "news")
    wait_render(page)
    assert page.locator('.brand h1').inner_text() == '拾光热榜'
    assert page.locator('.bottom-nav button.on').inner_text() == '资讯'

    # Theme control stays icon-only in the header.
    header_theme = page.locator('.brand [data-action="theme"]')
    header_theme.click()
    assert page.locator('html').get_attribute('data-theme') == 'dark'
    assert header_theme.inner_text() == ''
    assert header_theme.locator('svg').count() == 1
    header_theme.click()
    assert page.locator('html').get_attribute('data-theme') == 'light'

    # Real detail copy and the local source route.
    click(page, "tab", "live")
    choose_category(page, "全部")
    newest = stats['newest']
    click(page, "event", newest['id'])
    page.locator('[role="dialog"]').wait_for()
    assert page.locator('.sheet-body .detail-copy').text_content().strip() == newest['summary']
    assert page.locator('.source-card').count() == 1
    assert f"@{newest['sourceId']}" in page.locator('.sheet-body').inner_text()
    assert '1 个频道在说' not in page.locator('.sheet-body').inner_text()
    page.locator(f'.source-link[href="#source/{newest["id"]}"]').click()
    page.get_by_role('heading', name="频道原文", exact=True).wait_for()
    assert page.locator('.sheet-body .detail-copy').text_content().strip() == newest['summary']
    assert f"@{newest['sourceId']}" in page.locator('.sheet-body').inner_text()
    page.locator('.sheet-header a[aria-label="返回事件"]').click()
    page.get_by_role('heading', name="事件详情", exact=True).wait_for()
    close_dialog(page)

    image_event = page.evaluate('''() => {
      const event = EVENTS.find(e => e.image);
      return { id: event.id, image: event.image };
    }''')
    click(page, "event", image_event['id'])
    page.locator('[role="dialog"]').wait_for()
    assert page.locator('.detail-image').get_attribute('src') == image_event['image']
    page.wait_for_function('''() => {
      const image = document.querySelector('.detail-image');
      return image && image.complete && image.naturalWidth > 0;
    }''', timeout=3000)
    close_dialog(page)

    # Preview empty and error states recover from the design sheet.
    open_about(page)
    assert_typography(page)
    assert_red_tint_contrast(page)
    close_dialog(page)
    open_about(page)
    click(page, "status", "empty")
    page.get_by_text('暂无相关内容', exact=True).wait_for()
    click(page, "clear")
    assert page.locator('.story').count() == stats['total']
    open_about(page)
    click(page, "status", "error")
    page.get_by_text('加载失败', exact=True).wait_for()
    click(page, "retry")
    assert page.locator('.story').count() == stats['total']

    # Modal keyboard containment and return to the original feed position.
    page.locator('.feed-scroll').evaluate('(e) => e.scrollTop = 230')
    saved_scroll = page.locator('.feed-scroll').evaluate('(e) => e.scrollTop')
    open_about(page)
    page.keyboard.press('Tab')
    assert page.evaluate('Boolean(document.activeElement.closest("[role=dialog]"))')
    page.keyboard.press('Escape')
    page.locator('[role="dialog"]').wait_for(state="detached")
    assert page.locator('[role="dialog"]').count() == 0
    assert abs(page.locator('.feed-scroll').evaluate('(e) => e.scrollTop') - saved_scroll) < 2
    page.locator('.feed-scroll').evaluate('(e) => e.scrollTop = 0')

    # Horizontal swipes switch categories in order, stop at both ends and center the new pill.
    click(page, "tab", "live")
    choose_category(page, "全部")
    page.evaluate('''() => {
      window.__centered = [];
      const original = Element.prototype.scrollIntoView;
      Element.prototype.scrollIntoView = function (options) {
        window.__centered.push({
          text: this.textContent.trim(),
          action: this.dataset ? this.dataset.action || null : null,
          value: this.dataset ? this.dataset.value || null : null,
          options: options || null,
        });
        return original.call(this, options);
      };
    }''')
    for expected_category in expected[1:]:
        swipe(page, -90)
        assert active_category(page) == expected_category
        assert_centered(page, expected_category)
        assert page.locator('.story').evaluate_all('(els) => els.every(e => e.dataset.category === "' + expected_category + '")')
    swipe(page, -90)
    assert active_category(page) == "科技"
    assert_centered(page, "科技")
    for expected_category in reversed(expected[:-1]):
        swipe(page, 90)
        assert active_category(page) == expected_category
        assert_centered(page, expected_category)
    swipe(page, 90)
    assert active_category(page) == "全部"
    assert_centered(page, "全部")
    assert page.locator('.story').count() == stats['total']
    centered = page.evaluate('window.__centered.length')
    swipe(page, -40)
    assert active_category(page) == "全部"
    assert page.evaluate('window.__centered.length') == centered

    # Pull-to-refresh: downward vertical drag at scrollTop 0 refreshes; nothing else does.
    for tab in ("live", "hot", "review"):
        click(page, "tab", tab)
        choose_category(page, "全部")
        feed = page.locator('.feed-scroll')
        feed.evaluate('(e) => e.scrollTop = 0')
        before = active_category(page)
        centered = page.evaluate('window.__centered.length')
        swipe(page, 0, 120)
        indicator = page.locator('.ptr-indicator.ptr-refreshing')
        assert indicator.count() == 1, tab
        assert indicator.is_visible(), tab
        assert active_category(page) == before, tab
        assert page.evaluate('window.__centered.length') == centered, tab
        page.locator('.ptr-indicator').wait_for(state='detached', timeout=2000)
        assert page.locator('.ptr-indicator').count() == 0, tab
        assert page.locator(FIRST_TITLE[tab]).count() > 0, tab
        centered = page.evaluate('window.__centered.length')
        swipe(page, 0, 10)
        assert page.locator('.ptr-indicator').count() == 0, tab
        assert active_category(page) == before, tab
        assert page.evaluate('window.__centered.length') == centered, tab
        assert page.locator(FIRST_TITLE[tab]).count() > 0, tab

    click(page, "tab", "live")
    choose_category(page, "全部")
    feed = page.locator('.feed-scroll')
    feed.evaluate('(e) => e.scrollTop = 180')
    assert feed.evaluate('(e) => e.scrollTop') > 0
    before = active_category(page)
    swipe(page, 0, 120)
    assert page.locator('.ptr-indicator').count() == 0
    assert active_category(page) == before
    assert feed.evaluate('(e) => e.scrollTop') > 0
    feed.evaluate('(e) => e.scrollTop = 0')

    centered = page.evaluate('window.__centered.length')
    swipe(page, -90)
    assert page.locator('.ptr-indicator').count() == 0
    assert active_category(page) == "新闻"
    assert page.evaluate('window.__centered.length') == centered + 1
    swipe(page, 90)
    assert page.locator('.ptr-indicator').count() == 0
    assert active_category(page) == "全部"

    feed.evaluate('(e) => e.scrollTop = 180')
    centered = page.evaluate('window.__centered.length')
    swipe(page, -80, dy=120)
    assert active_category(page) == "全部"
    assert page.evaluate('window.__centered.length') == centered
    assert page.locator('[role="dialog"]').count() == 0
    assert page.locator('.overlay').count() == 0
    feed.evaluate('(e) => e.scrollTop = 0')

    # Hot and review share the category row and respond to the same swipe.
    for tab, selector in (("hot", ".hot-card"), ("review", ".review-item")):
        click(page, "tab", tab)
        choose_category(page, "全部")
        swipe(page, -90)
        assert active_category(page) == "新闻"
        assert_centered(page, "新闻")
        assert page.locator(selector).count() > 0
        assert page.locator(selector).evaluate_all('(els) => els.every(e => e.dataset.category === "新闻")')
        swipe(page, 90)
        assert active_category(page) == "全部"
        assert_centered(page, "全部")
    click(page, "tab", "live")
    choose_category(page, "全部")

    # Explore and mine also support pull-to-refresh.
    click(page, "section", "explore")
    wait_render(page)
    click(page, "explore-tab", "play")
    wait_render(page)
    page.locator('.explore-scroll').evaluate('(e) => e.scrollTop = 0')
    swipe(page, 0, 120, '.explore-scroll')
    indicator = page.locator('.ptr-indicator.ptr-refreshing')
    assert indicator.count() == 1
    assert indicator.is_visible()
    page.locator('.ptr-indicator').wait_for(state='detached', timeout=2000)
    assert page.locator('.explore-item').count() == explore['play']['count']

    click(page, "section", "mine")
    wait_render(page)
    page.locator('.mine-scroll').evaluate('(e) => e.scrollTop = 0')
    swipe(page, 0, 120, '.mine-scroll')
    indicator = page.locator('.ptr-indicator.ptr-refreshing')
    assert indicator.count() == 1
    assert indicator.is_visible()
    page.locator('.ptr-indicator').wait_for(state='detached', timeout=2000)
    assert page.locator('.mine-group').count() >= 3

    click(page, "section", "news")
    wait_render(page)
    click(page, "tab", "live")
    choose_category(page, "全部")

    # Touch targets and typography across the three sections.
    assert_touch_targets(page, ['.feed-tabs button', '.category-rail > button', '.bottom-nav button'])
    for section in ("news", "explore", "mine"):
        click(page, "section", section)
        wait_render(page)
        assert_typography(page)
        assert_icon_viewboxes(page)
        assert_nav_clearance(page)
    click(page, "section", "explore")
    wait_render(page)
    assert_touch_targets(page, ['.explore-tabs button', '.explore-chips button', '.bottom-nav button'])
    assert_tab_underline(page, '.explore-tabs button.on')

    click(page, "section", "news")
    wait_render(page)
    click(page, "tab", "live")
    choose_category(page, "全部")

    assert_group_filters(page)
    assert_explore_swipe(page, explore)
    assert_day_view(page, stats)

    click(page, "section", "news")
    wait_render(page)
    click(page, "tab", "live")
    choose_category(page, "全部")
    print('B5: interactions passed')


def main():
    (ROOT / 'shots').mkdir(exist_ok=True)
    errors = []
    external = []
    # Chromium's Unix socket path must fit within 108 bytes; keep this prefix short.
    with tempfile.TemporaryDirectory(prefix='.p-', dir=ROOT) as runtime:
        os.environ['TMPDIR'] = runtime
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=CHROMIUM, headless=True,
                args=['--no-sandbox', '--disable-background-networking'],
                env={**os.environ, 'TMPDIR': runtime},
            )
            context = browser.new_context(viewport={'width': 402, 'height': 874},
                                          device_scale_factor=3, is_mobile=True,
                                          has_touch=True, locale='zh-CN', offline=True)

            def block_network(route):
                external.append(route.request.url)
                route.abort()

            context.route('http://**/*', block_network)
            context.route('https://**/*', block_network)
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)

            page.goto(f'{(ROOT / "index.html").as_uri()}?t=light')
            validate(page)
            capture_b4_shots(page)

            group_dots = {}
            group_targets = {}
            for theme in ('light', 'dark'):
                page.goto(f'{(ROOT / "index.html").as_uri()}?t={theme}')
                page.locator('.story').first.wait_for()
                page.evaluate('document.fonts.ready')
                assert page.locator('html').get_attribute('data-theme') == theme
                assert page.locator('.brand [data-action="theme"]').get_attribute('aria-label') == ('切换到深色模式' if theme == 'light' else '切换到浅色模式')
                assert_tab_underline(page)
                expected_tint = [215, 40, 47, 0.05] if theme == 'light' else [240, 90, 95, 0.12]
                assert tint_parts(page) == expected_tint, tint_parts(page)
                assert page.evaluate('document.documentElement.scrollWidth === innerWidth')
                assert page.locator('.phone').bounding_box()['height'] == 874
                assert_chip_style_parity(page)

                load_feed_images(page)
                screenshot(page, f'realtime-{theme}.png')

                # Reset the preview seed so both themes' group shots share one read state.
                page.evaluate("localStorage.removeItem('rebang.lastSeen')")
                page.reload()
                page.locator('.story').first.wait_for()
                page.evaluate('document.fonts.ready')
                assert page.locator('html').get_attribute('data-theme') == theme

                choose_category(page, '新闻')
                group = page.locator('.group-btn')
                assert group.count() == 1
                snapshot = channel_snapshot(page)
                news_channels = [channel for channel in snapshot['channels'] if channel['category'] == '新闻']
                unread_total = sum(snapshot['counts'][channel['id']] for channel in news_channels)
                assert unread_total > 0, snapshot['counts']
                assert group.get_attribute('aria-label') == f'选择群组，{unread_total} 条未读'
                assert group.get_attribute('aria-expanded') == 'false'
                dot = page.locator('.group-dot')
                assert dot.count() == 1
                assert int(dot.inner_text()) == unread_total
                group_dots[theme] = dot.inner_text().strip()
                assert_group_dot_layout(page)
                assert_filter_row_layout(page)
                screenshot(page, f'group-category-{theme}.png')

                group.click()
                page.locator('[role="dialog"]').wait_for()
                wait_render(page)
                assert group.get_attribute('aria-expanded') == 'true'
                assert page.locator('.group-sheet').count() == 1
                assert page.locator('#dialog-title').inner_text() == '新闻 · 群组'
                assert page.locator('.group-sheet .group-option').count() == len(news_channels)
                assert page.locator('.group-sheet .unread-badge').count() >= 1
                screenshot(page, f'group-sheet-{theme}.png')

                target = next(channel for channel in news_channels if snapshot['counts'][channel['id']] > 0)
                group_targets[theme] = target['id']
                page.locator(f'.group-sheet .group-option[data-ch="{target["id"]}"]').click()
                page.locator('[role="dialog"]').wait_for(state='detached')
                wait_render(page)
                tag = page.locator('.channel-tag')
                assert tag.count() == 1
                assert target['name'] in tag.inner_text()
                assert group.get_attribute('aria-expanded') == 'false'
                assert page.locator('.feed-scroll').evaluate('(e) => e.scrollTop') == 0
                assert_touch_targets(page, ['.channel-tag-clear'])
                assert_filter_row_layout(page)
                assert page.locator('.story').count() > 0
                assert page.locator('.story').evaluate_all(
                    '(els, ch) => els.every(e => e.dataset.ch === ch)', target['id'])
                assert_selected_category_visible(page)
                screenshot(page, f'group-filtered-{theme}.png')
                assert_rail_right_fade(page)

                page.locator('.channel-tag-clear').click()
                wait_render(page)
                assert page.locator('.channel-tag').count() == 0
                assert page.locator('.feed-scroll').evaluate('(e) => e.scrollTop') == 0
                assert page.evaluate('document.activeElement && document.activeElement.classList.contains("group-btn")')
                choose_category(page, '全部')

                click(page, 'tab', 'hot')
                wait_render(page)
                assert page.locator('.hot-top').count() == 3
                assert_hot_ranking(page)
                screenshot(page, f'hot-{theme}.png')

                click(page, 'tab', 'review')
                wait_render(page)
                assert page.locator('.review-day').count() == page.evaluate('() => new Set(EVENTS.map(e => e.dateKey)).size')
                screenshot(page, f'review-{theme}.png')

                click(page, 'section', 'explore')
                wait_render(page)
                assert page.locator('.explore-tabs button.on').inner_text() == '好玩'
                screenshot(page, f'explore-play-{theme}.png')

                click(page, 'explore-tab', 'kan')
                wait_render(page)
                assert page.locator('.explore-tabs button.on').inner_text() == '好看'
                screenshot(page, f'explore-kan-{theme}.png')

                click(page, 'explore-tab', 'buy')
                wait_render(page)
                assert page.locator('.explore-tabs button.on').inner_text() == '好买'
                screenshot(page, f'explore-buy-{theme}.png')

                click(page, 'section', 'mine')
                wait_render(page)
                screenshot(page, f'mine-{theme}.png')

            assert group_dots['light'] == group_dots['dark'], group_dots
            assert group_targets['light'] == group_targets['dark'], group_targets

            # Mobile edge widths and centered desktop frame.
            click(page, 'section', 'news')
            page.set_viewport_size({'width': 320, 'height': 740})
            assert page.evaluate('document.documentElement.scrollWidth === innerWidth')
            page.set_viewport_size({'width': 1280, 'height': 1000})
            frame = page.locator('.phone').bounding_box()
            assert frame['width'] == 402 and frame['height'] == 874
            assert abs(frame['x'] + 201 - 640) < 1
            assert not external, f'Unexpected network requests: {external}'
            assert not errors, f'Browser errors: {errors}'
            browser.close()
    print(json.dumps({'screenshots': 24, 'browser_errors': len(errors), 'external_requests': len(external), 'checks': 'passed'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
