# 00_inbox 队友投递区 📥

这个文件夹是给队友临时放题目和附件的入口。队友不用判断文件应该进 `00_official/`、`01_problem/` 还是 `02_raw_data/`，先全部放到这里即可。

## 推荐放法

可以直接把比赛材料按下面方式放进来：

```text
00_inbox/
├── problem.pdf
├── official_notice.pdf
├── attachments/
│   ├── 附件1.xlsx
│   ├── 附件2.csv
│   └── 说明.docx
└── notes.txt
```

如果队友不会分类，也可以直接把一个完整附件文件夹拖进来。

## 然后告诉 Codex

材料放好后，在对话里说：

```text
题目和附件已经放到 00_inbox，请整理到正式目录。
```

Codex 会做这些事：

- 识别题目 PDF、官方通知、附件数据和说明文件；
- 把官方规则整理到 `00_official/`；
- 把题目原文和题面说明整理到 `01_problem/`；
- 把原始数据和附件整理到 `02_raw_data/`；
- 计算 SHA256；
- 更新 `02_raw_data/data_manifest.csv` 和 `02_raw_data/checksums.sha256`；
- 不修改原始数据内容。

## 注意

- `00_inbox/` 里的真实题目、数据和附件不会上传 GitHub。
- 大文件必须放在 E 盘项目目录内，不要放 C 盘。
- 整理完成后，`00_inbox/` 可以清空，只保留这个 README。
