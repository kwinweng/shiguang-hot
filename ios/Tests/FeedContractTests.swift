import Foundation
import Testing
@testable import ShiguangHot

struct FeedContractTests {
    private let pageJSON = #"{"schema":"rebang.page/1","channel":"current","page":1,"pages":2,"total":31,"has_more":true,"items":[{"id":"broken"},{"id":"tg:9","kind":"news","channel":"current","source_name":"示例频道","title":"原题","summary":"原摘要","url":"https://example.com/story","published_at":"2026-11-19T23:00:00+08:00","translation":{"title":"译题","summary":"译摘要","body_pending":true}}]}"#

    @Test func pageDecodesKnownEntriesAndKeepsTranslation() throws {
        let page = try FeedAPI.decoder().decode(FeedPage.self, from: Data(pageJSON.utf8))
        #expect(page.hasMore)
        #expect(page.items.map(\.id) == ["tg:9"])
        #expect(page.items[0].displayTitle == "译题")
        #expect(page.items[0].translation?.bodyPending == true)
        let persisted = try JSONEncoder().encode(page)
        let restored = try JSONDecoder().decode(FeedPage.self, from: persisted)
        #expect(restored.items.first?.displayTitle == "译题")
    }

    @Test func telegramCommentIdentifiersDoNotBreakBannerDecoding() throws {
        let json = #"{"slug":"finance","name":"财经","order":2,"total":1,"feed_total":0,"pages":1,"banner":[{"id":"tg:9","kind":"news","channel":"finance","source_name":"频道","title":"标题","summary":"摘要","url":"https://example.com/story","published_at":"2026-11-19T23:00:00+08:00","tg":{"comments":[{"id":12345,"text":"一条回复","reply_to":12344,"reply_text":"上一级评论"}]}}]}"#
        let channel = try FeedAPI.decoder().decode(Channel.self, from: Data(json.utf8))
        let comment = try #require(channel.banner.first?.tg?.comments?.first)
        #expect(comment.text == "一条回复")
        #expect(comment.replyText == "上一级评论")
    }

    @Test func sharingAndMediaUseExpectedOrigin() {
        #expect(FeedAPI.shareURL("tg:1/a#中").absoluteString == "https://news.kwinweng.com/#/item/tg%3A1%2Fa%23%E4%B8%AD")
        #expect(FeedAPI.mediaURL("media/tg/cover.jpg")?.absoluteString == "https://news.kwinweng.com/media/tg/cover.jpg")
        #expect(FeedAPI.mediaURL("http://example.com/media.jpg")?.scheme == "https")
        #expect(FeedAPI.mediaURL("media/../outside.jpg") == nil)
        #expect(FeedAPI.externalURL("javascript:alert(1)") == nil)
    }

    @MainActor @Test func paginationDeduplicatesStableIdentifiers() throws {
        let data = Data(pageJSON.utf8)
        let first = try FeedAPI.decoder().decode(FeedPage.self, from: data)
        let nextJSON = pageJSON.replacingOccurrences(of: #""page":1"#, with: #""page":2"#)
            .replacingOccurrences(of: #""has_more":true"#, with: #""has_more":false"#)
        let second = try FeedAPI.decoder().decode(FeedPage.self, from: Data(nextJSON.utf8))
        var segment = FeedStore.Segment()
        segment.append(first)
        segment.append(second)
        #expect(segment.items.map(\.id) == ["tg:9"])
        #expect(segment.next == 3)
        #expect(!segment.more)
    }

    @MainActor @Test func upgradeReadsBuildOneFavoriteWithoutChangingBackup() throws {
        let item = try #require(FeedAPI.decoder().decode(FeedPage.self, from: Data(pageJSON.utf8)).items.first)
        let directory = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let file = directory.appending(path: "hot-favorites.json")
        let migration = LegacyFavoriteMigration(file: file)
        #expect(try migration.payload() == nil)
        FavoritesStore(file: file).toggle(item)
        let original = try Data(contentsOf: file)
        let raw = try migration.payload()
        let payload = try #require(raw)
        let compatible = try FeedAPI.decoder().decode([FeedItem].self, from: Data(payload.utf8))
        #expect(compatible.map(\.id) == ["tg:9"])
        #expect(compatible.first?.displayTitle == "译题")
        #expect(try Data(contentsOf: file) == original)
    }

    @MainActor @Test func favoriteRetainsArticleWithoutServer() throws {
        let item = try #require(FeedAPI.decoder().decode(FeedPage.self, from: Data(pageJSON.utf8)).items.first)
        let directory = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let file = directory.appending(path: "favorites.json")
        FavoritesStore(file: file).toggle(item)
        let reopened = FavoritesStore(file: file)
        #expect(reopened.items.first?.displayTitle == "译题")
        reopened.toggle(item)
        #expect(FavoritesStore(file: file).items.isEmpty)
    }
}
