import SwiftUI
import UIKit

struct ChannelScreen: View {
    let store: FeedStore
    let favorites: FavoritesStore
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @AppStorage("horizontalChannelJump") private var horizontal = true
    @State private var position = ScrollPosition(idType: String.self)
    @State private var active = "current"
    @State private var route: ReadingRoute?
    @State private var movingTo: String?
    @State private var lastOffset = 0.0
    @State private var movingDown = true

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if store.channels.isEmpty {
                    if store.startupFailed {
                        ContentUnavailableView {
                            Label("暂时取不到频道", systemImage: "wifi.exclamationmark")
                        } actions: {
                            Button("重试") { Task { await store.refresh(around: nil) } }
                        }
                    } else { ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity) }
                } else {
                    channelsBar
                    if store.updateAvailable || store.startupFailed {
                        Button(store.updateAvailable ? "有新内容，点击刷新" : "未能刷新，重试") {
                            Task { await refresh() }
                        }
                        .font(.footnote.weight(.semibold)).frame(maxWidth: .infinity, minHeight: 44)
                    }
                    feed
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { Text(dateLabel).font(.headline).monospacedDigit() }
                ToolbarItemGroup(placement: .topBarTrailing) {
                    Button("刷新", systemImage: "arrow.clockwise") { Task { await refresh() } }
                        .disabled(store.updating)
                    Menu("频道翻法", systemImage: "ellipsis.circle") {
                        Toggle("左右滑换频道", isOn: $horizontal)
                    }
                }
            }
            .navigationDestination(item: $route) { selection in
                DetailScreen(route: selection, favorites: favorites)
            }
            .task { await store.start() }
        }
    }

    private var channelsBar: some View {
        ScrollViewReader { bar in
            ScrollView(.horizontal) {
                HStack(spacing: 16) {
                    ForEach(store.channels) { channel in
                        Button { jump(to: channel.slug) } label: {
                            Text(channel.name)
                                .font(.subheadline.weight(active == channel.slug ? .bold : .medium))
                                .foregroundStyle(active == channel.slug ? HotStyle.red : .secondary)
                                .padding(.vertical, 12)
                                .overlay(alignment: .bottom) {
                                    if active == channel.slug { Capsule().fill(HotStyle.red).frame(height: 2) }
                                }
                        }
                        .buttonStyle(.plain)
                        .accessibilityAddTraits(active == channel.slug ? .isSelected : [])
                        .accessibilityIdentifier("channel-\(channel.slug)")
                        .id(channel.slug)
                    }
                }.padding(.horizontal, 16)
            }
            .scrollIndicators(.hidden)
            .onChange(of: active) { bar.scrollTo(active, anchor: .center) }
        }
        .background(.background)
        .overlay(alignment: .bottom) { Divider() }
    }

    private var feed: some View {
        ScrollView {
            LazyVStack(spacing: 0, pinnedViews: [.sectionHeaders]) {
                ForEach(store.channels) { channel in
                    Section {
                        segment(channel)
                    } header: {
                        HStack {
                            Text(channel.name).font(.title2.bold()).accessibilityAddTraits(.isHeader)
                            Spacer()
                        }
                        .padding(.horizontal, 16).padding(.vertical, 10)
                        .background(.background)
                        .id("\(channel.slug)|header")
                    }
                }
            }.scrollTargetLayout()
        }
        .scrollPosition($position)
        .onChange(of: position.viewID(type: String.self)) { _, id in
            guard let id, let slug = id.split(separator: "|", maxSplits: 1).first.map(String.init), FeedAPI.channelSlugs.contains(slug) else { return }
            if let movingTo, movingTo != slug { return }
            active = slug
            movingTo = nil
        }
        .onScrollGeometryChange(for: Int.self) { Int($0.contentOffset.y / 8) } action: { _, bucket in
            let offset = Double(bucket)
            movingDown = offset > lastOffset
            lastOffset = offset
        }
        .gesture(HorizontalStepPan { direction in
            if horizontal { advance(direction) }
        })
        .refreshable { await refresh() }
    }

    @ContentBuilder
    private func segment(_ channel: Channel) -> some View {
        let segment = store.segments[channel.slug]
        if !channel.banner.isEmpty {
            ScrollView(.horizontal) {
                LazyHStack(spacing: 10) {
                    ForEach(Array(uniqueItems(channel.banner).prefix(5))) { item in
                        Button { open(item) } label: { BannerRow(item: item) }
                            .buttonStyle(.plain)
                            .itemActions(item, favorites: favorites)
                    }
                }.padding(.horizontal, 16)
            }
            .scrollIndicators(.hidden)
            .id("\(channel.slug)|banner")
        }
        ForEach(segment?.items ?? []) { item in
            Button { open(item) } label: { FeedRow(item: item) }
                .buttonStyle(.plain)
                .itemActions(item, favorites: favorites)
                .accessibilityIdentifier("item-\(item.id)")
                .id("\(channel.slug)|\(item.id)")
        }
        if segment?.more != false {
            Group {
                if segment?.loading == true {
                    ProgressView()
                } else {
                    Button(segment?.failed == true ? "再试一次" : "继续加载") {
                        Task { await store.load(channel, retry: true) }
                    }
                }
            }
            .frame(maxWidth: .infinity, minHeight: 48)
            .id("\(channel.slug)|more")
            .onScrollVisibilityChange(threshold: 0.15) { visible in
                guard visible, route == nil, channel.slug == active, movingDown || segment == nil else { return }
                Task { await store.load(channel) }
            }
        } else if channel.total == 0 {
            Text("暂无内容").font(.footnote).foregroundStyle(.secondary).padding(.horizontal, 16)
        }
    }

    private var dateLabel: String {
        guard let date = store.meta?.today else { return "频道" }
        return HotStyle.beijingDay() == date ? "今天" : date
    }

    private func open(_ item: FeedItem) {
        let available = store.channels.flatMap { $0.banner + (store.segments[$0.slug]?.items ?? []) }
        route = ReadingRoute(items: uniqueItems(available), id: item.id)
    }

    private func advance(_ direction: Int) {
        guard let index = store.channels.firstIndex(where: { $0.slug == active }) else { return }
        let next = index + direction
        if store.channels.indices.contains(next) { jump(to: store.channels[next].slug) }
    }

    private func jump(to slug: String) {
        guard let channel = store.channels.first(where: { $0.slug == slug }) else { return }
        movingTo = slug
        active = slug
        position.scrollTo(id: "\(slug)|header", anchor: .top)
        Task { @MainActor in
            if store.segments[slug] == nil { await store.load(channel) }
            if movingTo == slug { movingTo = nil }
        }
    }

    private func refresh() async {
        let before = store.meta?.builtAt
        await store.refresh(around: active)
        if before != nil, store.meta?.builtAt != before { jump(to: active) }
    }
}

func uniqueItems(_ items: [FeedItem]) -> [FeedItem] {
    var seen = Set<String>()
    return items.filter { seen.insert($0.id).inserted }
}
