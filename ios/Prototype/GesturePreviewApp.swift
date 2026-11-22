import SwiftUI
import UIKit

@main
struct GesturePreviewApp: App {
    var body: some Scene {
        WindowGroup { PreviewNavigation().ignoresSafeArea() }
    }
}

private struct PreviewNavigation: UIViewControllerRepresentable {
    func makeUIViewController(context: Context) -> UINavigationController {
        let root = UIHostingController(rootView: PreviewList(open: context.coordinator.open))
        root.title = "资讯手势预览"
        root.navigationItem.backButtonTitle = "资讯"
        let nav = UINavigationController(rootViewController: root)
        context.coordinator.navigation = nav
        return nav
    }

    func updateUIViewController(_ controller: UINavigationController, context: Context) {}
    func makeCoordinator() -> Coordinator { Coordinator() }

    final class Coordinator: NSObject, UIGestureRecognizerDelegate {
        weak var navigation: UINavigationController?
        private var flip: ((Int) -> Void)?
        private weak var activeDetail: UIViewController?
        private let model = PreviewSelection()

        func open(index: Int, policy: PreviewPolicy) {
            guard let navigation, navigation.viewControllers.count == 1 else { return }
            model.index = index
            let detail = UIHostingController(rootView: PreviewArticle(selection: model, policy: policy))
            detail.title = policy.rawValue
            detail.navigationItem.largeTitleDisplayMode = .never
            activeDetail = detail
            navigation.interactiveContentPopGestureRecognizer?.isEnabled = policy == .system
            if policy == .web {
                flip = { [model] delta in model.move(delta) }
                let pan = UIPanGestureRecognizer(target: self, action: #selector(translate(_:)))
                pan.delegate = self
                pan.cancelsTouchesInView = false
                if let edge = navigation.interactivePopGestureRecognizer { pan.require(toFail: edge) }
                detail.view.addGestureRecognizer(pan)
            }
            navigation.pushViewController(detail, animated: !UIAccessibility.isReduceMotionEnabled)
        }

        func gestureRecognizerShouldBegin(_ recognizer: UIGestureRecognizer) -> Bool {
            guard let pan = recognizer as? UIPanGestureRecognizer, let view = activeDetail?.view else { return false }
            let velocity = pan.velocity(in: view)
            let origin = pan.location(in: view).x - pan.translation(in: view).x
            return origin > 24 && abs(velocity.x) > abs(velocity.y) * 1.25
        }

        @objc private func translate(_ pan: UIPanGestureRecognizer) {
            guard pan.state == .ended else { return }
            let distance = pan.translation(in: pan.view).x
            if abs(distance) >= 64 { flip?(distance < 0 ? 1 : -1) }
        }
    }
}

private enum PreviewPolicy: String, CaseIterable, Identifiable {
    case web = "A · 沿用网页"
    case system = "B · iOS 返回"
    var id: Self { self }
}

@Observable @MainActor
private final class PreviewSelection {
    var index = 1
    func move(_ delta: Int) { index = min(max(0, index + delta), PreviewList.titles.count - 1) }
}

private struct PreviewList: View {
    let open: (Int, PreviewPolicy) -> Void
    @State private var policy = PreviewPolicy.web
    static let titles = ["早间速览：城市街区的一天", "长读：把日常小事记下来", "周末去哪里：三条慢行路线"]

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Picker("详情手势", selection: $policy) {
                ForEach(PreviewPolicy.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            Text("从第二条打开，在正文中间向右滑。换另一种方式再试一次。")
                .font(.subheadline).foregroundStyle(.secondary)
            ForEach(Array(Self.titles.enumerated()), id: \.offset) { index, title in
                Button { open(index, policy) } label: {
                    HStack(spacing: 14) {
                        Text("0\(index + 1)").font(.caption.monospacedDigit()).foregroundStyle(.red)
                        Text(title).font(.headline).foregroundStyle(.primary)
                        Spacer()
                        Image(systemName: "chevron.right").font(.caption).foregroundStyle(.secondary).accessibilityHidden(true)
                    }
                    .frame(minHeight: 48)
                    .contentShape(.rect)
                }.buttonStyle(.plain).accessibilityIdentifier("preview-row-\(index)")
                Divider()
            }
            Text("此原型只比较详情页的横滑手势，使用示例文章。")
                .font(.footnote).foregroundStyle(.secondary)
            Spacer()
        }
        .padding(20)
        .background(Color(uiColor: .systemBackground))
    }
}

private struct PreviewArticle: View {
    let selection: PreviewSelection
    let policy: PreviewPolicy
    @State private var gallery = false
    @State private var image = 0

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text("示例文章 · \(selection.index + 1) / 3")
                    .font(.subheadline.monospacedDigit()).foregroundStyle(.red)
                    .accessibilityIdentifier("preview-article-number")
                Text(PreviewList.titles[selection.index]).font(.largeTitle.bold())
                    .accessibilityAddTraits(.isHeader)
                Text(policy == .web ? "正文中间横滑翻条，左边缘右滑返回。" : "正文中间右滑也能返回，翻条用底部按钮。")
                    .font(.subheadline).foregroundStyle(.secondary)
                Text("路口的早餐摊刚开门。沿河走两条街，风声慢一点，树影落在石阶上。这里是演示正文，可以在这一段中间横滑。")
                    .font(.body).lineSpacing(7).frame(maxWidth: .infinity, alignment: .leading)
                Button("打开图集", systemImage: "photo.on.rectangle.angled") {
                    image = 0
                    gallery = true
                }.buttonStyle(.bordered)
                Text("试看：打开图集，横滑只换图；从详情左上角或边缘返回，仍可点回原来那条。")
                    .font(.body).lineSpacing(7)
            }.padding(20)
        }
        .contentShape(.rect)
        .safeAreaInset(edge: .bottom) {
            HStack {
                Button("上一条", systemImage: "chevron.left") { selection.move(-1) }
                    .disabled(selection.index == 0)
                Spacer()
                Button("下一条", systemImage: "chevron.right") { selection.move(1) }
                    .disabled(selection.index == PreviewList.titles.count - 1)
            }.padding().background(.bar)
        }
        .tint(.red)
        .fullScreenCover(isPresented: $gallery) {
            ZStack(alignment: .topTrailing) {
                Color.black.ignoresSafeArea()
                TabView(selection: $image) {
                    ForEach(["sun.haze", "cloud.moon"], id: \.self) { name in
                        Image(systemName: name)
                            .font(.system(size: 96)).foregroundStyle(.white)
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                            .tag(name == "sun.haze" ? 0 : 1)
                    }
                }.tabViewStyle(.page)
                Button("关闭图集", systemImage: "xmark") { gallery = false }
                    .labelStyle(.iconOnly).buttonStyle(.bordered).tint(.white).padding()
            }
            .simultaneousGesture(DragGesture(minimumDistance: 32).onEnded {
                if $0.translation.height > 90 && $0.translation.height > abs($0.translation.width) * 1.5 {
                    gallery = false
                }
            })
        }
    }
}
