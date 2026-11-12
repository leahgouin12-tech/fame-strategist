# Social Autopilot — design spec

**Date:** 2026-11-12 · **Status:** revised after subscription survey; ready for user review
**Owner:** solo creator, non-programmer, sole user of this app

---

## 1. What this is

A folder-driven system that turns raw photos and clips into platform-ready posts: judged
bluntly, edited where editing genuinely helps, captioned in the user's own voice, scheduled
against real data, and handed off for publishing. Plus a proactive layer that comes to the
user with observations rather than waiting to be driven.

The user's stated goal is to become an influencer. What this system owns: friction, craft,
consistency, and honest measurement. What it does not own: whether strangers decide to follow.

---

## 2. Constraints and boundaries — as verified

| Constraint | Evidence | Consequence |
|---|---|---|
| GPU: Intel UHD integrated, no discrete card | `Win32_VideoController` | No locally-runnable vision model. Judgment is remote by necessity. |
| RAM: 3.66 GB total physical | `TotalPhysicalMemory` = 3,934,248,960 B | Serial processing, memory prechecked, no Electron, no concurrent heavy jobs. |
| $0 marginal money | Standing rule across all their projects | No paid API tiers, no hosting bills. |
| Qoder subscription capacity | `threadlight` site live, `access_mode: public` | Already-paid capacity ≠ new cost — but see §2.2, it is deliberately not used for hosting. |
| Setup friction is a blocker | Builds apps for non-technical family | API key pasted once by this user into one config file. Never asked again. |

### 2.1 The privacy boundary, decided

**Model APIs are permitted. Public hosting is not.**

Reasoning, stated because it was gotten wrong once already: a vision-model call *is* the photo
leaving the machine, and on a GPU-less machine the judge was always going to be remote. So
"nothing leaves the machine" was never the rule in force. The boundary that is real and worth
holding is the distinction between **one image sent to one model API for one operation** and
**media sitting at a publicly fetchable URL on shared infrastructure.**

- ✅ Permitted: Gemini vision calls for judging; Gemini image generation for editing; web
  research by the agent.
- ❌ Not permitted: Qoder Sites or any host serving media at a public URL; media at rest on
  third-party storage; anything requiring a permanently enumerable file path.

**Consequence:** Instagram auto-publish is out — it requires exactly the forbidden thing. This
descopes Meta App Review entirely, which removes the longest and least predictable item from
the plan. Publishing is draft-assist handoff on all three platforms, uniformly.

### 2.2 Correction log — kept visible, not silently overwritten

Four claims were made and are now known to be wrong or overstated. They stay here because a
spec that hides its own errors gets re-made the same way next time.

1. *"Instagram auto-publish is permanently out because of the no-server rule."* Wrong — free
   public hosting existed. It is out now by explicit choice (§2.1), not by impossibility.
2. *"`ImageGen` is out for personal photos because it is a remote service."* Wrong — the photo
   is already remote at judging time, so excluding it bought nothing.
3. *"Generative editing costs nothing extra."* Overstated — see §2.3. It costs credits.
4. *"No trend signal is available for free."* Too bleak — there is no trend *API*, but an
   agent researching public sources is far stronger than the scraper I dismissed (§5.10).

### 2.3 Generative editing routes through the agent layer, and that has a price

`ImageGen` is a **Qoder tool the agent can call**, not an API the standalone app can call.
Two real consequences:

- Object removal, background swaps and relight are available when the **agent** is doing the
  edit, not when the local pipeline runs unattended.
- Those calls consume **Qoder credits — the user's explicitly scarce resource.** So generative
  editing is not free. It is paid-for-in-arrears, and it must be budgeted and reported the
  same as any other spend.

This is why §5.5 keeps two separate paths rather than one "best" path, and why the budget
tracker in §5.9 has two currencies: model quota and agent credits.

---

## 3. Explicit non-goals

**Permanent, not deferred.** Each is a documented ToS violation with an account-suspension path.

