---
id: metr-watch-time-duration-confound
confidence: proven
as_of: 2026-11-12
applies_to: tiktok, reels
tags: retention, format
does_not_claim: That loops earn extra distribution, and no platform has published how a replay is weighted against a first play.
sources:
  - https://arxiv.org/html/2508.11086v3 | Relative Advantage Debiasing for Watch-Time Prediction in Short-Video Recommendation | study
  - https://arxiv.org/html/2410.00289v1 | Delving Deep into Engagement Prediction of Short Videos | study
  - https://sproutsocial.com/insights/instagram-reels-analytics/ | How to Analyze Instagram Reels Analytics to Grow | practitioner
  - https://newsroom.tiktok.com/en-us/how-tiktok-recommends-videos-for-you | How TikTok recommends videos #ForYou | platform_official
---
claim: Never compare average watch time across videos of different lengths, because Reels watch time counts replays while average watch time divides by first plays only, so a 9-second loop can outrank a 40-second clip on a number that is not measuring the same thing.
mechanism: ByteDance's own watch-time research states raw watch time is duration-confounded, with longer videos accumulating more seconds regardless of interest and pushing systems to over-recommend length, and the Snap short-video study finds average watch percentage falls as duration rises, so the only fair comparison is same-length against same-length, or a percentile within your own length bucket.
