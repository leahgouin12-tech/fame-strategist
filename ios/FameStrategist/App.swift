import UIKit
import WebKit

/// One web view, one saved address, and a box to change it. The app is a window onto the laptop;
/// everything that does work lives there.
final class ServerViewController: UIViewController, WKNavigationDelegate {

    private static let defaultsKey = "fame.server"

    private var web: WKWebView!
    private var bar: UIToolbar!

    /// The address a phone types: scheme, the laptop's wifi address, port, and the first screen.
    /// Nothing in here points at the internet, and nothing in here is hardcoded to one machine -
    /// the laptop's address changes when the router feels like it, so it has to stay editable.
    private var startURL: URL? {
        if let saved = UserDefaults.standard.string(forKey: Self.defaultsKey),
           let url = URL(string: saved) {
            return url
        }
        return nil
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = UIColor(red: 0x12 / 255.0, green: 0x12 / 255.0,
                                       blue: 0x13 / 255.0, alpha: 1)

        let config = WKWebViewConfiguration()
        config.allowsInlineMediaPlayback = true
        // The server sets its own session cookie behind the PIN door; a shared store means she
        // answers once, here or in Safari, and the app keeps getting in.
        config.websiteDataStore = .default()

        web = WKWebView(frame: .zero, configuration: config)
        web.navigationDelegate = self
        web.allowsBackForwardNavigationGestures = true
        web.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(web)

        bar = UIToolbar()
        bar.barStyle = .black
        bar.isTranslucent = false
        bar.items = [
            UIBarButtonItem(image: UIImage(systemName: "arrow.left"), style: .plain,
                            target: web, action: #selector(WKWebView.goBack)),
            UIBarButtonItem(image: UIImage(systemName: "arrow.right"), style: .plain,
                            target: web, action: #selector(WKWebView.goForward)),
            UIBarButtonItem(image: UIImage(systemName: "arrow.clockwise"), style: .plain,
                            target: self, action: #selector(reload)),
            UIBarButtonItem(barButtonSystemItem: .flexibleSpace, target: nil, action: nil),
            UIBarButtonItem(image: UIImage(systemName: "desktopcomputer"), style: .plain,
                            target: self, action: #selector(editAddress)),
        ]
        bar.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(bar)

        NSLayoutConstraint.activate([
            bar.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            bar.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            bar.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor),
            web.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            web.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            web.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            web.bottomAnchor.constraint(equalTo: bar.topAnchor),
        ])

        if startURL == nil { askForAddress(first: true) } else { open() }
    }

    private func open() {
        guard let url = startURL else { return askForAddress(first: true) }
        web.load(URLRequest(url: url))
    }

    @objc private func reload() { open() }

    @objc private func editAddress() { askForAddress(first: false) }

    /// The whole configuration surface: one text field. Prefilled with what is saved, because the
    /// usual reason to open it is that the router handed the laptop a new address.
    private func askForAddress(first: Bool) {
        let alert = UIAlertController(
            title: first ? "Where is your laptop?" : "Server address",
            message: "Type the address the Phone page shows on the laptop, for example "
                   + "the wifi address followed by :8756. Nothing here talks to the internet.",
            preferredStyle: .alert)
        alert.addTextField { field in
            field.text = UserDefaults.standard.string(forKey: Self.defaultsKey)
            field.autocorrectionType = .no
            field.keyboardType = .URL
            field.placeholder = "192.168.1.20:8756"
        }
        let save = UIAlertAction(title: "Connect", style: .default) { [weak self] _ in
            guard var text = alert.textFields?.first?.text, !text.isEmpty else { return }
            if !text.contains("://") { text = "http://" + text }
            guard let url = URL(string: text) else { return }
            UserDefaults.standard.set(url.absoluteString, forKey: Self.defaultsKey)
            self?.web.load(URLRequest(url: url))
        }
        alert.addAction(save)
        if !first { alert.addAction(UIAlertAction(title: "Cancel", style: .cancel)) }
        present(alert, animated: true)
    }

    // MARK: WKNavigationDelegate

    /// The one screen that has to be honest about the laptop being asleep: a web view that cannot
    /// reach the address says so in words, and offers the two fixes that actually exist.
    ///
    /// The label is `withError`, which is what WebKit's own header spells it as - writing `with`
    /// compiles, quietly stops being the delegate method, and leaves this screen never arriving.
    /// Xcode 26.6 printed the requirement in full when it rejected the first version of this line.
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!,
                 withError error: any Error) {
        let code = (error as NSError).code
        // Names taken from Apple's own URLError.Code page on 2026-11-15, because the first attempt at
        // this list guessed one that does not exist. Each of these is a way the laptop specifically
        // failed to answer; anything else is a page-level error the web view can show on its own.
        let unanswered: [URLError.Code] = [.cannotConnectToHost, .cannotFindHost, .dnsLookupFailed,
                                           .timedOut, .networkConnectionLost, .notConnectedToInternet]
        guard unanswered.contains(where: { $0.rawValue == code }) else { return }
        let alert = UIAlertController(
            title: "The laptop did not answer",
            message: "This app is a window onto your computer, so it needs the computer awake, on "
                   + "the same wifi, and running. If it is, the address changed - tap the "
                   + "computer button to type the new one.",
            preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "Change address", style: .default) { [weak self] _ in
            self?.askForAddress(first: false)
        })
        alert.addAction(UIAlertAction(title: "Try again", style: .default) { [weak self] _ in
            self?.open()
        })
        alert.addAction(UIAlertAction(title: "Stop", style: .cancel))
        present(alert, animated: true)
    }
}

@main
final class AppDelegate: UIResponder, UIApplicationDelegate {
    var window: UIWindow?

    func application(_ application: UIApplication,
                     didFinishLaunching options: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        let window = UIWindow(frame: UIScreen.main.bounds)
        window.rootViewController = ServerViewController()
        window.makeKeyAndVisible()
        self.window = window
        return true
    }
}