1. **Automated write-actions** — follow, unfollow, like, comment, subscribe — performed by
   anything other than an official approved API. The only technical route is logging in as the
   user, and that route *is* the violation.
2. Purchased or botted followers, views, or likes. No elegant version exists: bots are not
   people, they do not watch or buy, platforms detect and purge them while suppressing reach.
3. DM automation to first contact / strangers.
4. Any login-as-you scraping of any platform.
5. Batch-posting identical content across accounts to farm reach.

**Important split, because the valuable half of #1 is being kept:** automated *action* on the
follower graph is out; automated *insight* into it is in. See §5.12.

---

## 4. Architecture: two layers, cost-aware

The design is driven by two facts: compute is scarce and judgement is cheap; and some
capabilities only exist in the agent layer.

```
                        ┌── LOCAL CORE (always runs, $0, no credits) ──┐
folder/ ──▶ [1] watcher ──▶ [2] preflight ──▶ [3] judge ──▶ [4] Tier A edits
   raw        watchdog      dedupe·blur·      Gemini        reframe·straighten·
                            orient·corrupt·   free tier     exposure·WB·shadows·
                            resolution floor                clarity·denoise·grade
                                                            └──▶ [5] packages
                        └────────────────────────────────────────┘
                                          ▲
                        ┌── AGENT LAYER (scheduled, spends credits) ──┐
                        │ [6] generative edits · [7] research ·       │
                        │ [8] coach · [9] engagement drafting ·       │
                        │ [10] follower-graph insight                 │
                        └─────────────────────────────────────────────┘
```

**The funnel rule:** anything a formula can decide must not cost an API call, and anything Tier
A can fix must not cost an agent credit. Escalation is deliberate, per-item, and logged.

---

## 5. Components

### 5.1 Intake
`watchdog` on one user-chosen folder. New file → staged copy → queued. Originals are never
mutated. Removes go to `archive/`, not the bin.

### 5.2 Local preflight (unlimited, free, no AI)
Near-duplicate bursts (perceptual hash), out-of-focus (Laplacian variance), wrong orientation,
corrupt or unreadable, resolution below platform floor, subject outside recoverable crop.
Eliminates junk before any quota or credit is spent.

### 5.3 The Judge
One Gemini call per surviving item, behind a swappable `JudgeEngine` interface, because free
tiers change and the app must survive that.

Persona: a blunt creative director with high standards. Output is a score, a verdict, and one
plain-language reason. The default posture is **no** — a judge that passes everything is
worthless, and calibration examples are written so a mediocre photo fails.

| Dimension | Weight | Decides |
|---|---|---|
| Hook / scroll-stop | 30% | Does frame one stop a thumb. Highest by design. |
| Format fit | 20% | Which durable format this is strongest in. |
| Clarity of subject | 15% | Can you tell what it's about in a second. |
| Lighting & exposure | 12% | Fixable or fatal. |
| Framing & composition | 10% | Crop, headroom, dead space, horizon. |
| Platform-safety risk | 8% | **Gate, not score** — a fail vetoes regardless of total. |
| Native-feel vs over-produced | 5% | **Inverted: heavy polish scores down.** |

Two hard behaviours: it **must reject**, and it **does not judge the person** — not
attractiveness, not body, not face. Models are poor at that, it is not a growth lever, and it
would make the app unpleasant to open. Enforced at prompt level *and* output-schema level, so a
slipped comment is dropped rather than surfaced.

Honest limit: free-tier models carry a strong agreeableness bias. Rubric and calibration reduce
it; they do not remove it. The user's overrides are the backstop, and overrides are themselves
training data (§5.9).

### 5.4 Format matcher
A curated library of durable structures — POV, storytime, before/after, list, hot-take,
tutorial, react, day-in-life, detail-macro, series/episode. No external data, works offline,
compounds instead of expiring. The judge picks the format; the format picks the edit recipe,
caption skeleton, and aspect ratio.

