// The launcher's background picture (HookLink X3): the default one the build packed (build_ipa.sh DM_LAUNCHER_BG → dm/launcher_background.jpg), or one of the player's own photos
// (Documents/launcher_backgrounds, added from Photos or Files), with how much it is darkened for the text over it and which part of a wide photo stays in view. Without either,
// a drawn sky. After kid-with-sword-remake's LauncherBackgroundStore (one picture), with several photos and the picker of HookLink's mock-up C3
import SwiftUI
import UIKit
import PhotosUI
import UniformTypeIdentifiers

/// HookLink's fresh look: frosted dark glass, white text, one gold accent
enum HLX {
    static let gold = Color(red: 0.925, green: 0.780, blue: 0.404)
    static let onGold = Color(red: 0.165, green: 0.122, blue: 0.020)
    static let glass = Color(red: 0.055, green: 0.063, blue: 0.086)
    static let line = Color.white.opacity(0.15)
    static let dim = Color.white.opacity(0.62)
    static let faint = Color.white.opacity(0.45)
    static func serif(_ s: CGFloat) -> Font { .system(size: s, weight: .regular, design: .serif) }
    static func body(_ s: CGFloat, _ w: Font.Weight = .regular) -> Font { .system(size: s, weight: w) }
}

extension View {
    /// A frosted dark glass card: the system's blur under a dark tint, a hairline edge
    func hlGlass(_ radius: CGFloat, tint: Double = 0.45) -> some View {
        self.background {
            RoundedRectangle(cornerRadius: radius, style: .continuous).fill(.ultraThinMaterial)
                .overlay(RoundedRectangle(cornerRadius: radius, style: .continuous).fill(HLX.glass.opacity(tint)))
        }
        .overlay(RoundedRectangle(cornerRadius: radius, style: .continuous).stroke(HLX.line, lineWidth: 1))
        .environment(\.colorScheme, .dark)
    }
}

final class HLBackgrounds: ObservableObject {
    static let shared = HLBackgrounds()
    static let defaultID = "default"
    @Published private(set) var photos: [String] = []          // file names in the folder, newest first
    @Published var choice: String { didSet { UserDefaults.standard.set(choice, forKey: "hooklink.bg.choice"); load() } }
    @Published var darken: Double { didSet { UserDefaults.standard.set(darken, forKey: "hooklink.bg.darken") } }   // 0 to 0.7
    // Which part of the photo stays in view where the screen crops it, for each photo: 0 the top (or left), 1 the centre, 2 the bottom (or right). A photo less wide than the
    // screen is cropped at the top and bottom, a wider one at the sides. The default picture starts at the bottom: its figure and the castle stay whole beside the side panel
    @Published private var positions: [String: Int] { didSet { UserDefaults.standard.set(positions, forKey: "hooklink.bg.positions") } }
    var position: Int {
        get { positions[choice] ?? (choice == Self.defaultID ? 2 : 1) }
        set { positions[choice] = max(0, min(2, newValue)) }
    }
    /// Whether the current photo is cropped at the top and bottom on this screen (less wide than the screen), else at the sides
    var cropsVertically: Bool {
        guard let i = image, i.size.height > 0 else { return true }
        let b = UIScreen.main.bounds, screen = max(b.width, b.height) / max(min(b.width, b.height), 1)
        return i.size.width / i.size.height < screen
    }
    @Published private(set) var image: UIImage?
    @Published var message: String?

    private var folder: URL { FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("launcher_backgrounds", isDirectory: true) }
    /// The packed default: the running program's dm folder (main.m DM_APP_DM), else the app's
    static var packedDefault: URL? {
        let dm = ProcessInfo.processInfo.environment["DM_APP_DM"].map { URL(fileURLWithPath: $0) } ?? Bundle.main.resourceURL?.appendingPathComponent("dm")
        guard let u = dm?.appendingPathComponent("launcher_background.jpg"), FileManager.default.fileExists(atPath: u.path) else { return nil }
        return u
    }
    var hasDefault: Bool { Self.packedDefault != nil }

