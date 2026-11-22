import Foundation

actor FeedAPI {
    static let liveOrigin = URL(string: "https://news.kwinweng.com/")!
    static let channelSlugs: Set<String> = ["current", "world", "finance", "tech-ai", "digital", "tools"]
    let origin: URL
    let session: URLSession

    enum Failure: Error, Equatable {
        case contract
        case http(Int)
    }

    init(origin: URL = liveOrigin, session: URLSession = .shared) {
        self.origin = origin
        self.session = session
    }

    func meta() async throws -> FeedMeta {
        let meta: FeedMeta = try await read("meta.json", limit: 1_000_000)
        let slugs = meta.channels.map(\.slug)
        guard meta.schema == "rebang.site-meta/1", !meta.fixture, meta.pageSize == 30,
              !meta.builtAt.isEmpty, slugs.count == 6, Set(slugs) == Self.channelSlugs,
              meta.channels.allSatisfy({ $0.pages >= 1 && $0.feedTotal >= 0 && $0.banner.count <= 5 }) else { throw Failure.contract }
        return meta
    }

    func channel(_ slug: String, _ number: Int) async throws -> FeedPage {
        guard Self.channelSlugs.contains(slug), number > 0 else { throw Failure.contract }
        let page = try await page("channel/\(slug)/page-\(number).json", number)
        guard page.channel == slug, page.items.allSatisfy({ $0.channel == slug && $0.kind == "news" }) else { throw Failure.contract }
        return page
    }

    func bloggerIndex() async throws -> BloggerIndex {
        let index: BloggerIndex = try await read("bloggers.json", limit: 16_000_000)
        guard index.schema == "rebang.site-bloggers/1" else { throw Failure.contract }
        return index
    }

    func blogger(_ platform: String, _ key: String, _ number: Int) async throws -> FeedPage {
        guard platform.wholeMatch(of: /[a-z0-9-]+/) != nil,
              key == "all" || key.wholeMatch(of: /h-[0-9a-f]+/) != nil, number > 0 else { throw Failure.contract }
        let page = try await page("blogger/\(platform)/\(key)/page-\(number).json", number)
        guard page.platform == platform, page.key == key, page.items.allSatisfy({ $0.kind == "post" }) else { throw Failure.contract }
        return page
    }

    func rank(day: String?) async throws -> HotRank {
        if let day, day.wholeMatch(of: /[0-9]{4}-[0-9]{2}-[0-9]{2}/) == nil { throw Failure.contract }
        let result: HotRank = try await read(day.map { "hotsearch/\($0).json" } ?? "hotsearch.json", limit: 2_000_000)
        guard result.schema == "rebang.hotsearch/1" else { throw Failure.contract }
        return result
    }

    func hotArchive() async throws -> HotArchive {
        let result: HotArchive = try await read("hotsearch/index.json", limit: 200_000)
        guard result.schema == "rebang.hotsearch-index/1" else { throw Failure.contract }
        return result
    }

    private func page(_ path: String, _ number: Int) async throws -> FeedPage {
        let page: FeedPage = try await read(path, limit: 4_000_000)
        guard page.schema == "rebang.page/1", page.page == number, page.pages >= number, page.total >= 0,
              page.hasMore == (number < page.pages) else { throw Failure.contract }
        return page
    }

    private func read<T: Decodable>(_ path: String, limit: Int) async throws -> T {
        let url = origin.appending(path: "data/\(path)")
        let (data, response) = try await session.data(for: URLRequest(url: url, timeoutInterval: 20))
        guard let http = response as? HTTPURLResponse else { throw Failure.contract }
        guard http.statusCode == 200 else { throw Failure.http(http.statusCode) }
        guard http.url?.host == origin.host, data.count <= limit else { throw Failure.contract }
        return try Self.decoder().decode(T.self, from: data)
    }

    static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    static func shareURL(_ id: String) -> URL {
        var components = URLComponents(url: liveOrigin, resolvingAgainstBaseURL: false)!
        let allowed = CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~")
        components.percentEncodedFragment = "/item/" + (id.addingPercentEncoding(withAllowedCharacters: allowed) ?? "")
        return components.url!
    }

    static func externalURL(_ value: String) -> URL? {
        guard let components = URLComponents(string: value), let scheme = components.scheme?.lowercased(),
              ["https", "http"].contains(scheme), let host = components.host, !host.isEmpty,
              components.user == nil, components.password == nil else { return nil }
        return components.url
    }

    static func mediaURL(_ value: String?) -> URL? {
        guard let value = value?.nonblank else { return nil }
        if let url = externalURL(value) {
            var parts = URLComponents(url: url, resolvingAgainstBaseURL: false)
            parts?.scheme = "https"
            return parts?.url
        }
        guard value.hasPrefix("media/") || value.hasPrefix("/media/"),
              let resolved = URL(string: value, relativeTo: liveOrigin)?.absoluteURL,
              resolved.host == liveOrigin.host, resolved.path.hasPrefix("/media/"),
              !resolved.pathComponents.contains("..") else { return nil }
        return resolved
    }
}