### 5.5 The edit ladder
Three tiers, deliberately separate because their costs are different in kind.

**Tier A — local, unlimited, free, always applied.** ffmpeg + Pillow + OpenCV + littleCMS:
reframe to 9:16 / 4:5 / 1:1 with focal-aware crop, straighten, perspective correction, exposure
and contrast, white balance, shadow and highlight recovery, dehaze, local contrast, sharpening,
luminance denoise, skin-tone-preserving grade, vignette control, dodge-and-burn. This handles
most of what people mean by "fix the lighting."

**Tier B — local, unlimited, free, small regions.** OpenCV inpaint on a tiny mask: stray hairs,
single blemishes, dust, sensor spots, small signs. Instant and convincing. Never escalates.

**Tier C — agent-routed, generative, spends credits.** Person and object removal, background
replacement, generative relight, large-region reconstruction. Two sub-paths:
- **Gemini image generation** when the plan's API access covers it.
- **Qoder `ImageGen` image-to-image** when the agent is present — higher quality on busy
  backgrounds, and this is the one that costs credits (§2.3).

**Fallback, not primary: IOPaint / LaMa on CPU.** Kept because it needs no credit and no quota,
but on 3.66 GB it is serial, resolution-capped and ~25s+ per image with a memory precheck that
refuses rather than thrashes. Used when Tier C is unavailable and the user still wants the edit.

**The identity zone — the rule that outranks every tier above.**

A face detector (OpenCV YuNet or MediaPipe; reads pixels, does not write them, runs locally in
milliseconds) defines an **identity zone**: face, eyes, brows, lips, hairline, and hands. Inside
that zone, **only deterministic Tier A operations may ever touch the pixels, and always with
strength caps.** No generative model — Tier C, LaMa, Gemini image generation, or `ImageGen` —
is permitted to write inside it, ever. Not as a preference. As a hard mask in the code.

Why this is the right shape: it converts "don't change how I look" from a promise into a
property of the pipeline. Classical operations are *global transforms on colour and geometry* —
they cannot invent a different nose, shift a jawline, or erase a mole, because they have no
mechanism to do so. Generative ops do. So the guarantee is structural, and it survives a
future model that would be better at quietly changing faces.

| Operation | On the identity zone | Elsewhere |
|---|---|---|
| Exposure, contrast, WB, dehaze, shadow/highlight | ✅ Always | ✅ |
| Straighten, perspective, crop, reframe | ✅ | ✅ |
| Unsharp / clarity with proper masking | ✅ Capped, halo-checked | ✅ |
| Denoise | ⚠️ Luminance-only, near-zero — pore smoothing *is* identity drift and *is* the cheap look | ✅ |
| Super-resolution / upscaling (ESRGAN-family) | ❌ **Never.** A neural upscaler hallucinates skin and eyelash detail it never captured, which is both an identity change and the single most detector-visible edit there is | ⚠️ Optional, and reported |
| Blemish spot fill | ⚠️ Small mask only, radius-capped, one at a time; whole-face smoothing stays a dial at low | ✅ |
| Grooming repair (makeup, stray hair, lace edge, lint) | ✅ Small-radius classical only — see the grooming layer below | ✅ |
| Generative person / object removal | ❌ | ✅ |
| Background replacement | n/a | ✅ |
| Generative relight | ❌ | ✅ |
| Face relight | ❌ replaced by **dodge and burn** — classical, identity-preserving, and closer to what a human retoucher actually does | n/a |
| Geometric warp / liquify | ❌ Never, anywhere | ❌ Never |

**The grooming layer — a permitted category, distinct from smoothing.**

Makeup and grooming defects are not identity and not texture erasure; they are application
errors that read as a bad photo. These are explicitly in scope, handled with small-radius
classical inpaint and local frequency separation, never with a generative pass:

- cakey or creasing foundation, concealer lines, powder flashback
- clumped or smudged mascara, bleeding liner, uneven brow product
- stray hairs, flyaways, a loose thread, lint, a crease in clothing
- a lace edge, strap or seam sitting wrong — **position and edge only, never shape**