    private init() {
        let d = UserDefaults.standard
        choice = d.string(forKey: "hooklink.bg.choice") ?? Self.defaultID
        darken = d.object(forKey: "hooklink.bg.darken") as? Double ?? 0.2
        positions = d.dictionary(forKey: "hooklink.bg.positions") as? [String: Int] ?? [:]
        reload()
    }
    func reload() {
        let names = (try? FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: [.creationDateKey]))?
            .filter { ["jpg", "jpeg"].contains($0.pathExtension.lowercased()) }
            .sorted { ((try? $0.resourceValues(forKeys: [.creationDateKey]).creationDate) ?? .distantPast) > ((try? $1.resourceValues(forKeys: [.creationDateKey]).creationDate) ?? .distantPast) }
            .map(\.lastPathComponent) ?? []
        photos = names
        if choice != Self.defaultID && !names.contains(choice) { choice = Self.defaultID } else { load() }
    }
    func url(_ id: String) -> URL? { id == Self.defaultID ? Self.packedDefault : folder.appendingPathComponent(id) }
    private func load() {
        image = url(choice).flatMap { UIImage(contentsOfFile: $0.path) }
    }
    func thumbnail(_ id: String) -> UIImage? {
        guard let u = url(id), let src = CGImageSourceCreateWithURL(u as CFURL, nil),
              let cg = CGImageSourceCreateThumbnailAtIndex(src, 0, [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceThumbnailMaxPixelSize: 360, kCGImageSourceCreateThumbnailWithTransform: true] as CFDictionary) else { return nil }
        return UIImage(cgImage: cg)
    }
    /// A picked photo, at most 2400 px on its long side, as a JPEG (a 48 MP photo would take about 190 MB of memory each time the launcher draws it); chosen at once
    @discardableResult func add(_ data: Data) -> Bool {
        guard let img = UIImage(data: data) else { message = "That file is not a picture this iPhone can read."; return false }
        let s = img.size, k = min(1, 2400 / max(s.width, s.height, 1)), size = CGSize(width: (s.width * k).rounded(), height: (s.height * k).rounded())
        let format = UIGraphicsImageRendererFormat(); format.scale = 1
        let out = UIGraphicsImageRenderer(size: size, format: format).image { _ in img.draw(in: CGRect(origin: .zero, size: size)) }
        guard let jpg = out.jpegData(compressionQuality: 0.88) else { message = "The picture could not be saved."; return false }
        do {
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            let name = "bg-\(UUID().uuidString.prefix(8)).jpg"
            try jpg.write(to: folder.appendingPathComponent(name), options: .atomic)
            fputs("launcher: background picture added (\(Int(size.width))x\(Int(size.height)))\n", stderr)
            message = nil; reload(); choice = name; return true
        } catch { message = "The picture could not be saved: \(error.localizedDescription)"; return false }
    }
    func remove(_ id: String) {
        guard id != Self.defaultID else { return }
        try? FileManager.default.removeItem(at: folder.appendingPathComponent(id)); reload()
    }
}

/// The picture filling the screen, darkened as the player set, with two soft shades that keep the side panel (left) and the Play button (bottom) readable; a drawn sky without one
struct HLBackdrop: View {
    @ObservedObject var bg: HLBackgrounds
    var body: some View {
        GeometryReader { g in
            ZStack {
                if let img = bg.image {
                    let vertical = img.size.width / max(img.size.height, 1) < g.size.width / max(g.size.height, 1)
                    Image(uiImage: img).resizable().scaledToFill()
                        .frame(width: g.size.width, height: g.size.height, alignment: (vertical ? [Alignment.top, .center, .bottom] : [Alignment.leading, .center, .trailing])[bg.position])
                        .clipped()
                } else {
                    LinearGradient(colors: [Color(red: 0.42, green: 0.62, blue: 0.82), Color(red: 0.62, green: 0.76, blue: 0.86), Color(red: 0.30, green: 0.42, blue: 0.24)], startPoint: .top, endPoint: .bottom)
                }
                Color.black.opacity(bg.darken)
                LinearGradient(colors: [Color.black.opacity(0.35), .clear], startPoint: .leading, endPoint: UnitPoint(x: 0.4, y: 0.5))
                LinearGradient(colors: [Color.black.opacity(0.3), .clear], startPoint: .bottom, endPoint: UnitPoint(x: 0.5, y: 0.7))
            }
            .frame(width: g.size.width, height: g.size.height)
        }
        .ignoresSafeArea()
        .accessibilityHidden(true)
    }
}

/// The background picker (the photo button at the top, or Extras › Background): the default and the player's photos, Add photo (Photos or Files), Darken for text, Position
struct HLBackgroundPicker: View {
    @ObservedObject var bg: HLBackgrounds
    let close: () -> Void
    @State private var photoItem: PhotosPickerItem?
    @State private var photosOpen = false
    @State private var filesOpen = false
    @State private var removing: String?

