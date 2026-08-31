// 51_ocr.swift — macOS Vision framework で画像を日本語OCRするCLI
//
// なぜ自作したか: この Mac に tesseract が無く、macOS 標準の Vision framework が
// 日本語スライドに対して十分な精度を出したため。外部依存ゼロで済む。
//
// ビルド: swiftc -O -o ocr 51_ocr.swift     （初回は2〜3分かかる）
// 使い方: ./ocr 画像1.jpg 画像2.jpg ...
// 出力:   1行1件の TSV「ファイル名<TAB>認識テキスト」。改行は \n にエスケープ。
//
// 1プロセスで複数枚を渡すこと。Vision のモデル初期化に約10秒かかるので、
// 1枚ずつ起動すると桁違いに遅くなる（実測 1枚起動24秒 / 30枚一括31秒）。
import Foundation
import Vision
import AppKit

func ocr(_ path: String) -> String {
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return "" }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.recognitionLanguages = ["ja-JP", "en-US"]
    req.usesLanguageCorrection = false   // 「50,000」等の数字を言語補正で壊さないため
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    do { try handler.perform([req]) } catch { return "" }
    guard let obs = req.results else { return "" }
    return obs.compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
}

for path in CommandLine.arguments.dropFirst() {
    let text = ocr(path)
        .replacingOccurrences(of: "\n", with: "\\n")
        .replacingOccurrences(of: "\t", with: " ")
    print("\((path as NSString).lastPathComponent)\t\(text)")
    fflush(stdout)
}