This is separated from skin smoothing on purpose. Removing a pore is erasure; removing a
mascara smudge is restoring what the person intended. Only the first one looks cheap.

**Banned outright: geometric warp (liquify).** Reshaping is neither classical correction nor
generative fill, so it slipped past the table above — and it is exactly where this promise
breaks. No body, face, hair-volume or garment *shape* may be pushed, pulled or slimmed by any
tool. Removing a distraction is allowed; changing a silhouette is not, because a warped photo
claims a shape that did not exist, which is the thing the user asked never to happen.

**The anti-catfish gate — enforced, measured, on every export.**

Two invariants, checked by code rather than trusted:

1. **Identity preservation.** A local face embedding (Insightface mobile-feature net: a few MB,
   milliseconds on CPU, never leaves the machine) is compared before and after. If cosine
   similarity drops below the threshold, the export is **refused**, not warned about. The
   threshold is calibrated against deliberately over-edited samples, not chosen to pass.
2. **Referential truth.** Every removal is logged as what left the frame, in the edit chain, and
   warp ops are absent by construction, so the pipeline cannot produce an image claiming a body
   or face geometry that the sensor never saw.

The operational definition the gate encodes: *someone who met you yesterday must recognise you
in this photo, and the photo must not claim anything that wasn't there.* That is the user's own
"never catfish" rule, turned into something that can fail a build.

**On "not AI detectable":** the honest reason this mostly solves itself is that there is nothing
to detect inside the identity zone. Classical correction is what every real photographer's
Lightroom catalog looks like; AI detectors look for generative artifacts, and no generative pass
runs on those pixels. Two real obligations remain, and they are transparency rather than
evasion:

- **Provenance.** The app keeps a signed local edit chain — every op, strength, and mask region
  in `SQLite` — so the user can *prove* a photo was corrected, not synthesised, if a platform's
  automatic labelling is wrong. C2PA-style "generated with AI" metadata is explicitly not added
  by any pipeline that only ran Tier A/B. A false AI label on a real photo costs reach, so
  having the receipts matters.
- **The boundary stated plainly.** This design is not an evasion system. If a generative edit
  ever changed how the user looks, this section would exist to help hide that from platforms and
  viewers — and it would not. The guarantee holds because the pixels genuinely are unaltered
  identity, not because the alteration is well disguised.

**Honest ceiling.** Classical ops cannot add detail that was never captured. A soft, heavily
motion-blurred, or badly underexposed shot gets cleaner, not resurrected — recovery past that
point always means invention, and invention is exactly what this section forbids on a face.
The judge's platform-safety and clarity gates (§5.3) are where "this one cannot be saved" gets
said out loud, before the user spends a slot on it.

**Budgeting is a first-class feature, in two currencies.** The app tracks remaining model quota
and remaining agent credits, queues Tier C work, and spends it only on posts scheduled this
week. It reports which path it used and what it cost, so "smart" never silently becomes
"expensive."

**Smoothing is a dial, default low.** Spot removal is on by default. Whole-face smoothing is
opt-in with an explicit strength setting, because blanket skin smoothing is the most
recognisable filter tell there is and conflicts with the user's own "must not look cheap"
rule. The judge scores heavy smoothing down on purpose.

### 5.6 Writer
Voice learned from a small corpus of how the user actually talks — their own captions, messages,
voice notes — because AI-sounding captions read as AI and cost reach. Hook line first, never
buried. 3–5 niche tags, not 30 generic ones. Alt text always. Per-platform variants: the same
media rewritten, not copy-pasted.

### 5.7 Scheduler
Starts on defensible defaults, then stops guessing. Each platform's own insights endpoints give
the account's audience-active times and per-post performance free to the account owner. After
roughly 20 posts, defaults are replaced by observed data.

