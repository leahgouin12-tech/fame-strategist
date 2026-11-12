# Playbook metrics research log

Task: source the numbers behind `data/playbook/metr-*.md` (retention, watch-through, follower
conversion, hook timing, rewatch/loop, engagement signals, contradicted folk advice).
Research date: 2026-11-12. Everything below was run through WebSearch first, then WebFetch.
A URL appears in the "loaded" section only if the page body actually rendered and I read the
relevant part. Everything else is in the rejected section with the reason.

## Entries written

| file | confidence | tier mix |
| --- | --- | --- |
| metr-completion-signal.md | proven | 3 platform_official |
| metr-watch-time-duration-confound.md | proven | 2 study + practitioner + platform_official |
| metr-retention-benchmark-gap.md | contested | 2 study + 2 secondhand |
| metr-3-second-hook-rule.md | folklore | practitioner + 3 secondhand |
| metr-view-to-follow-rate.md | folklore | study + practitioner + 2 secondhand/platform |
| metr-shares-over-likes.md | contested | 2 platform_official + study + 2 secondhand |
| metr-cadence-beats-clock.md | contested | 3 study + platform_official |
| metr-delete-underperformers.md | contested | 2 platform_official + 2 secondhand |

Distribution: 2 proven, 4 contested, 2 folklore (requirement was at least 3 contested/folklore).

## Loaded and used

**https://newsroom.tiktok.com/en-us/how-tiktok-recommends-videos-for-you** (TikTok Newsroom, 18 Jun 2020)
- Said: For You factors are user interactions, video information, and device/account settings, weighted by value to the user; "whether a user finishes watching a longer video from beginning to end" is a strong indicator of interest; "neither follower count nor whether the account has had previous high-performing videos are direct factors"; already-seen/repeated/spam content is not recommended; first likes, comments and replays seed early recommendations.
- Failed to establish: any numeric weight, any completion threshold, any initial test-audience size, and any statement about rewatch/loop weighting. Also 2020-vintage, so it is not a current ranking spec.

**https://about.instagram.com/blog/announcements/instagram-ranking-explained** (About Instagram, Adam Mosseri, 31 May 2023)
- Said: each surface has its own algorithm; for Reels the predictions include "reshare a reel, watch a reel all the way through, like it, and go to the audio page", ranked roughly by your activity, your history with the poster, reel information, poster information; reduced visibility for low-resolution, watermarked, muted, bordered or mostly-text reels; "we don't suppress content to encourage people to buy ads".
- Failed to establish: any ordering of sends vs likes vs watch time, any figure, and anything current (2023 text; no mention of the 2025-era "sends per reach" framing).

**https://www.tiktok.com/safety/en/policies-and-engagement/fyf-standards** (TikTok, released 25 Aug 2026, effective 24 Sep 2026)
- Said: a public For You feed eligibility policy exists; content "not suitable for a broad audience" is excluded from recommendation but can still appear in search/profile; low views do not necessarily mean a rule was broken; creators can see eligibility status in analytics; 16+ requirement for FYF.
- Failed to establish: anything about engagement signal weights, followers, or new accounts. Used only to prove an official eligibility layer exists (relevant to the "deleted/hidden post" folklore).

**https://github.com/twitter/the-algorithm** (X, repo created 27 Mar 2023)
- Said: the released surface is the For You Timeline plus Recommended Notifications; candidate sources are search-index (~50% of posts), tweet-mixer, UTEG and FRS; light ranker then heavy ranker; visibility filters; SimClusters/TwHIN/Real Graph model components.
- Failed to establish: the engagement weights. The README carries no numbers and points to a blog post I could not reach, so every "reply = 13.5, like = 0.5" figure in circulation comes from secondhand reads of the 2023 README.

**https://wistia.com/blog/video-marketing-statistics** (Wistia 2026 State of Video, 22 Apr 2026, Wistia's own report)
- Said: engagement rate is defined as how much of a video people watch on average; "the shorter the video, the higher the engagement rate"; sample is 900+ professionals surveyed plus 13M+ videos and 79M hours of Wistia viewing data; explicit caution that a longer video at a lower rate can still collect more total watch time; educational videos under five minutes get watched about halfway.
- Failed to establish: the actual per-length percentages, which live in a chart image whose text did not render, so no number like "52% under one minute" is cited anywhere in my files. Also B2B hosted video, not TikTok/Reels, so it cannot anchor a short-form retention benchmark.

