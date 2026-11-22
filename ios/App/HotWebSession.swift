import SafariServices
import SwiftUI
import WebKit

@MainActor @Observable
final class HotWebSession: NSObject, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandlerWithReply {
    private static let origin = URL(string: "https://news.kwinweng.com/")!
    private(set) var pageFailed = false
    var importFailed = false
    private var importing = false
    private weak var web: WKWebView?

    func makeWebView() -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()
        config.allowsInlineMediaPlayback = true
        config.userContentController.addScriptMessageHandler(self, contentWorld: .page, name: "hotShare")
        config.userContentController.addUserScript(WKUserScript(source: Self.shareFallback,
            injectionTime: .atDocumentStart, forMainFrameOnly: true))
        let view = WKWebView(frame: .zero, configuration: config)
        view.navigationDelegate = self
        view.uiDelegate = self
        // The site's touch handlers own article navigation, including the edge.
        view.allowsBackForwardNavigationGestures = false
        view.scrollView.contentInsetAdjustmentBehavior = .never
        view.underPageBackgroundColor = .systemBackground
        web = view
        view.load(URLRequest(url: Self.origin))
        return view
    }

    func retry() {
        pageFailed = false
        web?.load(URLRequest(url: Self.origin))
    }

    private static func trusted(_ url: URL?) -> Bool {
        guard let url else { return false }
        return url.scheme == "https" && url.host == origin.host && url.port == nil
            && url.user == nil && url.password == nil
    }

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction) async -> WKNavigationActionPolicy {
        guard let url = action.request.url else { return .cancel }
        // Third-party HTTPS media frames keep their normal WebKit behavior, not native privileges.
        if let target = action.targetFrame, !target.isMainFrame { return .allow }
        if action.targetFrame == nil { return .allow } // WKUIDelegate owns new windows.
        if Self.trusted(url) { return .allow }
        if action.navigationType == .linkActivated, action.sourceFrame.isMainFrame, Self.trusted(action.sourceFrame.request.url) {
            openExternal(url)
        }
        return .cancel
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        guard action.targetFrame == nil, let url = action.request.url else { return nil }
        if Self.trusted(action.sourceFrame.request.url) && action.sourceFrame.isMainFrame {
            if Self.trusted(url) { webView.load(action.request) }
            else { openExternal(url) }
        }
        return nil
    }

    func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse) async -> WKNavigationResponsePolicy {
        guard response.isForMainFrame else { return .allow }
        if !Self.trusted(response.response.url) || (response.response as? HTTPURLResponse).map({ $0.statusCode >= 400 }) == true {
            pageFailed = true
            return .cancel
        }
        return .allow
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: any Error) {
        if (error as NSError).code != NSURLErrorCancelled { pageFailed = true }
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: any Error) {
        if (error as NSError).code != NSURLErrorCancelled { pageFailed = true }
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) { pageFailed = true }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        pageFailed = false
        guard Self.trusted(webView.url), webView.url?.path == "/", !importing,
              !UserDefaults.standard.bool(forKey: LegacyFavoriteMigration.completionKey) else { return }
        importing = true
        Task { @MainActor in
            defer { importing = false }
            do {
                guard let payload = try LegacyFavoriteMigration().payload() else { return }
                let result = try await webView.callAsyncJavaScript(LegacyFavoriteMigration.script,
                    arguments: ["payload": payload], in: nil, contentWorld: .page)
                guard result as? Bool == true else { importFailed = true; return }
                UserDefaults.standard.set(true, forKey: LegacyFavoriteMigration.completionKey)
            } catch { importFailed = true }
        }
    }

    private func openExternal(_ url: URL) {
        guard ["https", "http"].contains(url.scheme ?? ""), url.host != nil, url.user == nil, url.password == nil else { return }
        presenter?.present(SFSafariViewController(url: url), animated: true)
    }

    private var presenter: UIViewController? {
        var controller = web?.window?.rootViewController
        while let next = controller?.presentedViewController { controller = next }
        return controller
    }

    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) async -> (Any?, String?) {
        guard message.name == "hotShare", message.frameInfo.isMainFrame, Self.trusted(message.frameInfo.request.url),
              Self.trusted(web?.url), let data = message.body as? [String: Any], let text = data["url"] as? String,
              text.utf8.count <= 4096, let url = URL(string: text), Self.trusted(url), url.path == "/",
              url.fragment?.hasPrefix("/item/") == true, let presenter else { return (nil, "share unavailable") }
        return await withCheckedContinuation { continuation in
            let sheet = UIActivityViewController(activityItems: [url], applicationActivities: nil)
            sheet.completionWithItemsHandler = { _, completed, _, error in
                continuation.resume(returning: error == nil ? (completed, nil) : (nil, "share unavailable"))
            }
            presenter.present(sheet, animated: true)
        }
    }

    private static let shareFallback = """
    if (location.origin === 'https://news.kwinweng.com' && typeof navigator.share !== 'function') {
        Object.defineProperty(navigator, 'share', { configurable: true, value: async ({url}) => {
            if (!navigator.userActivation?.isActive) throw new DOMException('User action required', 'NotAllowedError');
            const completed = await window.webkit.messageHandlers.hotShare.postMessage({url});
            if (!completed) throw new DOMException('Share cancelled', 'AbortError');
        }});
    }
    """
}

struct HotWebView: UIViewRepresentable {
    let session: HotWebSession
    func makeUIView(context: Context) -> WKWebView { session.makeWebView() }
    func updateUIView(_ web: WKWebView, context: Context) {}
}
