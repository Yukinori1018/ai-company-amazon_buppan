# GitHub Template Repository 化 手順

このリポジトリを GitHub の **Template repository** として公開し、"Use this template" ボタンから子会社リポジトリを量産できるようにする手順です。

所要時間：5分。

## Step 1: Template repository 機能を有効化

1. GitHub でこのリポのページを開く
2. **Settings** タブを開く
3. **General** セクション（左メニュー最上部）
4. ページ中段あたりにある **Template repository** チェックボックスをオンにする
   - チェックすると**即座に保存**されます（保存ボタンはありません）
5. リポ名のリンクをクリックしてトップページに戻り、`<> Code` ボタンの隣に緑色の **Use this template** ボタンが表示されていれば成功

## Step 2: リポジトリの説明と Topics を整える（推奨）

リポトップの右ペイン **About** 横の歯車から：

- **Description:** 例：「ローカルフォルダで動く AI 仮想会社の親テンプレート（秘書・経理・法務・庶務・コンテンツ制作の5エージェント構成、Notion カンバン連携）」
- **Topics:** `ai-agent`, `claude-code`, `template`, `notion`, `mcp` などを付ける

検索性とプロジェクトの第一印象が大幅に上がります。

## Step 3: main ブランチ保護の設定（推奨）

AI エージェントが直接 `main` を破壊しないようにする保護です。

1. **Settings** → **Branches**
2. **Add branch ruleset**（または旧 UI なら **Add rule**）
3. Branch name pattern: `main`
4. 以下を有効化：
   - **Require a pull request before merging**
     - Required approvals: 0（自分1人運用なら）／1（複数人なら）
   - **Block force pushes**
   - **Restrict deletions**
5. Save

これで `main` への直 push と force push が拒否され、必ず PR 経由になります。AI が事故的に main を吹き飛ばすリスクが下がります。

> 一人運用で「Required approvals: 0」にする場合でも、PR 経由になるだけで履歴と差分が必ず可視化されるメリットがあります。

## Step 4: Secret push protection の有効化（推奨）

`.mcp.json` の誤コミットを GitHub 側でブロックします。

1. **Settings** → **Code security and analysis**
2. **Push protection** → Enable（無料／パブリックリポなら有効化推奨）

`secret_xxx` のような Notion トークンらしき文字列が push されようとすると、GitHub が拒否してくれます。

## Step 5: 自分でテンプレート化テスト

公開直後に**自分で** "Use this template" を1回試して、子会社リポを作ってみるのが推奨。

1. リポトップの **Use this template → Create a new repository**
2. 新リポ名は捨て用（例：`ai-company-template-test`）
3. clone して、README の「子会社を作る手順 Step 1〜5」が通るかを実機検証
4. 通ったら捨て用リポは削除

これで README 通りに動くことが確認できます。

---

## 参考リンク

- [GitHub Docs: Creating a template repository](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-template-repository)
- [GitHub Docs: About protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [GitHub Docs: About push protection](https://docs.github.com/en/code-security/secret-scanning/push-protection-for-repositories-and-organizations)