**https://blog.hubspot.com/marketing/state-of-video-marketing-new-data** (HubSpot restating Wistia's report, updated 22 Apr 2026)
- Said: same sample sizes (900+ surveyed, 13M videos, 79M hours); a third of webinars still get plays three months later; social engagement is the top success metric for 22% of teams.
- Failed to establish: any engagement-by-length percentage. Used only to cross-check the Wistia sample numbers; not cited in the playbook.

**https://buffer.com/resources/how-often-should-you-post-on-tiktok/** (Buffer, Kirsti Lang / analysis by data scientist Julian Winternheimer, 8 Oct 2025, updated 25 Jun 2026)
- Said: 11.4M TikTok posts from 150,000+ accounts, fixed-effects regression plus Z-scores comparing each account to itself; vs one post/week, views per post rise up to 17% at 2-5/wk, 29% at 6-10, 34% at 11+; median views stay flat (489, 506, 487, 459) while the 90th percentile goes 3,722 to 14,401; authors state it is observational and "posting more just increases your odds".
- Failed to establish: causation, a time window, any survivorship-bias handling, and anything about accounts with zero followers. Sample is Buffer-scheduled posts, i.e. a vendor dataset commissioned by Buffer, not an independent study.

**https://buffer.com/resources/best-time-to-post-on-tiktok/** (Buffer, Kirsti Lang, 14 Sep 2026)
- Said: 7.1M posts published through Buffer, metric is median engagement rate per time slot, timezone-normalised; best slot Sunday 9 a.m., best day Saturday, evenings 6-11 p.m. generally stronger than 12-5 p.m.; explicit caveats that there is no single magic time, that timing is a small assist, and that other studies disagree on the best day.
- Failed to establish: an effect size for posting hour, which is exactly why the cadence entry is marked contested rather than proven; also Buffer users only.

**https://buzzabout.ai/blog/tiktok-engagement-rate-benchmarks** (buzzabout LLC, Viktor Surkov, 23 Jul 2026)
- Said: 460,594 tracked public TikTok posts, 460,483 with nonzero views, 212,029 creators, 130.9B views; engagement rate = (likes+comments+shares)/views per post; mean 5.38%, median 3.95%, p10 0.8%, p90 11.11%; likes 90.9%, shares 8.1%, comments 1.0% of all engagement; duration ladder 3.71% under 15s up to 5.25% over 5 min; variance explained eta-squared 0.662 creator, 0.425 topic, 0.028 duration, 0.012 hour of day, 0.015 hook.
- Failed to establish: any profile-visit or follow-conversion figure (the page states none is reported), any per-follower-tier benchmark, and representativeness, since entry is via niche research queries, not a TikTok panel. Vendor dataset, self-published, correlational by its own admission.

**https://arxiv.org/html/2508.11086v3** ("Relative Advantage Debiasing for Watch-Time Prediction in Short-Video Recommendation", Liu, Han, Zhan, Zhao, Mu, Song - ByteDance, v3 dated 24 Nov 2025)
- Said: raw watch time is a satisfaction proxy that is duration-confounded, "longer videos accumulate higher watch times regardless of true interest", producing "a tendency to over-recommend long-form content"; proposes quantile (CDF) labels to debias; validated on KuaiRand-Pure (26,592 users, 7,146 items, 1,384,425 interactions), an industrial set with over a billion interactions, and online A/B tests.
- Failed to establish: what TikTok/Reels actually do for organic creators, and any creator-side number. It is a recommender-modelling paper by the platform that owns the data, so the duration-confound claim is well evidenced but the remedy is invisible to a creator's dashboard.

