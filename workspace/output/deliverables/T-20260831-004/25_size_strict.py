# -*- coding: utf-8 -*-
"""規模判定 v3。

v2 の反省（並行実装のラベル200社で実測）:
  手判定で「大企業」と断じた187社のうち、アストロプロダクツ・城東テクノ・安永・
  BIALETTI は本命だった。**手判定を除外ゲートに使うと本命を殺す。**

v3 の方針:
  - 除外するのは「誰でも知っている大企業/上場グループ/グローバル本社」だけ（LARGE_CERTAIN）
  - それ以外は **規模未確認** としてリストに残し、列で警告する
  - 300人の線を引くのは gBizINFO の仕事。手判定はその代役をしない
"""
import re

LARGE_CERTAIN = re.compile(
    r"^(?:.*?)(?:"
    # 国内・グローバルの誰でも知る大企業
    r"三菱電機|東レ|日立|東芝|NEC|キヤノン|キャノン|エプソン|シャープ|富士フイルム|パナソニック|"
    r"ソニー|SONY|TOYOTA|トヨタ|Honda|ホンダ|Kawasaki|カワサキ|ブリヂストン|BRIDGESTONE|DUNLOP|"
    r"Suntory|サントリー|アシックス|asics|シマノ|SHIMANO|NORTH FACE|NIKE|ナイキ|adidas|"
    r"ヤマハ|YAMAHA|CASIO|カシオ|CITIZEN|Seiko|SEIKO|Makita|マキタ|山善|YAMAZEN|コクヨ|KOKUYO|"
    r"アイリスオーヤマ|IRIS OHYAMA|エレコム|ELECOM|バッファロー|BUFFALO|アイオーデータ|KIOXIA|"
    r"パイロットコーポレーション|3M|スリーエム|リンナイ|Rinnai|美和ロック|Miwalock|ニチアス|"
    r"三井化学|四国化成|旭化成|三ツ星ベルト|太平洋工業|パール金属|レック\(LEC\)|シモジマ|"
    r"サーモス|THERMOS|ホーチキ|Hochiki|ニチバン|NICHIBAN|セメダイン|Cemedine|ハスクバーナ|"
    # 玩具・出版・キャラクター大手
    r"BANDAI|バンダイ|タカラトミー|TAKARA TOMY|LEGO|レゴ|MATTEL|マテル|HASBRO|ハズブロ|"
    r"サンリオ|SANRIO|タミヤ|TAMIYA|グッドスマイル|GOOD SMILE|"
    # 外資・グローバルブランド
    r"KODAK|PHILIPS|SanDisk|SEAGATE|シーゲイト|Western Digital|ウエスタンデジタル|SAMSUNG|サムスン|"
    r"Logitech|Logicool|Razer|レイザー|NETGEAR|Braun|KÄRCHER|LEICA|ライカ|Sennheiser|ゼンハイザー|"
    r"Fender|フェンダー|KORG|コルグ|Wacom|ワコム|JBL|Audio Technica|オーディオテクニカ|"
    r"Zebra Technologies|Smith & Nephew|MAHLE|Continental|コンチネンタル|Coleman|コールマン|"
    r"Jabra|ジャブラ|Ergobaby|エルゴベビー|OM SYSTEM|オリンパス|Verbatim|バーベイタム|"
    r"シュナイダーエレクトリック|StarTech|ベンキュー|BenQ|Silicon Power|"
    # 大手の商品ブランド（実体は大企業）
    r"ロイヤルカナン|ピュリナ|チャオ \(CIAO\)|エリエール|クイックル|ワイドハイター|NANOXone|"
    r"アース渦巻香|ラウンドアップ|シンジェンタ|Laundrin|ランドリン|TIGORA|ティゴラ|"
    r"Eufy|ユーフィ|iface|SHOKZ|HOKA|NEW ERA|ニューエラ|Mont-bell|モンベル|Tile|タイル\(Tile\)|"
    r"THRIVE|スライヴ|MITSUBA|ミツバサンコーワ|ケンウッド|KENWOOD|ビクター|VICTOR|"
    r"シー・エフ・デー販売|本間ゴルフ|MIKIHOUSE|ミキハウス|ドウシシャ|DOSHISHA|山崎実業|Yamazaki|"
    r"TANITA|Omron|オムロン|マスプロ電工|DXアンテナ|海洋堂|KAIYODO|東京マルイ"
    r")",
    re.I)

def is_large_certain(name: str) -> bool:
    return bool(LARGE_CERTAIN.search(name or ""))
