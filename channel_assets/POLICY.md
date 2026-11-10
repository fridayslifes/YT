# FrameForge YouTube Monetization, Copyright & Synthetic Media Policy Ledger

**Last Verified**: 2026-11-10 UTC  
**Channel**: Cognitive Core (`UC6hwVBnsfvfUGxfZi2sFT3A`, `@CognitiveCoreOfficial`)

---

## 1. YouTube Partner Program (YPP) Eligibility Thresholds

* **Source**: [YouTube Partner Program overview & eligibility](https://support.google.com/youtube/answer/72851) (Retrieved 2026-11-10)
* **Tier 1 — Fan Funding & YouTube Shopping (Early Access)**:
  * **500 subscribers**
  * **3 valid public uploads** in the last 90 days
  * Either **3,000 valid public watch hours** in the past 12 months **OR** **3,000,000 valid public Shorts views** in the last 90 days.
* **Tier 2 — Watch Page & Shorts Feed Ad Revenue Sharing**:
  * **1,000 subscribers**
  * Either **4,000 valid public watch hours** in the past 12 months **OR** **10,000,000 valid public Shorts views** in the last 90 days.
* **Important Qualification Caveat**:
  * Ordinary Shorts feed watch time does **not** count toward the 3,000-hour or 4,000-hour long-form public watch-hour threshold. Only valid public long-form watch hours or valid public Shorts views (3M / 10M in 90 days) qualify.
  * **Correction to Unverified Claim**: Third-party rumors claiming YPP thresholds double to 8,000 watch hours or 20M Shorts views on February 1, 2027 are **not** supported by official Google Help documentation (`https://support.google.com/youtube/answer/72851`) and have been removed from repository guidance.

---

## 2. Inauthentic Content & Originality Policy (Formerly "Repetitious Content")

* **Source**: [YouTube channel monetization policies — Inauthentic content](https://support.google.com/youtube/answer/1311392) (Retrieved 2026-11-10)
* **Enforcement Rules**:
  1. Every project must be driven by a verified empirical dossier (`channel_assets/scientific_dossiers.json`) and reviewed release evidence (`channel_assets/evidence/*.json`) with printed-page locators.
  2. Template-recycled demos, mass-produced identical scripts, or static single-image slideshows are blocked by `tools/guard.py` and `tools/orchestrator/verifiers.py`.
  3. Every scene requires distinct topic-bound visual prompts (`Safe-Zone & Visual Uniqueness Gate`), and spoken numbers/mechanisms must match the verified dossier.

---

## 3. Altered or Synthetic Content Disclosure

* **Source**: [Disclosing use of altered or synthetic content](https://support.google.com/youtube/answer/14328491) (Retrieved 2026-11-10)
* **Enforcement Rules**:
  1. Every `project.json` and API upload body sets `containsSyntheticMedia: true` (`contains_synthetic_media: true`) and `selfDeclaredMadeForKids: false`.
  2. Generation prompts must **never** depict named living researchers (`named_subject` check in `verify_script`). Researcher names appear strictly in text overlays and citations.

---

## 4. Shorts Links & Packaging Compliance

* **Source**: [Links in YouTube Shorts](https://support.google.com/youtube/answer/13568600) (Retrieved 2026-11-10)
* **Enforcement Rules**:
  1. URLs in Shorts descriptions and comments are non-clickable. Shorts must use the YouTube Studio `Related Video` field to link to a long-form anchor (`LV-01` or `LV-02`) and must never instruct viewers to "click the link in the bio" when channel links are unset.

---

## 5. Commercial Asset & Speech Licensing Ledger

* **Speech Synthesis**: 100% local **Kokoro-82M ONNX** (`tools/kokoro_models/kokoro-v1.0.onnx` + `voices-v1.0.bin`, Apache-2.0 License). Microsoft Edge-TTS, Azure TTS, and unverified cloud voices are prohibited and blocked in code.
* **Typography**: Bundled SIL Open Font License (OFL 1.1) fonts in `tools/fonts/` (`BeVietnamPro-Bold.ttf`, `BeVietnamPro-Medium.ttf`, `SpaceGrotesk-Bold.ttf`, `SpaceMono-Bold.ttf`, `CrimsonPro-Variable.ttf`, `Fraunces-Variable.ttf`, `PlusJakartaSans-Variable.ttf`). Zero macOS `/System/Library/Fonts` dependencies.
* **Audio & Foley**: Programmatic synthesis (`tools/build_video.py`, `tools/sound_architect.py`) and local CC0 studio foley (`assets/audio/sfx/`).