### 5.8 Publish handoff
No scraping, no stored credentials, no fake login. Per-platform package: edited media, caption,
hashtags, alt text, suggested slot, deep link or share sheet into the native app. Two taps on
the phone. Uniform across all three platforms, because §2.1 is the reason and TikTok's audit
gate points the same way independently — two different constraints landing on the same design
is the strongest available signal it's the right one.

### 5.9 Feedback loop
Pulls reach, retention and profile-visit rate per post. Correlates against rubric scores, format
labels, and the user's own overrides. Reweights the rubric and surfaces the finding even when it
contradicts the app's taste: *"posts you scored 6/10 outperformed your 9/10s — your audience
does not care about composition."* That sentence is the most valuable thing here, and it can
only be earned from real data. Also tracks spend per post so the two currencies stay honest.

### 5.10 Trend research (agent layer)
Not an API — none is freely available, and a 1–3 day-old trend signal is a useless one because
reach is front-loaded. Instead a scheduled agent researching sources that are genuinely open:
Google Trends, published creator reports, niche YouTube and Reddit activity, format migrations
between platforms. Output is **formats and angles rising in their niche with a stated confidence
and an as-of date**, never a scraped hashtag list. Degrades to the §5.4 library when research
turns up nothing defensible.

### 5.11 Weekly Coach — the proactive layer
This is the honest answer to "a mind of its own." It is not sentience; it is **schedule + goals
+ research + receipts**. Once a week it runs unprompted and opens the conversation:

- what was dropped this week, what was rejected, and whether the rejection rate looks sane
- which posts performed, and the specific difference between the top and bottom
- where its own scores were wrong, since the user overrode it
- one thing to stop doing, one to start, and next week's slots
- what it found in research, with sources and dates
- what it spent in quota and credits, and what it would spend next week

It brings proposals to the user rather than acting on them. That is the whole design stance:
**the agent does everything that is preparation, and the user does everything that is a
decision or a human act.**

### 5.12 Follower-graph insight — insight yes, action no
Instagram and TikTok both provide the account owner their **own follower and following lists**
via official download-your-data export. The app parses two exports, diffs them, and reports:
who unfollowed, when, and which posts the window sits after. Correlated churn is the useful
part — *"you lost 40 followers the week you stopped doing POV series"* is actionable in a way
that an unfollow button never was.

The **action** half stays out (§3.1). What is lost is a button nobody should have pressed; what
is kept is the diagnosis that actually informs content.

### 5.13 Engagement drafting — the legitimate half of "do things for my account"
The app cannot be the user's personality. It can remove all the labour around the things that
grow an account:

- **pull every comment and draft replies in the user's voice**, queued for approve-and-tap
- **a daily 15-minute list**: accounts in the niche worth engaging, plus one specific,
  non-generic thing to say about their recent post
- series and continuation planning, collab and duet suggestions, profile and bio CTA review,
  keyword and hashtag-set SEO, cross-platform repurposing of a winner into a second format
- reminders when a slot is empty, or when a post is worth following up within its first hour

Fully open on X. On Instagram and TikTok comment read/reply needs a Business or Creator account
plus the relevant official permission — available through the approved API path, not via a bot.

---

## 6. Stack

- **Local core: Python** — pipeline, ffmpeg/OpenCV/Pillow, `watchdog`, `SQLite` ledger. Light
  process, fits inside 3.66 GB when run serially.
- **Edits:** ffmpeg + Pillow + OpenCV + littleCMS (Tier A/B); LaMa via IOPaint as fallback;
  Gemini image generation and Qoder `ImageGen` for Tier C.
- **Judge/Writer:** `JudgeEngine` interface, Gemini free tier first, swappable without rework.
- **Agent layer:** Qoder scheduled agent — research, coaching, generative edits, drafting.
- **UI: a local web page in the browser** (FastAPI on localhost, started on demand).
  Deliberately not Electron: Electron's baseline RAM is a genuine risk on this machine.
- **Config: one file, key pasted once.**
- **`outbound()` chokepoint:** one function through which every network call carrying image
  bytes must pass, so §2.1 is enforced by code and auditable in a log rather than asserted in a
  document.