**https://arxiv.org/html/2410.00289v1** ("Delving Deep into Engagement Prediction of Short Videos", Li et al., CUHK MMLab / Snap Inc, 30 Sep 2024)
- Said: builds SnapUGC from 90,000 Snapchat Spotlight short videos, 10-60s, each with 2,000+ views and 2,000+ viewers; argues average watch time is duration-dependent and "unsuitable for comparing two videos with different durations"; average watch percentage falls as duration rises; proposes normalised average watch percentage and an engagement continuation rate defined as the probability of watching more than five seconds; visual quality scores correlate with watch time only 0.084-0.290.
- Failed to establish: anything about TikTok or Reels distribution, and any hook-window recommendation for a solo creator; also a paid-free distinction, since Spotlight is not the same inventory as the For You feed.

**https://sproutsocial.com/insights/instagram-reels-analytics/** (Sprout Social, Mahnoor Sheikh, 28 Jan 2025, modified 1 May 2026)
- Said: Reels insights definitions, views counts plays and replays, reach is unique accounts split follower/non-follower, watch time includes replays, average watch time is total watch time divided by initial plays only, interactions are likes+comments+saves+shares, and follows shows which Reels converted viewers.
- Failed to establish: any benchmark number (the only figures on the page are hypothetical examples), and the profile-visit step of the funnel is not documented there. It is a vendor explaining Instagram's panel, so I treat it as practitioner documentation of metric definitions, not as evidence of a rate.

**https://www.socialinsider.io/social-media-benchmarks/instagram** (Socialinsider, Elena Cucu, 20 Feb 2026, modified 4 Nov 2026)
- Said: 67,541,436 organic Instagram brand posts from 579,000 brand accounts, tiered from under 5K to 100K-1M followers; engagement rate by followers 0.48% overall in 2025 vs 0.50% in 2024; Reels 0.52%, carousels 0.55%, images 0.37%; Reels lead comments at every tier; follower growth rate by tier 22% for 1K-5K down to 11.25% for 100K-1M.
- Failed to establish: any follows-per-post or view-to-follow figure, and reach rate; brands only, so not a solo-creator benchmark. Self-reported inconsistency in the page: the sample is labelled 2026 but contains 2025 values. Vendor-commissioned (Socialinsider sells the analytics).

**https://superdirector.app/glossary/follow-conversion-rate** (Superdirector, Bell Chen, 1 Mar 2026, updated 11 Oct 2026)
- Said: this is the most honest version of the folklore I found, it defines follow conversion, then states the numbers are "not published benchmarks; validate against your own panel", gives 0.15% Reels / 0.25% TikTok / 0.10% Shorts as operator heuristics, and states plainly that no industry benchmark publishes a verified follow-conversion median by audience size and that no platform names per-clip follow conversion as a ranking input.
- Failed to establish: the heuristics themselves, which are unattributed, plus a fictional worked example (0.64% for an invented brand). Used as the exhibit for "the number has no source", tier secondhand.

**https://www.superside.com/blog/best-video-hooks** (Superside, 28 Oct 2026)
- Said: TikTok's creative best practices claim "90% of ad recall impact is captured within the first six seconds", listed in the page's own source table as TikTok internal research for performance ads with no external study named; the earliest named first-seconds study is Google/YouTube Insights "The First 5 Seconds" (Jun 2015, thousands of TrueView ads, 16 countries, 11 verticals, 170 creative attributes); the page explicitly refuses to use the circulating 2.5-second figure because it "couldn't find evidence to back it up" and reports no credible published benchmark for hook rate or thumb-stop rate.
- Failed to establish: the primary TikTok page itself (it would not render, see rejected), so the 6-second figure stays secondhand, and it is an ad-recall number, not an organic-retention number.

**https://posteverywhere.ai/blog/how-the-tiktok-algorithm-works** (PostEverywhere, Jamie Partridge, 23 Mar 2026)
- Said: a practitioner guide that labels its own advice "a rule of thumb, not a TikTok figure", says retention thresholds like 70% are "a guess, not a fact", gives no study for the 3-second hook, and separately cites Buffer's 11.4M-post cadence work plus its own review of 4,500+ scheduled TikToks.
- Failed to establish: any primary source for the hook window. Used as evidence that vendors themselves cannot trace the number, tier secondhand.

