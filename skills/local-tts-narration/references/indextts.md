# IndexTTS 本地适配

官方来源：[IndexTTS](https://github.com/index-tts/index-tts)、[IndexTTS 2.5 模型](https://huggingface.co/IndexTeam/IndexTTS-2.5)。先检查已有安装及其版本，不把「最新版本」视为稳定接口。仓库不包含模型或参考音频。

本适配脚本依赖现有 IndexTTS 2.5 Python 环境，以及 PATH 中的 ffmpeg、ffprobe。使用模型环境的 Python 运行；不自动创建环境或下载模型。FP32 的 MPS 运行路径曾在 Apple Silicon 上验证；BF16 在一次环境中出现 NaN，这只说明需要逐环境试跑，不代表所有设备不支持。

## 生成清单

相对路径以清单所在目录为基准。模型标识填实际模型版本/快照与代码提交，用于缓存失效；改变权重文件后也要更新该标识。不要在清单内放凭证。

```json
{
  "model_id": "IndexTTS-2.5/<model-snapshot>/<code-commit>",
  "reference": "reference/approved.wav",
  "reference_note": "用户已确认的参考声音，来源及用途记录在项目本地",
  "seed": 1234,
  "init": {"device": "cpu", "use_bf16": false, "use_cuda_kernel": false, "use_qwen_emo": false},
  "inference": {"lang": "ZH", "use_random": false, "num_beams": 1},
  "segments": [
    {"id": "intro", "text": "这里演示如何保存一条知识。", "slot_seconds": 8},
    {"id": "result", "text": "保存后，可以查看处理结果。", "slot_seconds": 8}
  ]
}
```

`slot_seconds` 只用于报告是否超长，不会截断音频或自动改变语速。不要通过让模型读得极快来满足固定画面时长。

```bash
python scripts/generate_voice.py voice.json --source /path/to/index-tts \
  --model-dir /path/to/checkpoints --out work/voice --plan
python scripts/generate_voice.py voice.json --source /path/to/index-tts \
  --model-dir /path/to/checkpoints --out work/voice --ids intro
python scripts/generate_voice.py voice.json --source /path/to/index-tts \
  --model-dir /path/to/checkpoints --out work/voice
```

`--plan` 验证输入及缓存，不加载模型；它不会证明当前机器推理能成功。先实际生成一个片段。失败不生成成功记录；已有通过的片段仍可复用。

缓存键包含脚本自身、IndexTTS Python 源码、config.yaml、模型标识、参考音频和参数。脚本不反复哈希数 GB 权重，因此 `model_id` 必须跟随权重变化；元数据同时记录模型目录内文件的大小与修改时间。最终音频、哈希与时长写入每段 `meta.json`，`run.json` 记录本次所选片段，不把选段运行当成全部完成。