    private var ids: [String] { (bg.hasDefault ? [HLBackgrounds.defaultID] : []) + bg.photos }
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("Background").font(HLX.serif(22)).foregroundStyle(.white)
                Spacer()
                Button("Done", action: close).font(HLX.body(15, .semibold)).foregroundStyle(HLX.gold)
            }
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    ForEach(ids, id: \.self) { id in tile(id) }
                    Menu {
                        Button { photosOpen = true } label: { Label("Photo Library", systemImage: "photo.on.rectangle") }
                        Button { filesOpen = true } label: { Label("Files", systemImage: "folder") }
                    } label: {
                        VStack(spacing: 6) {
                            VStack(spacing: 4) { Image(systemName: "photo.badge.plus").font(.system(size: 22)); Text("Add photo").font(HLX.body(12, .medium)) }
                                .foregroundStyle(.white).frame(width: 150, height: 90)
                                .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).strokeBorder(Color.white.opacity(0.35), style: StrokeStyle(lineWidth: 1.5, dash: [5, 4])))
                            Text("Photos or Files").font(HLX.body(11)).foregroundStyle(HLX.faint)
                        }
                    }
                }.padding(.vertical, 2)
            }
            if let m = bg.message { Text(m).font(HLX.body(12)).foregroundStyle(HLX.gold) }
            Rectangle().fill(HLX.line).frame(height: 1)
            HStack(spacing: 14) {
                Text("Darken for text").font(HLX.body(13.5)).foregroundStyle(.white).frame(width: 130, alignment: .leading)
                Slider(value: $bg.darken, in: 0...0.7).tint(HLX.gold)
                Text("\(Int((bg.darken * 100).rounded())) %").font(HLX.body(12)).foregroundStyle(HLX.dim).monospacedDigit().frame(width: 44, alignment: .trailing)
            }
            HStack(spacing: 14) {
                Text("Position").font(HLX.body(13.5)).foregroundStyle(.white).frame(width: 130, alignment: .leading)
                Picker("Position", selection: Binding(get: { bg.position }, set: { bg.position = $0 })) {
                    let names = bg.cropsVertically ? ["Top", "Center", "Bottom"] : ["Left", "Center", "Right"]
                    ForEach(0..<3, id: \.self) { Text(names[$0]).tag($0) }
                }
                    .pickerStyle(.segmented).frame(maxWidth: 260)
                Spacer(minLength: 0)
            }
            Text("Touch and hold a photo to remove it.").font(HLX.body(11.5)).foregroundStyle(HLX.faint)
        }
        .padding(20)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(HLX.glass.ignoresSafeArea())
        .preferredColorScheme(.dark)
        .photosPicker(isPresented: $photosOpen, selection: $photoItem, matching: .images)
        .onChange(of: photoItem) { _, item in
            guard let item else { return }
            Task { if let d = try? await item.loadTransferable(type: Data.self) { await MainActor.run { bg.add(d) } } else { await MainActor.run { bg.message = "That photo could not be read." } }; await MainActor.run { photoItem = nil } }
        }
        .fileImporter(isPresented: $filesOpen, allowedContentTypes: [.image], allowsMultipleSelection: false) { r in
            if case .success(let urls) = r, let u = urls.first {
                let ok = u.startAccessingSecurityScopedResource(); defer { if ok { u.stopAccessingSecurityScopedResource() } }
                if let d = try? Data(contentsOf: u) { bg.add(d) } else { bg.message = "That file could not be read." }
            }
        }
        .confirmationDialog("Remove this photo?", isPresented: Binding(get: { removing != nil }, set: { if !$0 { removing = nil } }), titleVisibility: .visible) {
            Button("Remove", role: .destructive) { if let r = removing { bg.remove(r) }; removing = nil }
        }
    }
    private func tile(_ id: String) -> some View {
        let on = bg.choice == id
        return Button { bg.choice = id; UISelectionFeedbackGenerator().selectionChanged() } label: {
            VStack(alignment: .leading, spacing: 6) {
                ZStack(alignment: .topTrailing) {
                    Group {
                        if let t = bg.thumbnail(id) { Image(uiImage: t).resizable().scaledToFill() } else { HLX.glass }
                    }
                    .frame(width: 150, height: 90).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(on ? HLX.gold : HLX.line, lineWidth: on ? 2 : 1))
                    if on {
                        Image(systemName: "checkmark").font(.system(size: 11, weight: .bold)).foregroundStyle(HLX.onGold)
                            .frame(width: 20, height: 20).background(HLX.gold, in: Circle()).padding(6)
                    }
                }
                Text(id == HLBackgrounds.defaultID ? "HookLink default" : "Your photo").font(HLX.body(12)).foregroundStyle(on ? .white : HLX.dim)
            }
        }
        .buttonStyle(.plain)
        .contextMenu { if id != HLBackgrounds.defaultID { Button("Remove", role: .destructive) { removing = id } } }
        .accessibilityLabel(id == HLBackgrounds.defaultID ? "HookLink default background" : "Your photo")
        .accessibilityAddTraits(on ? .isSelected : [])
    }
}
