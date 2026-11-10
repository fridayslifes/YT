# Cognitive Core channel audit — 2 November 2026

**Channel:** [@CognitiveCoreOfficial](https://www.youtube.com/@CognitiveCoreOfficial) (`UC6hwVBnsfvfUGxfZi2sFT3A`). **Metrics snapshot:** authenticated, read-only YouTube Data API at 00:53 IST on 2 November 2026. Five videos were also browser-reviewed using auto-generated transcripts. The [31 October content tracker](../../CONTENT_TRACKER.md) supplies topic labels; counts below use the newer snapshot. No channel setting or upload was changed.

## The one fix this week

**Make the scientific promise match the cited study, starting with existing uploads.** First correct [SH-08](https://www.youtube.com/shorts/LbNaAb4xm7w)'s “cure social anxiety” title and the unsupported claims [SH-15](https://www.youtube.com/shorts/QbqtRznFtQE) attributes to a 1979 study. SH-08 makes a treatment promise that its cited T-shirt study did not test; SH-15 alone accounts for **503 of 1,098 Short views (45.8%)**. A correction is worthwhile for accuracy regardless of whether views change. YouTube says a title edit has no automatic ranking benefit; any distribution change follows viewer response. [Gilovich et al. (2000)](https://www.researchgate.net/profile/Thomas-Gilovich/publication/12609065_The_Spotlight_Effect_in_Social_Judgment_An_Egocentric_Bias_in_Estimates_of_the_Salience_of_One%27s_Own_Actions_and_Appearance/links/543680600cf2bf1f1f2bd452/The-Spotlight-Effect-in-Social-Judgment-An-Egocentric-Bias-in-Estimates-of-the-Salience-of-Ones-Own-Actions-and-Appearance.pdf); [Kahneman and Tversky (1979)](https://web.mit.edu/curhan/www/docs/Articles/15341_Readings/Behavioral_Decision_Theory/Kahneman_Tversky_1979_Prospect_theory.pdf); [YouTube performance FAQ](https://support.google.com/youtube/answer/141805?hl=en).

The source check problem recurs in production inputs. The [voice profile](../../channel_assets/voice.md) forbids instant cures and misattributed statistics but requires a numerical study result in every opening. The local [dossiers](../../channel_assets/scientific_dossiers.json) for SH-14, SH-15 and SH-16 include claims the named papers do not establish, although the [tracker](../../CONTENT_TRACKER.md) calls those videos dossier backed. Before another release, match **each** number and mechanism to its source, identify behavioral advice as advice, and allow a strong opening without a number when the paper supplies none. Hook scores and a `citation_verified` flag cannot substitute for that check.

## What the snapshot supports

- The uploads playlist contains **18 public, processed videos: 16 Shorts and two long videos**, with **five subscribers**. The channel API aggregate says `videoCount=16` and `viewCount=1,128`; the 18 individual videos sum to **1,130 views**. The discrepancy is unresolved, so these totals should not be silently combined.
- The 16 Shorts sum to **1,098 lifetime views**, with a **22.5-view median**. The top four—SH-15 (503), SH-01 (170), SH-06 (127), SH-07 (85)—have **885 views, or 80.6%** of Short views. Unequal upload ages prevent a fair topic ranking.
- There are **34 likes, including seven creator likes**. The **21 comments** comprise 20 top-level comments, of which 19 are by the creator, plus one reply. The sole outside top-level viewer comment is on SH-08. Comment totals therefore do not show a broad viewer conversation.
- Public Short views count starts and replays without a minimum watch duration. This snapshot cannot tell how many viewers chose to keep watching. [YouTube's Shorts metric definition](https://support.google.com/youtube/answer/10059070?hl=en).

### Three strengths to preserve

1. **A visible premise from frame one.** In five browser-reviewed samples, SH-15 opens on a man, cash and pain contrast; SH-14 shows a jam aisle and study card; SH-08 shows a cringing person and “THREE DAYS AGO?”; SH-16 opens on a photorealistic simulation scene; LV-02 shows dual screens and “BEFORE YOU FINISH ONE TASK.” Each gives an immediate subject.
2. **Highest playback count.** SH-15's 503 starts/replays are the highest count among the Shorts in this snapshot. Neither that count nor the five-subscriber total establishes unique reach. Preserve the concrete, personal framing while correcting its evidence.
3. **Other everyday-friction topics also drew views.** SH-01's doorway lapse (170), SH-06's waiting mode (127) and SH-07's unfinished tasks (85) are all above the Short median; SH-08 generated the one outside viewer comment. Their ages and exposure differ, so these are candidates for a controlled follow-up, not proof that their titles caused the difference.

**Secondary packaging test:** eight of the tracker’s latest ten Short titles begin “Why,” and the local title linter flags nine as longer than its 40-character mobile preview heuristic. Try a shorter, source-safe opening on a future title after the corrections; neither this pattern nor the linter score proves a performance problem.

## Actions on videos already live

YouTube Studio can edit a title and description on the existing URL. A description line beginning `Correction:` can identify a timestamp and explain a mistake. Studio Editor can cut the beginning, middle or end while preserving URL, views and comments, but it cannot replace narration or on-screen claims; a corrected upload gets a new URL. **Saved Studio cuts cannot be reverted.** Most local originals are no longer available, so preserve an original copy or download the current unedited upload, then preview the exact proposed cut before saving. [Edit video settings](https://support.google.com/youtube/answer/57404?hl=en); [trim guidance](https://support.google.com/youtube/answer/9057455?hl=en); [replace or delete guidance](https://support.google.com/youtube/answer/55770?hl=en-uk).

| Order | Video and sampled claim | Fix possible on its current URL | Media decision |
| --- | --- | --- | --- |
| 1 | **SH-08**, 54 views: tracker title says “Cure Social Anxiety”; spoken at 0:36 calls its five-second exercise a cure. The [2000 paper](https://www.researchgate.net/profile/Thomas-Gilovich/publication/12609065_The_Spotlight_Effect_in_Social_Judgment_An_Egocentric_Bias_in_Estimates_of_the_Salience_of_One%27s_Own_Actions_and_Appearance/links/543680600cf2bf1f1f2bd452/The-Spotlight-Effect-in-Social-Judgment-An-Egocentric-Bias-in-Estimates-of-the-Salience-of-Ones-Own-Actions-and-Appearance.pdf) measured estimates of who noticed participants' shirts, not anxiety treatment. | Rename along the lines of **“Why Your Awkward Moment Feels So Public”**; add a `Correction: 0:36` line clarifying the study's scope. Check the live title in Studio first. | A revised narration and new upload are needed to replace “cure” while retaining the takeaway; a cut may remove the ending's point. |
| 2 | **SH-15**, 503 views: the opening invokes 1979 prospect theory, then gives dollar thresholds, brain scans, amygdala/insula and cortisol claims without separate support. The [1979 paper](https://web.mit.edu/curhan/www/docs/Articles/15341_Readings/Behavioral_Decision_Theory/Kahneman_Tversky_1979_Prospect_theory.pdf) analyzes choices under risk; it does not establish those neural or hormonal mechanisms. | Add timestamped description corrections for 0:00, 0:18, 0:24 and 0:33; review the current “1979 Study On Why You Freeze” title against the paper. Preserve the relatable loss-versus-gain topic. | Several claims are woven through the Short. Plan a source-checked remake if the spoken explanation should be retained; do not assume one cut will repair it. |
| 3 | **SH-14**, 10 views: 0:00 says 24 choices cause “90%” focus loss; 0:23 adds prefrontal glucose depletion. [Iyengar and Lepper](https://business.columbia.edu/faculty/research/when-choice-demotivating-can-one-desire-too-much-good-thing) studied choice sets, purchases, satisfaction and essays, not those mechanisms. | Keep the 24-versus-six jam purchase framing; add timestamped corrections for the focus and glucose claims. | Preview whether two cuts leave a coherent story. Otherwise make a corrected version with a new URL. |
| 4 | **SH-16**, 11 views: 0:15 claims “1%” yields “billions to one”; the later brain-prediction and five-second anxiety method are mixed into [Bostrom's conditional trilemma](https://simulation-argument.com/simulation.pdf), which does not establish them. | Clarify the conditional argument in the description. Check the **Altered content** setting in Studio for the photorealistic scenes; the field was absent from this API response, so its current value is unknown. [YouTube settings](https://support.google.com/youtube/answer/57404?hl=en). | Replace the spoken numbers or mixed mechanism only through a coherent cut or corrected upload. |
| 5 | **LV-02**, 6 views: the spoken opening still says “lose 80% of your focus in 90 seconds,” although the [tracker](../../CONTENT_TRACKER.md) says metadata removed it. | Add `Correction: 0:00` and review the rest of the eight-minute narration for other unsupported numbers. | Test a start trim in preview; if the new opening fails, use a corrected upload. |

After those five, review the tracker’s open citation queue for SH-02–SH-07 and SH-09–SH-10 against the actual audio before asserting further errors. The sampled transcripts are auto-generated and may mishear names or words.

**Studio checks while editing:** confirm that each relevant Short has a **Related Video** leading to an appropriate long video, and that LV-01/LV-02 have useful end screens where absent. These fields were not verified. [Related Video setting](https://support.google.com/youtube/answer/57404?hl=en); [end screens](https://support.google.com/youtube/answer/6388789?hl=en). The API `caption` flag was true only on SH-05, SH-09 and SH-10; this does not establish subtitle absence on others. Check authored tracks separately from burned-in text. SH-14's missing tags can be repaired in Studio, but tags play a minimal discovery role; leave that after source corrections and the viewing path. [YouTube's tags guidance](https://support.google.com/youtube/answer/141805?hl=en).

## Seven-day readout once Studio data is available

Export a dated seven-day baseline **before** edits and log each Studio change. For the following seven days, track each affected Short's **engaged views**, feed exposure, viewed-versus-swiped share, average view duration/retention, and subscriber gains; for the long videos, track impressions, click-through rate, retention and traffic from Shorts if Studio exposes it. Compare each video with its own preceding seven days and a similar unchanged upload, while noting age and exposure differences. Use this to choose the next remake or packaging test, not to decide whether an inaccurate claim needs correcting. Engaged views and retention are separate from public starts/replays. [YouTube Shorts views](https://support.google.com/youtube/answer/10059070?hl=en); [Analytics metrics](https://developers.google.com/youtube/analytics/metrics).

This audit's credentials lack `yt-analytics.readonly`; **retention, engaged views, CTR, watch time and per-video subscriber gains were unavailable**. No inference about the algorithm, first-second drop-off, or a title edit's causal effect is supported yet.

The tracker records SH-16's public time, but does not supply a complete per-video publication timeline. Upload cadence was therefore not scored. The five auto-transcript samples do not establish which other videos repeat these claims.

## Public-video inventory at the snapshot

Topic labels follow the 31 October tracker. Counts are 2 November lifetime API values; likes include any creator likes, and comments include creator posts.

| ID | Public video | Views | Likes | Comments |
| --- | --- | ---: | ---: | ---: |
| SH-16 | [Simulation argument](https://www.youtube.com/shorts/qMpS90Fupbs) | 11 | 1 | 1 |
| SH-15 | [Loss aversion](https://www.youtube.com/shorts/QbqtRznFtQE) | 503 | 3 | 1 |
| SH-14 | [Jam choices](https://www.youtube.com/shorts/tyw9-qzJxwI) | 10 | 1 | 1 |
| LV-02 | [Three focus traps](https://www.youtube.com/watch?v=1Tg-y7fqAn4) | 6 | 2 | 1 |
| SH-12 | [Task deadlines](https://www.youtube.com/shorts/R1xMCnlsM6o) | 22 | 0 | 1 |
| SH-11 | [Bystander effect](https://www.youtube.com/shorts/sHJ2ubBWxEI) | 10 | 0 | 1 |
| SH-10 | [Phantom phone buzz](https://www.youtube.com/shorts/EaV0AeCH6hw) | 23 | 1 | 1 |
| SH-09 | [Netflix scrolling](https://www.youtube.com/shorts/X2wZIWeOqAQ) | 25 | 0 | 1 |
| SH-08 | [Spotlight effect](https://www.youtube.com/shorts/LbNaAb4xm7w) | 54 | 6 | 3 |
| SH-07 | [Unfinished tasks](https://www.youtube.com/shorts/r6CXqdeT1Tw) | 85 | 9 | 1 |
| SH-06 | [Waiting mode](https://www.youtube.com/shorts/FK59XNAeKVA) | 127 | 3 | 1 |
| SH-05 | [Store layout](https://www.youtube.com/shorts/gpXrsB6vBms) | 5 | 0 | 1 |
| SH-04 | [City architecture](https://www.youtube.com/shorts/GCSik-nPYWU) | 10 | 0 | 1 |
| SH-03 | [Late-night scrolling](https://www.youtube.com/shorts/H4dOsxJqstg) | 11 | 0 | 1 |
| SH-02 | [Attention habit](https://www.youtube.com/shorts/CV6Xl-yzNUc) | 23 | 0 | 1 |
| SH-01B | [Doorway effect, part two](https://www.youtube.com/shorts/9Q-FT8oE-EQ) | 9 | 0 | 1 |
| SH-01 | [Doorway effect](https://www.youtube.com/shorts/ljjAPauTnN4) | 170 | 7 | 2 |
| LV-01 | [Dopamine exhaustion](https://www.youtube.com/watch?v=f2vsYJOyZ3U) | 26 | 1 | 1 |

**Outside the live inventory:** SH-13 is a local render awaiting a verified research dossier, according to the tracker. It was not uploaded at this cutoff. Do not use it to resolve the channel's `videoCount` discrepancy.

**Next action:** prepare the exact SH-08 title and the SH-08/SH-15 timestamped correction text for Studio review, then continue through the five-video evidence list.
