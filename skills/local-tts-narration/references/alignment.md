# 文稿对齐、响度与时间线

本地对齐使用 [stable-ts](https://github.com/jianfch/stable-ts) 的 `model.align`。脚本读取本地 Whisper `.pt` 权重，不自动选用在线模型。对齐应在最终音频版本上完成；变速、剪头尾或重新配音后必须重新对齐。

## 清单

```json
{
  "language": "zh",
  "segments": [
    {"id": "intro", "audio": "finished/intro.wav", "text": "这里演示如何保存一条知识。", "start_seconds": 12.4, "slot_seconds": 8},
    {"id": "result", "audio": "finished/result.wav", "text": "保存后，可以查看处理结果。", "start_seconds": 21, "slot_seconds": 8}
  ]
}
```

`start_seconds` 是音频在成片中的实际起点，已经包含镜头起点及旁白延迟；`slot_seconds` 是从该起点计算的可用时长。音频里已有的静音属于音频时间，不再重复加偏移。

```bash
python scripts/align_narration.py timeline.json --model /path/to/base.pt \
  --out work/alignment-v1 --device cpu
```

脚本按句号、逗号、分号、问号和感叹号提示分句，顿号不切断词组。缓存含音频哈希、文稿、Whisper 权重哈希和 stable-ts 版本。输出保持文稿（比较时只忽略空白），检查正时长、非重叠、镜头边界和音频边界。全局排序后再输出 JSON 与 SRT；有片段未完成或不合格则失败，保留已完成的对齐缓存。

## 对齐前后检查

1. 先听原始生成音频，修复漏句、重复、误读。强制对齐能给错误发音分配时间，不能证明朗读正确。
2. 需要统一音量时保留 raw，另生成 finished。例如 `loudnorm=I=-17:TP=-2:LRA=7` 可作为项目起点，不是所有视频的标准。严格响度交付使用测量后的两遍处理，并复测混音。
3. 需要变速时记录 `atempo`，核对语感；对处理后的文件重新对齐更易避免时间换算遗漏。
4. SRT 时间以毫秒计，检查相邻字幕取整后仍不重叠。编辑器以帧计时则额外记录 fps 与舍入规则。
5. 检查最终编码视频的实际听感与语句落点；对齐 JSON 通过不代表背景音乐、字幕版式和剪辑节奏通过。