**https://posteverywhere.ai/blog/how-the-x-twitter-algorithm-works** (PostEverywhere, Jamie Partridge, 23 Mar 2026)
- Said: reads the April 2023 home-timeline ranking README (in `twitter/the-algorithm-ml`, `projects/home/recap/README.md`) as like 0.5, repost 1.0, reply 13.5, reply-engaged-by-author 75, good profile click 12, conversation click plus 2 min dwell 10, video watched halfway 0.005, negative feedback -74, report -369; notes the Jan 2026 `xai-org/x-algorithm` release states weights "do _not_ scale the raw engagement counts" and publishes no matching table; ~1,500 candidates per request, roughly half from people you follow.
- Failed to establish: current weights, and anything about bookmarks or shares. The page itself concedes the 2026 code does not match the 2023 table, which is why metr-shares-over-likes is contested.

**https://www.terezatizkova.com/writing/x-algorithm** (Tereza Tizkova, Jul 2026)
- Said: independently lands on the same 2023 numbers and names the variables (`scored_tweets_model_weight_retweet`, `reply_engaged_by_author`, `good_profile_click`) plus author-diversity decay 0.5 and floor 0.25; states learned model weights are not published, so "we know what features go in and how the formula combines them, but not what the neural network learned".
- Failed to establish: anything official. Not cited in the playbook because it is a single blogger's read of the same 2023 README that PostEverywhere cites, and I could not verify against the code myself.

**https://cut.pro/en/blog/tiktok-stuck-at-200-views-2026** (Cut.Pro, Nicolas Zani, 2 Nov 2026)
- Said: the clearest debunk of the batch-distribution myth I found, TikTok "has never published" batch sizes, the "first batch of 200 to 500 users" story traces to Chinese write-ups about Douyin copied into other languages without a source, the 70% retention threshold is unsourced folklore, and there is no TikTok source for fixed 200/1k/10k tiers; confirms moderation-before-distribution, that follower count and prior virality are not direct factors, that reposting the same file resets nothing, and that "shadowban" is not a TikTok term (the real concepts are FYF ineligibility and account restriction, both visible in-app); cites a 5.16M-post study where the modal view count is around 100 and Buffer's median of 459-506.
- Failed to establish: the 5.16M-post study's identity (not named in a way I could load), and any primary TikTok document for the batch-size denial, which is argued from absence.

**https://www.zoomsphere.com/reach-myths** (ZoomSphere, first published 27 Sep 2026, last verified 30 Oct 2026)
- Said: an on-record myth register keyed to dates, Mosseri on 30 Oct 2026 that taking a post off the grid does not affect the reach of anything else you post, only that the removed post loses profile visits; repeated trial re-posts of the same reel are "just sort of a bad growth hack"; scheduling does not hurt reach (23 Oct 2026); hashtags are for categorisation and search, not distribution (May 2025); "warming up the algorithm" is "just a rumour" (Sep 2025); also names watch time, likes per reach and sends per reach as Mosseri's recommended metrics.
- Failed to establish: the primary video, since these are Instagram Stories AMAs compiled by a vendor; the page itself warns they are one executive's statements, not verified platform policy. This is the weakest load-bearing source in the set and drove the contested rating on metr-delete-underperformers.

**https://www.socialmediatoday.com/news/instagram-chief-shares-algorithm-insights-and-posting-tips/831326/** (Social Media Today, Andrew Hutchinson, 24 Sep 2026)
- Said: Instagram's own framing is that without ranking the feed fills with accounts that post far more than creators do; ranking predicts "whether they're likely to watch it, share it with a friend"; Instagram tests small public creators' content with non-followers "with a view to boosting posts from new creators"; Mosseri advises engagement rate over total views or likes, and posting as often as possible without burning out.
- Failed to establish: delete/repost guidance (not addressed) and any numeric signal. Independent trade press quoting Instagram's published videos, so secondhand but not vendor-self-serving.

**https://democraticmedia.org/publishings/first-5-seconds-creating-youtube-ads-break-through-skippable-world** (Center for Digital Democracy summary of Google/Think with Google, 18 Jun 2015)
- Said: the origin of the "first seconds" genre of advice in measurable form, thousands of TrueView ads across 16 countries and 11 verticals sorted by 170 creative attributes, watch behaviour from aggregated AdWords analytics, brand awareness from Google Brand Lift, and the point that the five-second skip button forces the whole story to work up front.
- Failed to establish: the actual findings numbers (only qualitative on this mirror) and any transferability, since it is 2015 skippable in-stream advertising on YouTube, not organic short video. Used in metr-3-second-hook-rule to show where the earliest real "seconds" research actually sits.

