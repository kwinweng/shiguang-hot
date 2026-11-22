import Foundation
import Observation

@MainActor @Observable
final class FeedStore {
    struct Segment {
        var items: [FeedItem] = []
        var next = 1
        var more = true
        var failed = false
        var loading = false
        private var seen: Set<String> = []

        mutating func append(_ page: FeedPage, excluding banner: [FeedItem] = []) {
            seen.formUnion(banner.map(\.id))
            items.append(contentsOf: page.items.filter { seen.insert($0.id).inserted })
            next = page.page + 1
            more = page.hasMore
            failed = false
        }
    }

    private struct CachedOpening: Codable {
        let meta: FeedMeta
        let slug: String
        let segmentPage: FeedPage
    }

    let api: FeedAPI
    private let openingFile: URL
    private(set) var meta: FeedMeta?
    private(set) var segments: [String: Segment] = [:]
    private(set) var updating = false
    private(set) var startupFailed = false
    private(set) var updateAvailable = false
    @ObservationIgnored private var generation = UUID()

    init(api: FeedAPI, openingFile: URL = URL.cachesDirectory.appending(path: "hot-opening.json")) {
        self.api = api
        self.openingFile = openingFile
    }

    var channels: [Channel] { meta?.channels.sorted { $0.order < $1.order } ?? [] }

    func start() async {
        guard meta == nil, !updating else { return }
        if let data = try? Data(contentsOf: openingFile),
           let cached = try? JSONDecoder().decode(CachedOpening.self, from: data),
           !cached.meta.fixture, cached.segmentPage.channel == cached.slug,
           cached.segmentPage.page == 1, let channel = cached.meta.channels.first(where: { $0.slug == cached.slug }) {
            var segment = Segment()
            segment.append(cached.segmentPage, excluding: channel.banner)
            segments[cached.slug] = segment
            meta = cached.meta
        }
        await refresh(around: channels.first?.slug)
    }

    func refresh(around slug: String?) async {
        guard !updating else { return }
        updating = true
        defer { updating = false }
        do {
            let incoming = try await api.meta()
            guard let channel = incoming.channels.first(where: { $0.slug == slug }) ?? incoming.channels.min(by: { $0.order < $1.order }) else { return }
            if incoming.builtAt == meta?.builtAt, segments[channel.slug]?.next ?? 1 > 1, !updateAvailable {
                startupFailed = false
                return
            }
            let page = try await api.channel(channel.slug, 1)
            try Task.checkCancellation()
            guard page.pages == channel.pages, page.total == channel.feedTotal else { throw FeedAPI.Failure.contract }
            var fresh = Segment()
            fresh.append(page, excluding: channel.banner)
            generation = UUID()
            meta = incoming
            segments = [channel.slug: fresh]
            startupFailed = false
            updateAvailable = false
            if channel.slug == incoming.channels.min(by: { $0.order < $1.order })?.slug,
               let data = try? JSONEncoder().encode(CachedOpening(meta: incoming, slug: channel.slug, segmentPage: page)) {
                try? data.write(to: openingFile, options: .atomic)
            }
        } catch is CancellationError {
            return
        } catch {
            startupFailed = true
        }
    }

    func load(_ channel: Channel, retry: Bool = false) async {
        var segment = segments[channel.slug] ?? Segment()
        guard segment.more, !segment.loading, !segment.failed || retry else { return }
        let requested = segment.next
        let snapshot = generation
        segment.loading = true
        segment.failed = false
        segments[channel.slug] = segment
        defer {
            if snapshot == generation { segments[channel.slug]?.loading = false }
        }
        do {
            let page = try await api.channel(channel.slug, requested)
            try Task.checkCancellation()
            guard snapshot == generation, segments[channel.slug]?.next == requested else { return }
            if page.total != channel.feedTotal || page.pages != channel.pages { updateAvailable = true }
            segments[channel.slug]?.append(page, excluding: channel.banner)
        } catch is CancellationError {
            return
        } catch FeedAPI.Failure.http(404) {
            guard snapshot == generation else { return }
            updateAvailable = true
            segments[channel.slug]?.failed = true
        } catch {
            if snapshot == generation { segments[channel.slug]?.failed = true }
        }
    }
}

@MainActor @Observable
final class FavoritesStore {
    private(set) var items: [FeedItem] = []
    private let file: URL
    private(set) var writeFailed = false

    init(file: URL = URL.applicationSupportDirectory.appending(path: "hot-favorites.json")) {
        self.file = file
        if let data = try? Data(contentsOf: file), let stored = try? JSONDecoder().decode([FeedItem].self, from: data) {
            items = stored
        }
    }

    func contains(_ item: FeedItem) -> Bool { items.contains { $0.id == item.id } }

    func toggle(_ item: FeedItem) {
        var next = items
        if let index = next.firstIndex(where: { $0.id == item.id }) { next.remove(at: index) }
        else { next.insert(item, at: 0) }
        do {
            try FileManager.default.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
            try JSONEncoder().encode(next).write(to: file, options: .atomic)
            items = next
            writeFailed = false
        } catch {
            writeFailed = true
        }
    }
}
