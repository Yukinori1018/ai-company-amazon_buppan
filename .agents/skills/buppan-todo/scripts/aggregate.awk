#!/usr/bin/awk -f
#
# 01_master-todo.md を読んで、済 / 着手中 / 未着手 を数える。
#
#   awk -f aggregate.awk 01_master-todo.md
#
# 数えるのを人間（や LLM）がやると必ずズレます。ここが唯一の集計元で、
# A章のサマリ表も 03_process-board.html の数字も、全部この出力から作ります。
#
# 出力は JSON。
#   {"mid":[{"id":"1-1","title":"…","done":3,"doing":2,"todo":1}, …],
#    "major":[{"no":"1","title":"…","mids":6,"done":10,"doing":10,"todo":11}, …],
#    "total":{"done":49,"doing":43,"todo":116,"items":208,"mids":42,"majors":8}}

function jesc(s) { gsub(/\\/, "\\\\", s); gsub(/"/, "\\\"", s); return s }

BEGIN {
    nmid = 0; nmaj = 0
    tdone = 0; tdoing = 0; ttodo = 0
}

# 大項目: "## 1. 開業・法務・アカウント登録（中項目6 / 小項目31）"
/^## [1-8]\. / {
    line = substr($0, 4)
    split(line, a, ". ")
    nmaj++
    maj_no[nmaj] = a[1]
    t = substr(line, length(a[1]) + 3)
    sub(/（.*$/, "", t)
    maj_title[nmaj] = t
    maj_done[nmaj] = 0; maj_doing[nmaj] = 0; maj_todo[nmaj] = 0; maj_mids[nmaj] = 0
    cur_maj = nmaj
    cur_mid = 0
    next
}

# 大項目の外（A章・C章・D章）のチェックボックスは集計に入れない
/^## / { cur_maj = 0; cur_mid = 0; next }

# 中項目: "### 1-1. 事業体・税務の届出"
/^### [1-8]-[0-9]+\. / {
    if (cur_maj == 0) next
    line = substr($0, 5)
    split(line, a, ". ")
    nmid++
    mid_id[nmid] = a[1]
    mid_title[nmid] = substr(line, length(a[1]) + 3)
    mid_done[nmid] = 0; mid_doing[nmid] = 0; mid_todo[nmid] = 0
    cur_mid = nmid
    maj_mids[cur_maj]++
    next
}

# 小項目
/^- \[[x~ ]\] / {
    if (cur_mid == 0) next
    m = substr($0, 4, 1)
    if (m == "x")      { mid_done[cur_mid]++;  maj_done[cur_maj]++;  tdone++ }
    else if (m == "~") { mid_doing[cur_mid]++; maj_doing[cur_maj]++; tdoing++ }
    else               { mid_todo[cur_mid]++;  maj_todo[cur_maj]++;  ttodo++ }
}

END {
    printf "{\n  \"mid\": [\n"
    for (i = 1; i <= nmid; i++) {
        printf "    {\"id\":\"%s\",\"title\":\"%s\",\"done\":%d,\"doing\":%d,\"todo\":%d}%s\n",
            mid_id[i], jesc(mid_title[i]), mid_done[i], mid_doing[i], mid_todo[i],
            (i < nmid ? "," : "")
    }
    printf "  ],\n  \"major\": [\n"
    for (i = 1; i <= nmaj; i++) {
        printf "    {\"no\":\"%s\",\"title\":\"%s\",\"mids\":%d,\"done\":%d,\"doing\":%d,\"todo\":%d}%s\n",
            maj_no[i], jesc(maj_title[i]), maj_mids[i], maj_done[i], maj_doing[i], maj_todo[i],
            (i < nmaj ? "," : "")
    }
    printf "  ],\n  \"total\": {\"done\":%d,\"doing\":%d,\"todo\":%d,\"items\":%d,\"mids\":%d,\"majors\":%d}\n}\n",
        tdone, tdoing, ttodo, tdone + tdoing + ttodo, nmid, nmaj
}
