import Foundation

struct FeedItem: Codable, Identifiable, Sendable {
    let id: String
    let kind: String
    let channel: String?
    let sourceName: String
    let title: String
    let summary: String
    let body: String?
    let url: String
    let publishedAt: String
    let image: Artwork?
    let translation: Translation?
    let blocks: [Block]?
    let highlight: Bool?
    let quote: Quote?
    let tg: Telegram?
    let blogger: Blogger?

    var displayTitle: String { translation?.title?.nonblank ?? title.nonblank ?? blogger?.displayName ?? sourceName }
    var displaySummary: String { translation?.summary?.nonblank ?? summary }
    var shareURL: URL { FeedAPI.shareURL(id) }
    var originalURL: URL? { FeedAPI.externalURL(url) }

    struct Artwork: Codable, Sendable {
        let url: String
        let width: Int?
        let height: Int?
    }

    struct Translation: Codable, Sendable {
        let title: String?
        let summary: String?
        let body: String?
        let blocks: [Block]?
        let bodyPending: Bool?
    }

    struct Block: Codable, Sendable {
        let type: String
        let text: String?
        let items: [String]?
        let src: String?
        let alt: String?
        let width: Int?
        let height: Int?
        let missing: Bool?
    }

    struct Quote: Codable, Sendable {
        let kind: String?
        let sourceName: String?
        let displayName: String?
        let handle: String?
        let text: String?
        let textZh: String?
        let url: String?
    }

    struct Comment: Codable, Sendable {
        let handle: String?
        let displayName: String?
        let text: String
        let textZh: String?
        let like: Int?
        let replyText: String?
    }

    struct Telegram: Codable, Sendable {
        let views: Int?
        let viewsLabel: String?
        let commentsTotal: Int?
        let reactions: [Reaction]?
        let comments: [Comment]?
    }

    struct Reaction: Codable, Sendable {
        let emoji: String
        let count: Int
    }

    struct Blogger: Codable, Sendable {
        let displayName: String?
        let handle: String?
        let platform: String?
        let avatar: String?
        let metrics: [String: Int]?
        let media: [Media]?
        let quote: Quote?
        let comments: [Comment]?
    }

    struct Media: Codable, Sendable {
        let type: String
        let url: String
        let previewUrl: String?
    }
}

struct FeedMeta: Codable, Sendable {
    let schema: String
    let builtAt: String
    let today: String
    let fixture: Bool
    let pageSize: Int
    let channels: [Channel]
}

struct Channel: Codable, Identifiable, Sendable {
    let slug: String
    let name: String
    let order: Int
    let total: Int
    let feedTotal: Int
    let pages: Int
    let banner: [FeedItem]
    var id: String { slug }
}

struct FeedPage: Codable, Sendable {
    let schema: String
    let channel: String?
    let platform: String?
    let key: String?
    let page: Int
    let pages: Int
    let total: Int
    let hasMore: Bool
    let items: [FeedItem]

    private enum CodingKeys: String, CodingKey { case schema, channel, platform, key, page, pages, total, hasMore, items }

    init(from decoder: any Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        schema = try values.decode(String.self, forKey: .schema)
        channel = try values.decodeIfPresent(String.self, forKey: .channel)
        platform = try values.decodeIfPresent(String.self, forKey: .platform)
        key = try values.decodeIfPresent(String.self, forKey: .key)
        page = try values.decode(Int.self, forKey: .page)
        pages = try values.decode(Int.self, forKey: .pages)
        total = try values.decode(Int.self, forKey: .total)
        hasMore = try values.decode(Bool.self, forKey: .hasMore)
        var array = try values.nestedUnkeyedContainer(forKey: .items)
        guard let count = array.count, count <= 30 else { throw FeedAPI.Failure.contract }
        var decoded: [FeedItem] = []
        while !array.isAtEnd {
            // superDecoder consumes the entry even when the item is malformed.
            let element = try array.superDecoder()
            if let item = try? FeedItem(from: element), !item.id.isEmpty, ["post", "news"].contains(item.kind) {
                decoded.append(item)
            }
        }
        guard count == 0 || !decoded.isEmpty else { throw FeedAPI.Failure.contract }
        items = decoded
    }
}

struct BloggerIndex: Decodable, Sendable {
    let schema: String
    let platforms: [Platform]

    struct Platform: Decodable, Identifiable, Sendable {
        let id: String
        let name: String
        let count: Int
        let status: String?
        let accounts: [Account]
    }

    struct Account: Decodable, Identifiable, Sendable {
        let key: String
        let name: String
        let total: Int
        var id: String { key }
    }
}

struct HotRank: Decodable, Sendable {
    let schema: String
    let providers: [Provider]

    struct Provider: Decodable, Identifiable, Sendable {
        let id: String
        let name: String
        let status: String
        let items: [Entry]
    }

    struct Entry: Decodable, Identifiable, Sendable {
        let rank: Int
        let title: String
        let url: String
        let pinned: Bool
        let hotLabel: String?
        let hotScore: Int?
        var id: String { "\(rank)|\(url)" }
    }
}

struct HotArchive: Decodable, Sendable {
    let schema: String
    let dates: [Day]
    struct Day: Decodable, Identifiable, Sendable {
        let date: String
        var id: String { date }
    }
}

extension String {
    var nonblank: String? {
        let clean = trimmingCharacters(in: .whitespacesAndNewlines)
        return clean.isEmpty ? nil : clean
    }
}
