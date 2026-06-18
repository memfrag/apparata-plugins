import AppKit

// Renders the icon macOS displays for an app bundle to a PNG at a given size.
// Works for every .app — including bundles with no CFBundleIconFile — because
// NSWorkspace always returns the effective icon.
guard CommandLine.arguments.count >= 3 else {
    fputs("Usage: extract_icon <app-path> <output-png> [size]\n", stderr)
    exit(1)
}

let appPath = CommandLine.arguments[1]
let outPath = CommandLine.arguments[2]
let size = CommandLine.arguments.count >= 4 ? Double(CommandLine.arguments[3]) ?? 128 : 128

let icon = NSWorkspace.shared.icon(forFile: appPath)
let targetSize = NSSize(width: size, height: size)

let newImage = NSImage(size: targetSize)
newImage.lockFocus()
icon.draw(in: NSRect(origin: .zero, size: targetSize),
          from: NSRect(origin: .zero, size: icon.size),
          operation: .sourceOver, fraction: 1.0)
newImage.unlockFocus()

guard let tiff = newImage.tiffRepresentation,
      let bitmap = NSBitmapImageRep(data: tiff),
      let png = bitmap.representation(using: .png, properties: [:]) else {
    fputs("Failed to render icon for \(appPath)\n", stderr)
    exit(1)
}

try! png.write(to: URL(fileURLWithPath: outPath))
