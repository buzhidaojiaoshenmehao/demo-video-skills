# Demo Video Skills

两个从产品演示视频制作中提炼的 Codex skills，覆盖录屏剪辑、精准构图、本地旁白、字幕对齐与可恢复交付。

| Skill | 适用任务 | 配套能力 |
| --- | --- | --- |
| [product-demo-edit](skills/product-demo-edit/SKILL.md) | 项目作品录屏、比赛演示、按时间点修改放大/全景 | 抽取复核帧、联系表、解码与导出规格检查 |
| [local-tts-narration](skills/local-tts-narration/SKILL.md) | 替换录制原声、固定音色旁白、本地 IndexTTS | 分段缓存续做、强制字幕对齐、完整性检查 |

剪辑 skill 延续所选编辑器；Remotion、剪映等仍使用各自工具。本仓库提供工作方法和确定性辅助脚本，不是独立视频编辑器。

## 安装

下载或克隆本仓库，将 `skills/` 下需要的目录复制到个人 Codex skills 目录（通常为 `~/.codex/skills/`）。如果已有同名 skill，先比较内容再更新，不要直接覆盖。

可以在对话中使用：

```text
使用 $product-demo-edit，把我的录屏做成 4 分钟的演示，重点展示操作闭环。
使用 $product-demo-edit，调整 42–49 秒构图，并验证最终文件小于 50 MB。
使用 $local-tts-narration，沿用已确认音色生成旁白，中断后只续做缺失片段。
```

## 依赖与运行

- Python 3.9+。
- 视频复核：PATH 中提供 ffmpeg 和 ffprobe；联系表额外需要 Pillow。
- 语音生成：使用已安装的 IndexTTS 2.5 Python 环境与本地模型。
- 字幕对齐：stable-ts、其兼容的 PyTorch/Whisper 环境与本地 Whisper 权重。

每个脚本提供 `--help`。具体命令、清单格式、适配边界和验收步骤见对应 `SKILL.md` 及引用文档。没有自动下载模型、调用云端配音或上传素材的逻辑。

## 检查

```bash
python3 -m unittest discover -s tests -v
```

测试生成临时合成视频，验证导出规格、超限失败、边界抽帧，以及配音缓存失效和字幕时间检查。它们不代替真实模型试跑或成片观看听审。

仓库仅包含通用说明、代码与虚构示例，不含项目录屏、个人声音、业务数据或本机绝对路径。

## License

MIT，适用于本仓库的原创说明和辅助代码。IndexTTS、模型权重、参考声音及其他依赖各自遵循其许可证。
