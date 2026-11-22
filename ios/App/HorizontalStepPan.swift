import SwiftUI
import UIKit

struct HorizontalStepPan: UIGestureRecognizerRepresentable {
    var reservesBackEdge = false
    let action: (Int) -> Void

    func makeCoordinator(converter: CoordinateSpaceConverter) -> Delegate {
        Delegate(reservesBackEdge: reservesBackEdge)
    }

    func makeUIGestureRecognizer(context: Context) -> UIPanGestureRecognizer {
        let recognizer = UIPanGestureRecognizer()
        recognizer.maximumNumberOfTouches = 1
        recognizer.cancelsTouchesInView = false
        recognizer.delegate = context.coordinator
        return recognizer
    }

    func handleUIGestureRecognizerAction(_ recognizer: UIPanGestureRecognizer, context: Context) {
        guard recognizer.state == .ended else { return }
        let distance = recognizer.translation(in: recognizer.view)
        if abs(distance.x) >= 64, abs(distance.x) > 1.5 * abs(distance.y) {
            action(distance.x < 0 ? 1 : -1)
        }
    }

    final class Delegate: NSObject, UIGestureRecognizerDelegate {
        let reservesBackEdge: Bool

        init(reservesBackEdge: Bool) { self.reservesBackEdge = reservesBackEdge }

        func gestureRecognizerShouldBegin(_ gestureRecognizer: UIGestureRecognizer) -> Bool {
            guard let pan = gestureRecognizer as? UIPanGestureRecognizer else { return false }
            let velocity = pan.velocity(in: pan.view)
            return abs(velocity.x) > 1.5 * abs(velocity.y)
        }

        func gestureRecognizer(_ recognizer: UIGestureRecognizer, shouldReceive touch: UITouch) -> Bool {
            if reservesBackEdge, touch.location(in: touch.view?.window).x <= 24 { return false }
            var view = touch.view
            while let ancestor = view, ancestor !== recognizer.view {
                if let scroll = ancestor as? UIScrollView,
                   scroll.contentSize.width > scroll.bounds.width + 4,
                   scroll.contentSize.height <= scroll.bounds.height + 4 { return false }
                view = ancestor.superview
            }
            return true
        }

        func gestureRecognizer(_ recognizer: UIGestureRecognizer, shouldRequireFailureOf other: UIGestureRecognizer) -> Bool {
            reservesBackEdge && other is UIScreenEdgePanGestureRecognizer
        }

        func gestureRecognizer(_ recognizer: UIGestureRecognizer, shouldRecognizeSimultaneouslyWith other: UIGestureRecognizer) -> Bool {
            !(other is UIScreenEdgePanGestureRecognizer)
        }
    }
}

/// Leave the original navigation stack and its edge-pop gesture in charge of returning to the feed.
struct EdgeBackOnly: UIViewControllerRepresentable {
    func makeUIViewController(context: Context) -> Controller { Controller() }
    func updateUIViewController(_ controller: Controller, context: Context) {}

    final class Controller: UIViewController {
        private weak var contentPop: UIGestureRecognizer?
        private var wasEnabled = false

        override func viewDidAppear(_ animated: Bool) {
            super.viewDidAppear(animated)
            if #available(iOS 26.0, *), contentPop == nil,
               let recognizer = navigationController?.interactiveContentPopGestureRecognizer {
                contentPop = recognizer
                wasEnabled = recognizer.isEnabled
                recognizer.isEnabled = false
            }
        }

        override func viewDidDisappear(_ animated: Bool) {
            super.viewDidDisappear(animated)
            contentPop?.isEnabled = wasEnabled
            contentPop = nil
        }
    }
}
