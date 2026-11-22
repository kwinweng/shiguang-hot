import Foundation

struct LegacyFavoriteMigration {
    static let completionKey = "hot-favorites-native-import-v1"
    let file: URL

    init(file: URL = URL.applicationSupportDirectory.appending(path: "hot-favorites.json")) {
        self.file = file
    }

    func payload() throws -> String? {
        let data: Data
        do { data = try Data(contentsOf: file) }
        catch let error as CocoaError where error.code == .fileReadNoSuchFile { return nil }
        let items = try JSONDecoder().decode([FeedItem].self, from: data)
        guard !items.isEmpty else { return nil }
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return String(decoding: try encoder.encode(items), as: UTF8.self)
    }

    // Only invoked by native code on the first successful load of the real site. No JS read API.
    // Store the marker with the merged snapshot: retrying after an interrupted acknowledgement must not restore deletions.
    static let script = """
    if (location.origin !== 'https://news.kwinweng.com' || location.pathname !== '/') throw Error('unexpected document');
    const f = window.RebangFavorites;
    if (!f || typeof f.snapshot !== 'function' || typeof f.STORAGE_KEY !== 'string') throw Error('favorites unavailable');
    const prior = localStorage.getItem(f.STORAGE_KEY);
    const saved = prior === null ? null : JSON.parse(prior);
    if (saved?.nativeImportV1 === true) return true;
    if (saved !== null && !Array.isArray(saved) && !Array.isArray(saved.items)) throw Error('unexpected favorites format');
    const existing = f.load();
    const seen = new Set(existing.map(x => x.id));
    for (const item of JSON.parse(payload)) {
        if (!item.id || seen.has(item.id)) continue;
        const snapshot = f.snapshot({...item, translated: !!item.translation});
        existing.push({...item, ...snapshot, translation: item.translation ?? null});
        seen.add(item.id);
    }
    localStorage.setItem(f.STORAGE_KEY, JSON.stringify({version: 1, items: existing, nativeImportV1: true}));
    return true;
    """
}
