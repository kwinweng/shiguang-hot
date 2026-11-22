import SwiftUI

@main
struct ShiguangHotApp: App {
    @State private var session = HotWebSession()

    var body: some Scene {
        WindowGroup {
            @Bindable var session = session
            ZStack {
                HotWebView(session: session).ignoresSafeArea()
                if session.pageFailed {
                    ContentUnavailableView {
                        Label("暂时打不开拾光资讯", systemImage: "wifi.exclamationmark")
                    } actions: {
                        Button("重试") { session.retry() }
                    }.background(Color(uiColor: .systemBackground))
                }
            }
            .alert("旧收藏暂未导入", isPresented: $session.importFailed) {
                Button("稍后", role: .cancel) {}
                Button("重试") { session.retry() }
            } message: {
                Text("原来的收藏文件仍在这台设备上。连接网络后可重试。")
            }
        }
    }
}