Not chosen: Electron (RAM), paid API tiers (rule), scraping frameworks (ToS), Qoder Sites
hosting (declined for the public-URL reason in §2.1).

---

## 7. Known failure modes — stated before building

1. **Agent credits are the real budget**, not money. Tier C edits and the weekly coach spend
   them, and the user's credits are scarce. Mitigated by the two-currency tracker and Tier C
   being restricted to posts scheduled this week.
2. **Tier C is not unattended.** Generative edits happen when the agent runs, not the instant a
   file is dropped. A post may sit in a queue overnight.
3. **Object removal on busy backgrounds leaves artifacts sometimes.** LaMa and generative fill
   are strong, not magic, and the CPU fallback is resolution-capped.
4. **Judging is capped by free-tier model quality.** Rubric design beats model size, but there
   is a ceiling and it is worth naming now rather than discovering later.
5. **Agreeableness bias persists.** Some mediocre posts will pass. Threshold, calibration and
   user overrides are the mitigation.
6. **Free-tier caps can tighten or close.** The swappable interface contains the damage without
   making it zero: an outage degrades to preflight + Tier A + manual judgment.
7. **The coach is generic before ~25 posts** of real data. It will say so rather than dress up
   guesswork as insight.
8. **3.66 GB is tight.** LaMa with a browser and the app open together may fail; precheck
   refuses rather than thrashes.
9. **TikTok publishing stays manual** until the user passes their audit — unrelated to build
   quality, and not fixable by this app.
10. **Growth is not guaranteed.** This deletes friction, raises consistency and measures
    honestly. On-camera presence is the larger factor and it is not software.

---

## 8. Success criteria

**App-level (weeks):** drop-to-ready-package in under 10 minutes of the user's own attention;
judge rejection rate in a believable band; overrides declining over time, and scores moving
where they don't; spend per post visible and inside budget; zero ToS-violating code paths,
verifiable by grep; every image-bearing call routed through `outbound()`.

**Real-world (months, and the honest one):** posting cadence held for 8 weeks, follower growth
tracked with the caveat that content and presence decide it far more than this tool does.

---

## 9. Build order

| Phase | Deliverable | Proves |
|---|---|---|
| **1** | Local core: folder → preflight → judge → blunt verdict in a UI | **Whether the bluntness is real.** Cheap enough to know within a day. |
| **2** | Tier A + B edit ladder, per-platform packages | Whether output looks native instead of cheap. |
| **3** | Writer + voice learning | Whether captions sound like them. |
| **4** | Weekly Coach + feedback loop + two-currency budget | Whether it actually gets smarter — and what it costs. |
| **5** | Trend research + format library | Whether research beats guessing. |
| **6** | Tier C generative edits, LaMa fallback | Whether credit cost is worth it per edit type. |
| **7** | Follower-graph insight + engagement drafting | Whether the diagnosis changes what they post. |
| **8** | Niche discovery mode | Whether the experiment framework reads correctly. |

Phase 1 is the judge alone, deliberately. If the verdicts come out polite, the premise is wrong
and it is far better to learn that on day one than after the editing machinery exists.

The user has **no niche yet**, so §8 is not a nice-to-have — it is how the niche gets found
rather than guessed.

---

## 10. Remaining open questions

1. Which platforms does the account exist on now, and are any Business/Creator accounts?
   (Decides whether §5.13 and insights ingestion work at all.)
2. Roughly how much media gets dropped per week? (Sets whether the two-currency budget is tight
   or comfortable.)
3. Willing to record voice-note commentary, or photo-and-clip only? (Changes writer and video
   pipeline substantially.)
4. **How many Qoder credits per week can this realistically have?** Tier C and the coach both
   draw on them and credits are already the scarce resource. If the honest answer is "very
   few," §5.5 Tier C shrinks and §5.11 moves to fortnightly. Better decided now than rationed
   under protest later.
