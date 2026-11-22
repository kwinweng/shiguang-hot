import SwiftUI

struct FavoritesScreen: View {
    let favorites: FavoritesStore
    @State private var route: ReadingRoute?

    var body: some View {
        NavigationStack {
            Group {
                if favorites.items.isEmpty {
                    ContentUnavailableView("还没有收藏", systemImage: "bookmark", description: Text("长按一条内容即可收藏。收藏只保存在这部手机上。"))
                } else {
                    ScrollView {
                        LazyVStack(spacing: 0) {
                            ForEach(favorites.items) { item in
                                Button { route = ReadingRoute(items: favorites.items, id: item.id) } label: { FeedRow(item: item) }
                                    .buttonStyle(.plain).itemActions(item, favorites: favorites)
                            }
                        }
                    }
                }
            }
            .overlay(alignment: .bottom) {
                if favorites.writeFailed { Text("没能保存收藏，请重试").font(.footnote).padding().background(.bar) }
            }
            .navigationTitle("收藏").navigationBarTitleDisplayMode(.inline)
            .navigationDestination(item: $route) { DetailScreen(route: $0, favorites: favorites) }
        }
    }
}

struct BloggerScreen: View {
    let api: FeedAPI
    let favorites: FavoritesStore
    @State private var index: BloggerIndex?
    @State private var platformID: String?
    @State private var account = "all"
    @State private var segment = FeedStore.Segment()
    @State private var route: ReadingRoute?
    @State private var status = ""
    private var platform: BloggerIndex.Platform? { index?.platforms.first { $0.id == platformID } }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if let index {
                    ScrollView(.horizontal) {
                        HStack(spacing: 18) {
                            ForEach(index.platforms) { option in
                                Button(option.name) {
                                    if platformID != option.id { platformID = option.id; account = "all"; segment = .init() }
                                }.font(.subheadline.weight(platformID == option.id ? .bold : .regular))
                                    .foregroundStyle(platformID == option.id ? HotStyle.red : .secondary)
                                    .frame(minHeight: 44)
                            }
                        }.padding(.horizontal, 16)
                    }.scrollIndicators(.hidden)
                    Divider()
                    if let platform, !platform.accounts.isEmpty {
                        ScrollView(.horizontal) {
                            HStack(spacing: 15) {
                                accountChoice("全部", key: "all")
                                ForEach(platform.accounts) { person in accountChoice(person.name, key: person.key) }
                            }.padding(.horizontal, 16)
                        }.scrollIndicators(.hidden)
                        Divider()
                    }
                    ScrollView {
                        LazyVStack(spacing: 0) {
                            ForEach(segment.items) { item in
                                Button { route = ReadingRoute(items: segment.items, id: item.id) } label: { FeedRow(item: item) }
                                    .buttonStyle(.plain).itemActions(item, favorites: favorites)
                            }
                            if segment.more {
                                Group {
                                    if segment.loading { ProgressView() }
                                    else { Button(segment.failed ? "重试" : "继续加载") { Task { await load() } } }
                                }.frame(maxWidth: .infinity, minHeight: 48)
                                    .onScrollVisibilityChange(threshold: 0.2) { visible in
                                        if visible, route == nil, !segment.failed { Task { await load() } }
                                    }
                            } else if segment.items.isEmpty {
                                Text("暂无内容").foregroundStyle(.secondary).padding(16)
                            }
                        }
                    }.id(selection)
                    .task(id: selection) { await load() }
                } else if !status.isEmpty {
                    ContentUnavailableView {
                        Label(status, systemImage: "wifi.exclamationmark")
                    } actions: { Button("重试") { Task { await loadIndex() } } }
                } else { ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity) }
            }
            .navigationTitle("博主").navigationBarTitleDisplayMode(.inline)
            .navigationDestination(item: $route) { DetailScreen(route: $0, favorites: favorites) }
            .task { if index == nil { await loadIndex() } }
        }
    }

    private var selection: String { "\(platformID ?? "")|\(account)" }

    private func accountChoice(_ name: String, key: String) -> some View {
        Button(name) { if account != key { account = key; segment = .init() } }
            .font(.caption).foregroundStyle(account == key ? HotStyle.red : .secondary)
            .frame(minHeight: 44)
    }

    private func loadIndex() async {
        do {
            let result = try await api.bloggerIndex()
            try Task.checkCancellation()
            index = result
            platformID = result.platforms.first?.id
        } catch is CancellationError {} catch { status = "暂时取不到博主" }
    }

    private func load() async {
        guard let platformID, segment.more, !segment.loading else { return }
        let current = selection
        let selectedAccount = account
        let next = segment.next
        segment.loading = true
        defer { if current == selection { segment.loading = false } }
        do {
            let page = try await api.blogger(platformID, selectedAccount, next)
            try Task.checkCancellation()
            guard current == selection, segment.next == next else { return }
            segment.append(page)
        } catch is CancellationError {} catch { if current == selection { segment.failed = true } }
    }
}

struct HotScreen: View {
    let api: FeedAPI
    @State private var data: HotRank?
    @State private var archive: HotArchive?
    @State private var provider = "baidu"
    @State private var day: String?
    @State private var error = false

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(spacing: 0) {
                    if let data {
                        HStack {
                            ForEach(data.providers) { source in
                                Button(source.id == "bilibili" ? "B站" : source.name) { provider = source.id }
                                    .font(.subheadline.weight(provider == source.id ? .bold : .regular))
                                    .frame(maxWidth: .infinity, minHeight: 44)
                                    .foregroundStyle(provider == source.id ? HotStyle.red : .secondary)
                            }
                        }
                        Divider()
                        if let source = data.providers.first(where: { $0.id == provider }), source.status == "ok" {
                            ForEach(source.items) { entry in
                                if let link = FeedAPI.externalURL(entry.url) {
                                    Link(destination: link) {
                                        HStack(alignment: .firstTextBaseline, spacing: 10) {
                                            Text(entry.pinned ? "置顶" : "\(entry.rank)").font(.subheadline.monospacedDigit().bold())
                                                .foregroundStyle(entry.rank <= 3 ? HotStyle.red : .secondary).frame(minWidth: 30, alignment: .leading)
                                            Text(entry.title).font(.headline).foregroundStyle(.primary)
                                            Spacer(minLength: 0)
                                            if let label = entry.hotLabel { Text(label).font(.caption).foregroundStyle(.secondary) }
                                        }.frame(maxWidth: .infinity, minHeight: 50, alignment: .leading).padding(.horizontal, 16)
                                    }.contextMenu { ShareLink(item: link) }
                                    Divider().padding(.leading, 16)
                                }
                            }
                        } else { Text("该榜暂时取不到").foregroundStyle(.secondary).padding(20) }
                    } else if error {
                        Button("暂时取不到，重试") { Task { await read(day) } }.padding(24)
                    } else { ProgressView().padding(24) }
                }
            }
            .refreshable { await read(day) }
            .navigationTitle("热搜").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu(day ?? "今天", systemImage: "calendar") {
                        Button("最新") { day = nil }
                        ForEach(archive?.dates ?? []) { date in Button(date.date) { day = date.date } }
                    }
                }
            }
            .task(id: day) {
                await read(day)
                if archive == nil { archive = try? await api.hotArchive() }
            }
        }
    }

    private func read(_ selected: String?) async {
        error = false
        if selected == day { data = nil }
        do {
            let result = try await api.rank(day: selected)
            try Task.checkCancellation()
            if selected == day { data = result }
        } catch is CancellationError {} catch { if selected == day { self.error = true } }
    }
}
