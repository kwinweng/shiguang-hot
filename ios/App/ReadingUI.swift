import AVKit
import SwiftUI
import UIKit

extension ReadingRoute: Hashable {
    nonisolated static func == (lhs: ReadingRoute, rhs: ReadingRoute) -> Bool { lhs.id == rhs.id }
    nonisolated func hash(into hasher: inout Hasher) { hasher.combine(id) }
}

@MainActor
enum HotStyle {
    static let red = Color(uiColor: UIColor { trait in
        trait.userInterfaceStyle == .dark ? UIColor(red: 1, green: 0.40, blue: 0.40, alpha: 1) : UIColor(red: 0.76, green: 0.08, blue: 0.09, alpha: 1)
    })

    private static let zone = TimeZone(identifier: "Asia/Shanghai")!
    private static let day = Date.ISO8601FormatStyle(timeZone: zone).year().month().day().dateSeparator(.dash)
    private static let clock = Date.FormatStyle(date: .omitted, time: .shortened, locale: Locale(identifier: "zh_CN"), timeZone: zone)
    private static let shortDate = Date.FormatStyle(date: .abbreviated, time: .shortened, locale: Locale(identifier: "zh_CN"), timeZone: zone)

    static func beijingDay() -> String { day.format(.now) }

    static func timestamp(_ value: String) -> String {
        let fractional = Date.ISO8601FormatStyle(includingFractionalSeconds: true)
        guard let date = (try? Date.ISO8601FormatStyle().parse(value)) ?? (try? fractional.parse(value)) else { return "" }
        return day.format(date) == beijingDay() ? clock.format(date) : shortDate.format(date)
    }
}

struct FeedRow: View {
    let item: FeedItem
    @Environment(\.dynamicTypeSize) private var size

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            let layout = size.isAccessibilitySize ? AnyLayout(VStackLayout(alignment: .leading, spacing: 8)) : AnyLayout(HStackLayout(alignment: .top, spacing: 12))
            layout {
                VStack(alignment: .leading, spacing: 5) {
                    HStack(spacing: 6) {
                        Text(item.blogger?.displayName ?? item.sourceName)
                        Text(HotStyle.timestamp(item.publishedAt)).monospacedDigit()
                        if item.highlight == true { Text("今日重点").foregroundStyle(HotStyle.red) }
                    }
                    .font(.caption).foregroundStyle(.secondary)
                    Text(item.displayTitle).font(.headline).foregroundStyle(.primary)
                    if let summary = item.displaySummary.nonblank, summary != item.displayTitle {
                        Text(summary).font(.subheadline).foregroundStyle(.secondary).lineLimit(3)
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
                if let url = FeedAPI.mediaURL(item.image?.url ?? item.blogger?.media?.first?.previewUrl) {
                    RemotePicture(url: url, fill: true)
                        .frame(width: size.isAccessibilitySize ? 132 : 87, height: size.isAccessibilitySize ? 93 : 66)
                        .clipShape(.rect(cornerRadius: 7)).accessibilityHidden(true)
                }
            }.padding(.vertical, 13)
            Divider()
        }.padding(.horizontal, 16).contentShape(.rect)
        .accessibilityElement(children: .combine)
    }
}

struct BannerRow: View {
    let item: FeedItem
    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            if let url = FeedAPI.mediaURL(item.image?.url) {
                RemotePicture(url: url, fill: true).frame(width: 248, height: 112).clipped()
                    .clipShape(.rect(cornerRadius: 8)).accessibilityHidden(true)
            }
            Text(item.displayTitle).font(.subheadline.weight(.semibold)).lineLimit(2)
        }
        .frame(width: 248, alignment: .leading).padding(.bottom, 9)
    }
}

struct RemotePicture: View {
    let url: URL
    var fill = false
    var body: some View {
        GeometryReader { geometry in
            AsyncImage(url: url) { phase in
                if let image = phase.image {
                    image.resizable().aspectRatio(contentMode: fill ? .fill : .fit)
                        .frame(width: geometry.size.width, height: geometry.size.height).clipped()
                } else {
                    Rectangle().fill(.quaternary).overlay {
                        if phase.error != nil { Image(systemName: "photo").foregroundStyle(.secondary) }
                    }
                }
            }
        }
    }
}

