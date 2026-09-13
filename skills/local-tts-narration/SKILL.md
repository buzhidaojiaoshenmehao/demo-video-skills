---
name: local-tts-narration
description: Produce consistent narration with locally installed IndexTTS using an approved reference voice, resumable segment generation, and exact-script subtitle alignment. Use for replacing guide audio or generating demo narration locally; do not assume cloud TTS or a particular voice is wanted.
---

# 本地 TTS 旁白制作

把已确认文稿变成音色一致、可修改、能续做的分段音频；再用文稿对齐字幕。

## 音色与文稿

- 先检查项目里已批准的音色、参考声音来源和样音。认可过的参考可以沿用，无须每次修订重新确认。
- 没有参考时，按用户偏好寻找可用于本次用途的参考，制作短样音再定稿。性别、沉稳程度和语言是项目选择，不默认所有任务使用同一声音。
- 演示原声可用于理解操作，成片旁白应对应真实画面，不能把口误、等待时间和无关对话全部照搬。
- 将文稿分成具有稳定 ID 的片段，记录对应镜头起点、可用时长与发音备注。先试短句、术语和长句，再批量生成。

## 本地生成与续做

读 [indextts.md](references/indextts.md) 检查本地模型/API和清单格式，再使用 [generate_voice.py](scripts/generate_voice.py)。脚本适配 `indextts.infer_v2_5.IndexTTS2`，其他版本需先核对本地接口。

- 用同一参考、模型版本和生成配置维持音色；不把种子当作跨硬件完全一致的保证。
- 缓存由文本、参考哈希、模型标识、代码内容和生成参数共同决定。文件存在不代表可复用，还需核对元数据、输出哈希和音频有效性。
- 输出按内容键分目录，成功片段独立落盘。中断后只继续缺失或失效的片段；不要覆盖此前通过的音频。
- 精度/设备必须记录。若出现 NaN 或设备算子错误，保留日志并针对该环境试 FP32 或 CPU；不要无限重试同一失败配置。
- 所选本地工作流不自动转云服务。模型首次加载可能仍下载缺失依赖；需要离线时先备齐并验证本地缓存。

## 对齐字幕与成片

读 [alignment.md](references/alignment.md)，使用 [align_narration.py](scripts/align_narration.py) 对已完成的最终旁白文件做本地强制对齐。

- 字幕内容以已确认文稿为准，ASR 只用于发现漏词、重复和读音问题，不自动改稿。
- 不按字数平均分配字幕时间。用真实发声边界对齐，并计入镜头起点、音频偏移、变速与裁剪。
- 放不进镜头时，优先缩短稿件、调整停顿或延长镜头。不要默认强行加速；允许轻微变速时记录速度并重新对齐最终音频。
- 听审句尾、呼吸、长停顿与专业词，确认每段音量一致。响度目标按交付环境选择，混入背景音乐后再测成片。
- 对齐脚本只在全部片段通过时输出全片 SRT，不把部分生成误称为全片完成。机检通过仍要看片听审。

交付分段音频、文稿、SRT、生成配置和继续点。参考声音和本地路径留在项目中；分享 skill 时只带通用脚本及合成示例。
