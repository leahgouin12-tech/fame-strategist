---
id: form-zero-followers-not-equal-everywhere
confidence: proven
as_of: 2026-11-12
applies_to: tiktok, x, reels
tags: algorithm, failure-modes
does_not_claim: That zero followers is harmless everywhere: TikTok's statement is about the For You feed, its follower thresholds still gate features, and X's published code describes candidate sourcing rather than a promise that new accounts cannot travel.
sources:
  - https://newsroom.tiktok.com/en-us/how-tiktok-recommends-videos-for-you | How TikTok recommends videos for you | platform_official
  - https://ar5iv.labs.arxiv.org/html/2301.04945 | Analyzing User Engagement with TikTok's Short Format Video Recommendations using Data Donations | study
  - https://github.com/twitter/the-algorithm | Source code for the X Recommendation Algorithm | platform_official
  - https://digiday.com/marketing/how-every-major-platform-pays-creators/ | How every major platform pays creators | secondhand
---
claim: Start the video formats on TikTok and Reels and treat X as a slower lane, because TikTok states that neither follower count nor past hits are direct ranking factors, donated-view data shows non-followed videos completed at least as often as followed ones, and X's own code sources roughly half of For You candidates from accounts the viewer already follows.
mechanism: A feed assembled from out-of-network candidates can carry a stranger, while a feed half-filled from the viewer's own network has nowhere to place an account nobody follows yet, and the paid doors are almost all gated above zero, from 1,000 followers for TikTok LIVE to 500 verified followers plus millions of impressions on X.