private struct ItemActions: ViewModifier {
    let item: FeedItem
    let favorites: FavoritesStore
    func body(content: Content) -> some View {
        content.contextMenu {
            Button(favorites.contains(item) ? "取消收藏" : "收藏", systemImage: "bookmark") { favorites.toggle(item) }
            ShareLink(item: item.shareURL)
            Button("复制链接", systemImage: "link") { UIPasteboard.general.url = item.shareURL }
            if let original = item.originalURL { Link(destination: original) { Label("打开原文", systemImage: "arrow.up.right") } }
        }
        .accessibilityAction(named: favorites.contains(item) ? "取消收藏" : "收藏") { favorites.toggle(item) }
    }
}

extension View {
    func itemActions(_ item: FeedItem, favorites: FavoritesStore) -> some View {
        modifier(ItemActions(item: item, favorites: favorites))
    }
}

struct DetailScreen: View {
    let route: ReadingRoute
    let favorites: FavoritesStore
    @State private var original = false
    @State private var showComments = false
    @State private var gallery: GallerySelection?

    private var item: FeedItem { route.item }
    private var comments: [FeedItem.Comment] { item.tg?.comments ?? item.blogger?.comments ?? [] }
    private var quote: FeedItem.Quote? { item.quote ?? item.blogger?.quote }
    private var translated: Bool { !original && item.translation != nil }
    private var blocks: [FeedItem.Block]? { translated ? item.translation?.blocks : item.blocks }
    private var media: [GalleryAsset] {
        var urls = Set<URL>()
        var assets = (item.blogger?.media ?? []).compactMap { entry -> GalleryAsset? in
            guard let url = FeedAPI.mediaURL(entry.url), urls.insert(url).inserted else { return nil }
            return GalleryAsset(url: url, preview: FeedAPI.mediaURL(entry.previewUrl), kind: entry.type)
        }
        if let url = FeedAPI.mediaURL(item.image?.url), urls.insert(url).inserted { assets.insert(.init(url: url, preview: nil, kind: "image"), at: 0) }
        return assets
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 17) {
                Text(original ? item.title.nonblank ?? item.displayTitle : item.displayTitle)
                    .font(.largeTitle.bold()).accessibilityAddTraits(.isHeader)
                    .accessibilityIdentifier("reading-title")
                HStack {
                    Text(item.blogger?.displayName ?? item.sourceName)
                    Text(HotStyle.timestamp(item.publishedAt)).monospacedDigit()
                }.font(.subheadline).foregroundStyle(.secondary)
                if item.translation != nil {
                    HStack {
                        if translated { Label("机器翻译", systemImage: "character.bubble").font(.caption).foregroundStyle(.secondary) }
                        Spacer()
                        Button(translated ? "查看原文文字" : "查看译文") { original.toggle() }.font(.subheadline)
                    }
                }
                if !media.isEmpty { mediaStrip }
                if let blocks, !blocks.isEmpty {
                    ForEach(Array(blocks.enumerated()), id: \.offset) { _, block in blockView(block) }
                } else if let bodyText = displayedBody.nonblank {
                    Text(bodyText).lineSpacing(6).textSelection(.enabled)
                }
                if translated && item.translation?.bodyPending == true {
                    Text("全文仍在翻译").font(.footnote).foregroundStyle(.secondary)
                }
                if let quote { quoteCard(quote) }
                if let tg = item.tg {
                    ViewThatFits(in: .horizontal) {
                        HStack(spacing: 8) { telegramMetrics(tg) }.fixedSize(horizontal: true, vertical: false)
                        ScrollView(.horizontal) { HStack(spacing: 8) { telegramMetrics(tg) } }.scrollIndicators(.hidden)
                    }.font(.footnote).foregroundStyle(.secondary)
                }
                if let counts = item.blogger?.metrics {
                    ScrollView(.horizontal) {
                        HStack(spacing: 9) {
                            ForEach([("reply", "回复"), ("repost", "转发"), ("like", "喜欢"), ("view", "浏览")], id: \.0) { key, title in
                                if let n = counts[key] { Text("\(title) \(n)") }
                            }
                        }.font(.footnote).foregroundStyle(.secondary)
                    }.scrollIndicators(.hidden)
                }
                if !comments.isEmpty {
                    Button(item.tg == nil ? "热门回复" : "评论楼", systemImage: "bubble.left.and.bubble.right") { showComments = true }
                }
                if let url = item.originalURL { Link(destination: url) { Label("打开原文", systemImage: "arrow.up.right") } }
            }.padding(16)
        }
        .id(item.id)
        .gesture(HorizontalStepPan(reservesBackEdge: true, action: step))
        .background { EdgeBackOnly().frame(width: 0, height: 0).allowsHitTesting(false) }
        .accessibilityIdentifier("reading-detail")
        .toolbarVisibility(.hidden, for: .tabBar)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItemGroup(placement: .topBarTrailing) {
                Button(favorites.contains(item) ? "取消收藏" : "收藏", systemImage: favorites.contains(item) ? "bookmark.fill" : "bookmark") { favorites.toggle(item) }
                ShareLink(item: item.shareURL)
            }
        }
        .safeAreaInset(edge: .bottom) {
            HStack {
                Button("上一条", systemImage: "chevron.left") { step(-1) }.disabled(route.index == 0)
                Spacer()
                Button("下一条", systemImage: "chevron.right") { step(1) }.disabled(route.index + 1 >= route.items.count)
            }.font(.subheadline).padding(.horizontal, 16).frame(minHeight: 48).background(.bar)
        }
        .sheet(isPresented: $showComments) {
            NavigationStack {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 15) {
                        ForEach(Array(comments.enumerated()), id: \.offset) { _, comment in
                            VStack(alignment: .leading, spacing: 6) {
                                Text(comment.displayName ?? comment.handle ?? "").font(.subheadline.bold())
                                if let reply = comment.replyText?.nonblank {
                                    Text(reply).font(.subheadline).foregroundStyle(.secondary).padding(8).background(.quaternary, in: .rect(cornerRadius: 6))
                                }
                                Text(comment.textZh?.nonblank ?? comment.text)
                                if let likes = comment.like { Label("\(likes)", systemImage: "heart").font(.footnote).foregroundStyle(.secondary) }
                            }.frame(maxWidth: .infinity, alignment: .leading)
                            Divider()
                        }
                    }.padding(16)
                }
                .navigationTitle(item.tg == nil ? "热门回复" : "评论楼")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("完成") { showComments = false } } }
            }.presentationDetents([.medium, .large])
        }
        .fullScreenCover(item: $gallery) { selection in GalleryView(selection: selection, original: item.originalURL) }
    }

    private var displayedBody: String {
        if translated, let translation = item.translation { return translation.body?.nonblank ?? translation.summary?.nonblank ?? item.summary }
        return item.body?.nonblank ?? item.summary
    }

    private var mediaStrip: some View {
        ScrollView(.horizontal) {
            HStack(spacing: 8) {
                ForEach(Array(media.enumerated()), id: \.element.id) { index, asset in
                    Button {
                        gallery = GallerySelection(assets: media, index: index)
                    } label: {
                        ZStack {
                            if let image = asset.preview ?? (asset.kind == "image" ? asset.url : nil) {
                                RemotePicture(url: image, fill: true)
                            } else { RoundedRectangle(cornerRadius: 8).fill(.quaternary) }
                            if asset.kind != "image" { Image(systemName: "play.circle.fill").font(.title).foregroundStyle(.white).shadow(radius: 4) }
                        }.frame(width: media.count == 1 ? 256 : 172, height: 120).clipShape(.rect(cornerRadius: 8))
                    }.buttonStyle(.plain).accessibilityLabel(asset.kind == "image" ? "查看图片 \(index + 1)" : "播放媒体 \(index + 1)")
                }
            }
        }.scrollIndicators(.hidden)
    }

    @ContentBuilder private func blockView(_ block: FeedItem.Block) -> some View {
        switch block.type {
        case "h": if let text = block.text { Text(text).font(.title3.bold()).accessibilityAddTraits(.isHeader) }
        case "hr": Divider()
        case "pre": if let text = block.text {
            ScrollView(.horizontal) { Text(text).font(.system(.footnote, design: .monospaced)).padding(12) }
                .background(.quaternary, in: .rect(cornerRadius: 6)).textSelection(.enabled)
        }
        case "ul", "ol": if let values = block.items {
            ForEach(Array(values.enumerated()), id: \.offset) { i, text in
                Text("\(block.type == "ol" ? "\(i + 1)." : "•") \(text)")
            }
        }
        case "img":
            if block.missing != true, let url = FeedAPI.mediaURL(block.src) {
                Button {
                    gallery = GallerySelection(assets: [.init(url: url, preview: nil, kind: "image")], index: 0)
                } label: { RemotePicture(url: url).aspectRatio(1.65, contentMode: .fit) }
                .buttonStyle(.plain).accessibilityLabel(block.alt?.nonblank ?? "查看正文图片")
            } else { Text("这张图没存下来").font(.footnote).foregroundStyle(.secondary) }
        case "p", "quote": if let text = block.text { Text(text).lineSpacing(6).textSelection(.enabled) }
        default: EmptyView()
        }
    }

    @ContentBuilder private func telegramMetrics(_ tg: FeedItem.Telegram) -> some View {
        if let views = tg.viewsLabel { Label(views, systemImage: "eye") }
        else if let views = tg.views { Label("\(views)", systemImage: "eye") }
        ForEach(Array((tg.reactions ?? []).enumerated()), id: \.offset) { _, reaction in Text("\(reaction.emoji) \(reaction.count)") }
        if let count = tg.commentsTotal { Label("\(count)", systemImage: "bubble") }
    }

    private func quoteCard(_ quote: FeedItem.Quote) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(quote.displayName ?? quote.sourceName ?? quote.handle ?? "引用").font(.subheadline.bold())
            if let content = (original ? quote.text : quote.textZh?.nonblank ?? quote.text)?.nonblank { Text(content).textSelection(.enabled) }
            if let value = quote.url, let url = FeedAPI.externalURL(value) { Link("打开引用原帖", destination: url).font(.footnote) }
        }.frame(maxWidth: .infinity, alignment: .leading).padding(12).background(.quaternary, in: .rect(cornerRadius: 8))
    }

    private func step(_ delta: Int) {
        let next = route.index + delta
        guard route.items.indices.contains(next) else { return }
        original = false
        route.index = next
    }
}