## Tried and rejected (never cited)

- `https://www.tiktok.com/creator-academy/en/article/tool-analytics-intro` - body did not render (JS shell only), so TikTok's own metric definitions for average watch time and completion remain unread. This is the single biggest hole in the set.
- `https://help.instagram.com/202865988324236/` (View insights on your Instagram reels) - same, Help Center returned only CSS/config. The "watch time includes replays" definition therefore leans on Sprout's documentation instead of Instagram's.
- `https://help.x.com/en/resources/recommender-systems/for-you-home-timeline-recommendations` - 403 Forbidden.
- `https://help.x.com/en/using-x/x-timeline` - 403 Forbidden. No official X help page could be read, so every X claim rests on the GitHub README plus secondhand source reads.
- `https://www.facebook.com/business/help/1792720544284355` (About video ad metrics) - Meta's official definition of 3-second video plays never rendered; I did not cite the metric even though it is very likely the paid-media ancestor of the 3-second rule.
- `https://ads.tiktok.com/business/zh/blog/creative-best-practices-top-performing-ads` - TikTok's own creative best practices page returned styling only, so the "90% of ad recall in six seconds" line is carried as secondhand via Superside.
- `https://business.google.com/aunz/think/marketing-strategies/creating-youtube-ads-that-break-through-in-a-skippable-world/` - 404.
- `https://www.thedrum.com/news/new-report-debunks-social-media-s-3-second-rule-and-other-creator-myths` - empty body. The "Creator Instinct" report (5,000 creator assets, 77 brands, US/UK, front-loading brand cuts view rates ~44%) exists and is directly on question 3 and 6, but I could not read it from any source, so it is NOT cited anywhere.
- `https://www.netinfluencer.com/front-loading-brand-pitches-cut-social-view-rates-by-44-percent-research-finds/` - headline only, body was JS/CSS. Same report, same reason for exclusion.
- `https://medium.com/inst414-data-science-tech/does-posting-time-really-matter-on-tiktok-af9477b1fa54` - 403. Would have been a useful independent 28,844-post test of posting-hour effects.
- `https://dl.acm.org/doi/10.1145/3613904.3642433` (Analyzing User Engagement with TikTok's Short Format..., CHI 2024) - 403. Its "attention remains stable at around 45%" figure is therefore not cited.
- `https://pubmed.ncbi.nlm.nih.gov/37640135/` and `https://www.researchgate.net/publication/373430867_...` (Rein et al. 2023, 150 TikTok videos, retention predicts views) - cookie wall and 403 respectively, so the only real per-video retention-vs-views study in this space stayed unread and is not cited.
- `https://ceur-ws.org/Vol-3590/short2.pdf` (Formulating Video Watch Success Signals) - PDF streams undecoded, no readable text.
- `https://get.rivaliq.com/hubfs/eBooks/2024-Rival-IQ-Social-Media-Industry-Benchmark-Report.pdf` - PDF binary, undecoded. Would have been the best independent-ish vendor benchmark with a stated sample.
- `https://support.google.com/youtube/answer/9314415` (audience retention report) - styling only, no article text.
- `https://publora.com/blog/x-algorithm-open-source` - CSS only.
- `https://admanage.ai/blog/what-is-a-good-hook-rate-for-facebook-ads` - truncated before the benchmarks, so no hook-rate percentile is cited.
- `https://buffer.com/resources/instagram-reach-engagement-analysis/` - my fetch attempt 403'd (bad URL construction on my side); I did not retry, so the Reels-vs-carousel reach comparison is absent from the playbook.
- All `facebook.com/adam/...` and `instagram.com/reel/...` results (Mosseri's original AMA posts, TikTok's own recap videos) - login/JS walls; these are why metr-delete-underperformers is contested rather than proven.

## Questions answered, and the ones that are not

1. Retention / watch-through benchmarks: **partially answered, no platform-official number exists.**
   No platform publishes a retention curve, average watch percentage, or completion benchmark for
   short video. What exists is (a) two qualitative official statements, (b) Wistia's share-watched
   by length for hosted business video with the actual percentages locked in a chart image, and
   (c) vendor corpora (buzzabout, Socialinsider) that disagree with Wistia's direction. Recorded as
   metr-retention-benchmark-gap, contested.
2. Follower conversion (view to profile visit to follow): **not answered with a real rate.** The
   metric exists in Instagram's per-Reel panel and TikTok's analytics, but not one published
   view-to-follow or profile-visit-to-follow rate with a stated method turned up. The numbers in
   circulation (0.10-0.25%, "2%") are self-declared heuristics by the vendors who publish them.
   Recorded as metr-view-to-follow-rate, folklore.
3. Origin of the 3-second hook: **no primary origin found.** Traced to ad-reporting artifacts,
   Meta's 3-second video plays (definition unreadable, so noted only as a suspicion, not a claim)
   and Google's 2015 TrueView "first 5 seconds" work, plus TikTok's own ad-recall figure which is
   six seconds and internal, while tool vendors label the 3-second rule a rule of thumb. Recorded
   as metr-3-second-hook-rule, folklore, which is the deliverable rather than a failure.
4. Rewatch / loop / full-view rate: **official statements yes, effect on distribution no.** TikTok
   names finishing a long video as a strong interest signal and mentions replays only as a seed
   signal; Instagram's Reels predictions include watching all the way through. Whether a short
   looping clip is structurally advantaged is contradicted inside the platforms' own research,
   since ByteDance's watch-time papers say raw watch time biases toward longer videos and that
   average watch percentage falls as duration rises. Recorded as metr-completion-signal (proven)
   and metr-watch-time-duration-confound (proven for the measurement trap).
5. Comments/shares/sends vs likes: **directionally answered, weights not.** Instagram's official
   text puts reshare and watch-through among the predicted actions; X's released code reportedly
   weights replies and author-engaged replies far above likes; but the X weights are 2023, the 2026
   release publishes none, and on TikTok likes are 90.9% of recorded engagement. Recorded as
   metr-shares-over-likes, contested.
6. Contradicted folk advice: **answered for two of three.** Posting at a magic hour survives only
   as a small unquantified effect against cadence, which has measured numbers (metr-cadence-beats-clock).
   Deleting underperformers is contradicted by Mosseri on record and by TikTok's duplicate-content
   stance (metr-delete-underperformers), but only via vendor compilations, so it is contested. The
   3-second rule is handled in item 3. Still un-answered: whether TikTok's "first 200-500 accounts"
   batch exists, because the debunk I found (Cut.Pro) argues from absence and TikTok has published
   nothing either way; I left it out rather than cite a negative.

## Audit notes for whoever reads this next

- Commissioning is stated in does_not_claim for the two vendor-run studies that carry numbers:
  Buffer ran its own samples on posts scheduled through Buffer, and buzzabout/Socialinsider sell
  the analytics their benchmark posts advertise.
- Nothing in these files cites example.com. `Store.load()` on `data/playbook/` returned clean when I
  ran it at 14:06 on 2026-11-12. Note that the two scaffold files that were there when I started
  (`hook-first-second.md`, `watch-time-dominates.md`, both with PENDING placeholder URLs) had been
  replaced by another worker's `mech-*.md` entries before that run, so this directory is being
  written to concurrently and my clean-load result describes the whole folder, not only my files.
  My own eight files each validate to `[]` on their own.
- Possible duplication to review when merging: `mech-watch-through-is-a-named-input.md`,
  `mech-follower-count-not-a-gate.md` and `mech-test-batch-and-fyp-hashtag-folklore.md` cover ground
  adjacent to my metr-completion-signal, metr-view-to-follow-rate and metr-3-second-hook-rule.
- Oldest source in the set is 2015 (Google/YouTube TrueView, used only as a provenance exhibit);
  the two platform-official explainers are 2020 and 2023 and are the likely first entries to go
  stale in practice even though as_of is fresh.
