# Third-party notices and model-use conditions

LessonVoice application source is GPL-3.0; that license does not relicense external model weights, tokenizer assets or their outputs. No model weights, cloned personal voices or paid assets are bundled in the repository. Downloading and using dependencies remains subject to their own terms.

## OmniVoice

The OmniVoice code is Apache-2.0 ([official source](https://github.com/k2-fsa/OmniVoice), [license copy](licenses/omnivoice-apache-2.0.txt)). The installed package is `omnivoice==0.2.1`; see `requirements-lock.txt` for the complete pinned Python environment and each distribution's own notices.

The separately downloaded pretrained model revision is `c5fdb5ccb189668d56333f77ba2629f4cd7535f4`. Its [official model README](https://huggingface.co/k2-fsa/OmniVoice/blob/c5fdb5ccb189668d56333f77ba2629f4cd7535f4/README.md) states that pretrained weights are **CC-BY-NC**, due to training-data constraints including Emilia. The upstream statement does not identify a CC license version; this project does not invent one. Treat this configured model as noncommercial: do not represent LessonVoice with these weights as commercially licensed. Keep the upstream README and all downloaded notices with the installation.

Model attribution: Han Zhu, Lingxuan Ye, Wei Kang, Zengwei Yao, Liyong Guo, Fangjun Kuang, Zhifeng Han, Weiji Zhuang, Long Lin and Daniel Povey, *OmniVoice: Towards Omnilingual Zero-Shot Text-to-Speech with Diffusion Language Models*, arXiv:2604.00688 (2026).

## Higgs audio tokenizer and Meta Llama 3

The model's audio tokenizer includes the BOSON HIGGS AUDIO 2 COMMUNITY LICENSE AGREEMENT dated June 20, 2025. Its exact local upstream license is copied to [licenses/boson-higgs-audio2.txt](licenses/boson-higgs-audio2.txt). [Official tokenizer source](https://huggingface.co/bosonai/higgs-audio-v2-tokenizer/blob/main/LICENSE). That agreement incorporates the Meta Llama 3 Community License and acceptable-use policy. Official copies are included as [Meta license](licenses/meta-llama3.txt) and [use policy](licenses/meta-llama3-use-policy.txt), fetched from [Meta's repository](https://github.com/meta-llama/llama3).

**Built with Higgs Materials licensed from Boson AI USA, Inc., Copyright Boson AI USA, Inc., All Rights Reserved and Meta Llama 3 licensed under the Meta Llama 3 Community License, Copyright Meta Platforms, Inc., All Right Reserved". based on Meta Llama 3**

Meta Llama 3 is licensed under the Meta Llama 3 Community License, Copyright © Meta Platforms, Inc. All Rights Reserved.

Boson Higgs Audio 2 is licensed under the Boson Community License, Copyright © Boson AI USA, Inc. All Rights Reserved.

The same notices are retained in [licenses/NOTICE.txt](licenses/NOTICE.txt). Preserve license copies and prominent attribution when distributing an application using these materials. Read the full terms: among other conditions, they include a Boson annual-active-user threshold, acceptable-use restrictions and restrictions on improving other models. The conditional naming provision requires “Higgs Audio 2” at the beginning of the name of an AI model or similar software created, modified, enhanced, trained, fine-tuned or improved using Higgs Materials. LessonVoice invokes the existing OmniVoice model without training or modifying it; that description is not a legal determination that any provision is inapplicable. Commercial or broader deployment requires an appropriate rights review, including the separate noncommercial weights restriction.

## Other components

Python, PyTorch, torchaudio, Transformers and other locked dependencies retain their upstream licenses. Their binaries and the `.neural-venv` environment are not committed. VoiceStudio is research inspiration only; no VoiceStudio code, branding, models or voice assets are copied. The earlier eSpeak prototype is superseded and is not a runtime fallback.