struct GalleryAsset: Identifiable {
    let url: URL
    let preview: URL?
    let kind: String
    var id: URL { url }
}

struct GallerySelection: Identifiable {
    let id = UUID()
    let assets: [GalleryAsset]
    let index: Int
}

struct GalleryView: View {
    let selection: GallerySelection
    let original: URL?
    @Environment(\.dismiss) private var dismiss
    @State private var index = 0

    var body: some View {
        ZStack(alignment: .topTrailing) {
            Color.black.ignoresSafeArea()
            TabView(selection: $index) {
                ForEach(Array(selection.assets.enumerated()), id: \.element.id) { position, asset in
                    VStack {
                        if asset.kind == "image" {
                            ZoomPicture(url: asset.url)
                        } else if ["video", "gif"].contains(asset.kind), position == index {
                            VideoPlayer(player: AVPlayer(url: asset.url))
                        } else if let original {
                            Link("打开原帖播放", destination: original)
                        }
                    }.tag(position)
                }
            }.tabViewStyle(.page(indexDisplayMode: selection.assets.count > 1 ? .always : .never))
            Button("关闭图集", systemImage: "xmark") { dismiss() }
                .labelStyle(.iconOnly).padding(12).background(.thinMaterial, in: .circle).padding(10)
        }
        .foregroundStyle(.white).preferredColorScheme(.dark)
        .onAppear { index = selection.index }
        .simultaneousGesture(DragGesture(minimumDistance: 36).onEnded {
            if $0.translation.height > 100, $0.translation.height > abs($0.translation.width) * 1.5 { dismiss() }
        })
    }
}

private struct ZoomPicture: View {
    let url: URL
    @GestureState private var pinch = 1.0
    @State private var zoom = 1.0
    var body: some View {
        RemotePicture(url: url)
            .scaleEffect(min(max(zoom * pinch, 1), 4))
            .gesture(MagnifyGesture().updating($pinch) { value, state, _ in state = value.magnification }
                .onEnded { zoom = min(max(zoom * $0.magnification, 1), 4) })
    }
}
