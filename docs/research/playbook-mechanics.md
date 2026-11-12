# Research log — platform distribution mechanics (Task 2)

Scope: official statements only, on what gates distribution of a post on TikTok, Instagram Reels and X.
Date of research: 2026-11-12. Agent: web research for `data/playbook/mech-*.md`.

Rule followed: a URL is only cited if it appeared in my own WebSearch results **and** I then read the
page. Pages that 404'd, 403'd, or rendered only scripts/CSS are listed under "tried and rejected" and
are **not** cited anywhere in the playbook.

## Entries written (8)

| file | confidence | platform_official sources |
| --- | --- | --- |
| mech-watch-through-is-a-named-input.md | proven | 3 |
| mech-no-published-metric-weighting.md | contested | 2 |
| mech-follower-count-not-a-gate.md | proven | 3 |
| mech-test-batch-and-fyp-hashtag-folklore.md | folklore | 2 |
| mech-posting-volume-not-recommended-away.md | strong | 1 |
| mech-reused-content-is-recommendation-ineligible.md | proven | 3 |
| mech-x-reaches-past-your-followers.md | proven | 2 |
| mech-x-links-reach-contested.md | contested | 1 |

Confidence distribution: 4 proven, 2 contested, 1 strong, 1 folklore. 17 of 24 source lines are
`platform_official`.

## URLs loaded and kept

1. **https://newsroom.tiktok.com/en-us/how-tiktok-recommends-videos-for-you** — "How TikTok recommends
   videos #ForYou", dated 2020-06-18, still live.
   *What it says:* recommendation factors are user interactions ("the videos you like or share, accounts
   you follow, comments you post, and content you create"), video information ("captions, sounds, and
   hashtags"), and device/account settings ("language preference, country setting, and device type")
   which get "lower weight ... relative to other data points we measure" because users do not actively
   express them; factors are "weighted based on their value to a user", so "whether a user finishes
   watching a longer video from beginning to end" gets "greater weight than a weak indicator, such as
   whether the video's viewer and creator are both in the same country"; and "Neither follower count nor
   whether the account has had previous high-performing videos are direct factors in the recommendation
   system."
   *What it fails to establish:* any numeric weighting; watch history, replays, shares-per-reach or
   follows-from-view as named metrics; anything about session length, demographics, or per-video vs
   per-account eligibility. It is also a 2020 document that TikTok has not revised, so I did not let it
   carry any "current weighting" claim.

2. **https://newsroom.tiktok.com/en-us/5-tips-for-tiktok-creators** — "5 tips for TikTok creators",
   2020-07-30.
   *What it says:* "Vertical videos perform best on TikTok, as do videos that are longer than five
   seconds"; "The amount of videos you post won't impact how your content is recommended in the For You
   feed"; "no one engagement metric is necessarily more important than another"; "Watch time factors into
   how a video gets recommended"; recommendations "generally pull from videos posted within the last 90
   days"; "hashtags like #FYP, #ForYou, and #ForYouPage work just like all other hashtags on TikTok" and
   adding them "won't necessarily improve your chances of getting on someone's For You feed"; use
   relevant hashtags, audio helps make videos "more discoverable and shareable"; "anyone can be a
   creator".
   *What it fails to establish:* how watch time compares to other metrics numerically (its "no one metric"
   line actually pulls the other way, which is why mech-no-published-metric-weighting is contested),
   whether the 90-day window is a filter or a description, and any official view on time-of-day posting.

3. **https://www.tiktok.com/safety/en/policies-and-engagement/fyf-standards** — "For You feed Eligibility
   Standards", released 2026-08-25, effective 2026-09-24.
   *What it says:* TikTok "make[s] ineligible for the FYF certain content that may not be suitable for a
   broad audience" and points to the "FYF Ineligible" labels inside the Community Guidelines; it tries to
   avoid repeatedly recommending content that may produce a negative experience ("extreme fitness or
   dieting, sexual suggestiveness, sadness, or overgeneralized mental health advice") and can interrupt
   repeats during "crisis or unrest"; users must be 16+ for videos to appear in the FYF; "not all content
   is guaranteed to be recommended"; creators "can check TikTok's analytics", including whether content
   was "made ineligible for recommendation"; non-recommended videos can still be found via search or the
   profile, and low views do not necessarily mean a rule was broken.
   *What it fails to establish:* the appeal route for FYF ineligibility and whether ineligibility is
   decided per-video or per-account (page body truncated mid-list); it does not mention unoriginal or
   reused content at all, so that claim rests on source 4.

4. **https://www.tiktok.com/safety/en/policies-and-engagement/integrity-authenticity** — "Integrity and
   Authenticity", released 2026-08-25, effective 2026-09-24.
   *What it says:* "You should only post content you created or have the right to share"; IP-violating
   content is not allowed and "If we become aware of content that breaks these rules, we will remove it";
   and "Content is also ineligible for the FYF if it includes unoriginal or reused material without
   anything new."
   *What it fails to establish:* definitions of the detection (watermarks, GIF-only compilations, screen
   recordings), the penalty ladder for unoriginal content, false-positive rates, and any account-level
   consequence — so the entry says "ineligible for recommendation", not "strike" or "ban".

5. **https://about.instagram.com/blog/announcements/instagram-ranking-explained** — "Instagram Ranking
   Explained", Adam Mosseri, 2023-05-31.
   *What it says:* Feed signal groups "roughly in order of importance" are your activity, information
   about the post, information about the poster, and your history of interacting with someone, and the
   interactions that matter most are "how likely you are to spend a few seconds on a post, comment on it,
   like it, share it, and tap on the profile photo"; format preference is now used ("if we notice you
   prefer photos, we'll show you more photos"); for Reels the predictions are "how likely you are to
   reshare a reel, watch a reel all the way through, like it, and go to the audio page", with signal
   groups ordered your activity, your history with the poster, information about the reel, information
   about the poster; in Explore "the most important actions we predict ... include likes, saves, and
   shares" and popularity signals "matter much more in Explore than they do in Feed or in Stories".
   *What it fails to establish:* the words "sends per reach", any "share-worthy" update, originality as a
   ranking factor, and any weight numbers. 2023 vintage, so I kept it to "what they name", not "what
   dominates today".

6. **https://creators.instagram.com/how-to-grow** — "How to Grow | Instagram for Creators".
   *What it says:* Instagram "doesn't have a singular algorithm" but different recommendation systems per
   surface; content can be excluded from recommendations for watermarks, reposting others' work, or
   overly long reels, and "Reels over 3 minutes won't be recommended to new audiences"; a reel is shown
   to followers and non-followers and is "initially shown to a small audience of people we think will
   enjoy it", with strong performers expanding — "designed to level the playing field by distributing
   content based on its engagement, not just the creator's follower count"; named signals are "watch time,
   retention, shares, likes, and comments"; warns against "Taking credit for content that isn't yours";
   technical advice is 720p/30fps minimum, hook "within the first 3 seconds", captions for sound-off
   viewing, and "Reels makes up over 50% of all time spent on Instagram".
   *What it fails to establish:* numeric weights, the metric name "sends per reach", and anything for
   TikTok or X.

7. **https://creators.instagram.com/blog/helping-creators-of-all-sizes-break-through** — "Helping creators
   of all sizes break through", 2025-02-26, article headline "Improving how reels are ranked and
   recommended".
   *What it says:* repeats the level-playing-field line and the small-audience-then-wider model; says
   recommendations offer "significantly higher upside today than in the past" and that
   recommendation-friendly creators will see "more of their overall reach ... come from non-followers";
   signals "watch time, retention, shares, likes, and comments"; April 2024 ranking updates; global video
   time up "double digit percentages year-over-year" in Q4 2024; reels reshared "over 4.5 billion times
   every day across Instagram and Facebook"; first-3-seconds hook with View Rate in Insights; case study
   @pov_husband, created April 2024, "over 1.2 billion views", "from 0 followers to over 2 million
   followers in less than a year".
   *What it fails to establish:* what share of a new account's reach actually comes from non-followers,
   and whether watch time outranks shares; it is Instagram writing about its own upward trajectory, so the
   growth numbers are self-reported.

8. **https://github.com/xai-org/x-algorithm** — repo "Algorithm powering the For You feed on X", README
   heading "X For You Feed Algorithm".
   *What it says:* the pipeline is query hydration → candidate sources (in-network via Thunder;
   out-of-network via Phoenix retrieval, SimClusters and popular posts) → candidate hydration → pre-scoring
   filters (duplicates, own posts, blocked/muted, muted keywords, seen/served, and an AgeFilter that drops
   "Posts older than 48 hours") → scoring → TopK selection → post-selection visibility filters → blending
   with ads, Who to Follow and prompts; scoring is "Final Score = Σ (weight_i × P(action_i))" over
   predicted actions: favorite, reply, repost, quote, share, share via DM, share via copy link, link /
   profile / photo / video-open clicks, quality view, dwell, dwell time, click dwell time, video
   continuation seconds, profile visit seconds, follow author, and negatives (not interested, mute, block,
   report, not dwelled); weights "do *not* scale the raw engagement counts" so a 468x report weight is not
   "1 report cancels out 468 likes"; then author-diversity decay, an out-of-network discount factor below
   1, and a new-author boost that lifts posts "from authors with few impressions"; visibility filtering
   returns ALLOW / NOTICE / INTERSTITIAL / DROP and some rules drop a recommended post from an unfollowed
   viewer while "The same post is allowed to a follower"; some rules are not in the repo, to reduce gaming
   risk.
   *What it fails to establish:* the actual weight values, the model's parameters and training data, and
   any written link/media/length policy; the README also distinguishes its config defaults from what runs
   in production without detailing the difference.

9. **https://github.com/twitter/the-algorithm** — "Source code for the X Recommendation Algorithm" (the
   March 2023 release).
   *What it says:* open-sourced services cover "the For You Timeline and Recommended Notifications";
   For You candidate sources are search-index, tweet-mixer, UTEG and follow-recommendation-service, and
   "search-index supplies ~50% of posts"; heavy ranker and TwHIN live in a separate ML repo; includes
   trust-and-safety-models and visibility-filters; AGPL-3.0.
   *What it fails to establish:* 2026 behaviour (this is why mech-x-reaches-past-your-followers names the
   ~50% figure as the earlier system in its does_not_claim), any gaming-risk statement, and any weight or
   link policy.

10. **https://www.heise.de/en/news/X-Releases-Timeline-Algorithm-Transparency-with-Gaps-11147699.html** —
    "X Releases Timeline Algorithm - Transparency with Gaps", 2026-01-20.
    *What it says:* the For You source code is on GitHub and is to be refreshed every four weeks; Thunder
    supplies in-network candidates and the Grok-based Phoenix predicts reactions, each multiplied by a
    weighting factor and summed; manual features were removed; but X "does not publish the specific
    weighting factors", nor Phoenix's parameters or training data — "one learns that Phoenix calculates a
    weighted sum of behavioral predictions - but not what exactly happens in the black box"; the release
    is framed against EU pressure including a 120 million euro fine over transparency deficiencies; quotes
    Musk: "We know this algorithm is dumb and needs massive improvements".
    *What it fails to establish:* any number, and whether links or media are deboosted.

11. **https://x.com/i/trending/2082323264748105828** — "X Confirms No More Penalties for Posts with Links".
    *What it says:* X ended link penalties more than a year ago; Nikita Bier, X's product head, on July 28:
    "you do not need to put the links in replies anymore"; Paul Graham on July 29: "You no longer penalize
    tweets with links in them?" and Musk: "We haven't for over a year"; the open-sourced ranking code shows
    no deboost for links; lower reach is attributed to people clicking away rather than to punishment.
    *What it fails to establish:* a published ranking rule in either direction — the page carries a
    disclaimer that its Grok summary can contain errors, which is precisely why the link entry is
    contested and not proven.

12. **https://postory.io/blog/x-algorithm-2026** — "Twitter/X Algorithm 2026: What xAI's Open-Sourced Code
    Shows", 2026-05-15 (modified 2026-11-11).
    *What it says:* "There is no hard-coded link penalty anywhere in the open-source release" and
    `CLICK_WEIGHT` is positive, so any demotion would be learned rather than coded; video only counts for
    the Video Quality View signal above `MIN_VIDEO_DURATION_MS`; a "banger" quality screen with
    `quality_score` / `slop_score` and a pass mark of `score >= 0.4`; accounts under 1,000 followers face an
    extra reply-spam screen and no social-proof badge (`VIEWER_FOLLOWERS_THRESHOLD: i64 = 1000`); follows
    rank highest among positive predictions, likes lowest-tier; reply-to-like ratios circulating online are
    "external estimates, not from the OSS". It cites repo files and line numbers.
    *What it fails to establish:* official confirmation of anything; it is one practitioner's code read and
    some thresholds are its own guesses, so it is tiered `practitioner` and only used to corroborate the
    contested link claim.

13. **https://posteverywhere.ai/blog/how-the-tiktok-algorithm-works** — "How the TikTok Algorithm Works in
    2026 (For You Page Ranking Signals)", 2026-03-23.
    *What it says:* debunks nine claims (needing followers, self-views, deleting underperformers,
    shadowbanning, posting-time guarantees, more posts = more reach, hashtag stuffing, teens-only,
    "hacking" the algorithm); quotes TikTok that neither follower count nor previous high performers are
    direct factors; states "TikTok doesn't publish how much each signal counts", so "watch time is 40-50%"
    or a "70% retention" bar are "a guess, not a fact"; the phased test rollout is something "creators and
    agencies describe" and "TikTok hasn't confirmed that"; "TikTok does not acknowledge shadowbanning"; its
    timing data is its own sample of 4,500+ scheduled TikToks.
    *What it fails to establish:* an official TikTok statement about test batches, first-minutes windows or
    shadowbanning — the article's value here is documenting the absence, which is why it supports the
    folklore and contested entries rather than a proven one.

14. **https://www.merra.ai/blog/when-should-i-post-tiktok** — "When Should I Post on TikTok?", 2026-07-25.
    *What it says:* TikTok "tests every video with a small audience the moment you post it, regardless of
    the hour" and "decides how far to push it based on their reaction"; rates posting time of day "Low to
    negligible"; "a great hook posted at 3pm beats a weak hook posted at the 'optimal' 7pm slot every time".
    *What it fails to establish:* any TikTok documentation for the test-group model — it cites only its own
    other articles, which is the concrete evidence that the staged-test story is folklore.

15. **https://ad2.app/blog/do-hashtags-still-work** — "Do hashtags still work in 2026? What platforms said",
    2026-08-04.
    *What it says:* hashtags are a labelling input, not a boost; for TikTok it points to the two newsroom
    posts behind the #FYP line; for Instagram it reports a December 2025 @creators announcement of a cap of
    up to five hashtags per reel or post, and Mosseri in April 2025 saying hashtags "don't significantly
    increase your reach"; for X it reports Musk on 2024-12-17 "Please stop using hashtags" while X's Help
    Center still recommends a maximum of two hashtags, an unresolved conflict it admits it cannot settle; it
    concedes no platform has published an optimal tag count.
    *What it fails to establish:* first-hand proof — some of its quotes are relayed through Social Media
    Today, and I could not load the Threads post or the help.x.com hashtag guidance. I used it only as a
    practitioner pointer inside the folklore entry, never as the basis for a proven claim.

16. **https://buffer.com/resources/social-media-frequency-guide/** — "How Often to Post on Social Media in
    2026: A Data-Backed Guide", 2026-01-13.
    *What it says:* TikTok 2-5 posts/week from Buffer's own data (up to "17% more views per post"),
    Instagram 3-5/week, X 3-4/day citing EverywhereMarketer's study of 30 top accounts, Facebook 1-2/day
    citing HubSpot's 13,500+ user survey; repeatedly caveats that these are "a rule of thumb, not social
    media commandments set in stone" and that "there's no universal 'right number'"; the only platforms
    quoted with direct guidance are Pinterest and the YouTube Creators channel.
    *What it fails to establish:* official cadence guidance from TikTok, Instagram or X — that absence is
    exactly why mech-posting-volume-not-recommended-away leans on the single TikTok sentence and calls the
    third-party numbers survey data.

## URLs loaded but NOT used as evidence

- **https://arxiv.org/html/2605.10690v1** — "When 'For You' Isn't For You: Measuring User Agency in
  TikTok's Algorithmic Feed" (Kaplan, Patel, Gerzon, Mislove, Sapiezynski; Northeastern; arXiv preprint
  dated 2026-05-11, ICWSM reviewers thanked but no confirmed peer review). Method: mobile-app audit with
  cloned sock-puppet accounts replaying identical watch histories across cooking, fitness and sports
  betting, 200 FYP videos per phase. Findings: seeded feeds reached 44.5% on-topic videos (89/200) for
  cooking and sports betting vs 8.5%/1.5% baselines; explicit "Not Interested" cut on-topic share far more
  than implicit skipping (84.4% vs 47.5% decrease in the cooking run); feeds relapsed when signalling
  stopped (all 5 implicit cooking runs); the control is "unintuitively buried in the interface".
  Not used: it measures user *control* over a feed, not what gates a creator's distribution, and it is an
  unreviewed preprint. Kept in the log as the closest thing to a real study I found on TikTok ranking.

## Tried and rejected (and why)

- **https://support.tiktok.com/en/using-tiktok/exploring-videos/how-tiktok-recommends-content** — 302 to
  `www.tiktok.com/support/faq_detail?id=7655285288050104852`, which returned only a JSON config dump
  (CDN URLs, region "US-TTP2", SDK versions) with no article text. Rejected; the newsroom post covers the
  same ground and rendered.
- **https://support.tiktok.com/en/safety-hc/account-and-user-safety/why-is-my-account-not-being-recommended**
  — 302 to `faq_detail?id=7543604783110969862`, same config dump. This was the page most likely to state
  TikTok's *account-level* ineligibility and appeal wording, so the eligibility entries rest on the two
  Community Guidelines pages instead and say nothing about appeals.
- **https://help.instagram.com/653964212890722/** ("Recommendation eligibility on Instagram") — WebFetch
  returned only CSS variables; `curl` gave HTTP 400. Rejected.
- **https://help.instagram.com/313829416281232/** ("Recommendations on Instagram") — same JS/CSS dump,
  HTTP 400 via curl. Rejected. This was the source for the "three categories of content allowed but not
  eligible for recommendations" list, so that list is deliberately absent from the playbook.
- **https://help.x.com/en/using-x/x-timeline**, **https://help.x.com/en/rules-and-policies/recommendations**,
  **https://help.x.com/en/resources/recommender-systems/account-recommendations** — HTTP 403 from both
  WebFetch and curl. Rejected; X's official eligibility wording is unverifiable from here, so the X entries
  cite the open-sourced repos and one x.com page instead.
- **https://www.axios.com/2023-10-03/musk-x-links-long-form** — 403.
- **https://www.niemanlab.org/2025/10/x-makes-overtures-to-journalists-with-new-feature-designed-to-improve-reach-for-links/**
  — 403.
- **https://techcrunch.com/2023-11-13/elon-musk-says-x-is-changing-its-algorithm-to-highlight-smaller-accounts/**
  and **https://techcrunch.com/2023-10-05/x-cuts-headlines-from-link-previews-as-musk-wants-users-posting-directly-on-the-platform/**
  — both 404 on the dashed and the slashed URL form my search returned; not retried, not cited. The
  underlying claims are covered by source 8 (new-author boost) and source 11.
- **https://kompozy.io/news/x-algorithm-link-penalty-posting-signals** — returned only Tailwind CSS and
  font rules, no body. Rejected in favour of the x.com trending page.
- Search hits I did not load because they are login-walled or non-official: `instagram.com/reel/DFdW_yPNUEP`
  and `instagram.com/reel/DFFyRp-pINJ` (Mosseri on average watch time and "sends ÷ reach"),
  `instagram.com/reel/DSaDo6YE5al`, `instagram.com/p/DXw3LpnlJFW`, all `facebook.com/fb-answers/*` pages,
  `reddit.com/r/TikTok*` threads, `youtube.com/watch?v=0XISsbJaH34`, `x.com/Megvii`, `x.com/TikTokComms`.
- **https://www.scribd.com/document/902855416/news-4-Introduction-to-the-Tiktok-recommendation-system** —
  a Scribd reproduction of a TikTok document, not the document host. Rejected as an unauthorized copy whose
  fidelity I could not check.
- Blogger pages that appeared repeatedly but that I did not cite because the primary pages superseded them:
  `blog.hootsuite.com/tiktok-algorithm`, `blog.hootsuite.com/instagram-algorithm`,
  `buffer.com/resources/instagram-algorithms`, `later.com/blog/how-instagram-algorithm-works`,
  `sproutsocial.com/insights/tiktok-algorithm`, `socialscheduler.ai/blog/tiktok-algorithm`,
  `go-viral.app/blog/tiktok-hashtag-strategy`, `shadowbanchecker.com/blog/tiktok-banned-hashtags`,
  `dashsocial.com/blog/tiktok-algorithm`, `socialpilot.co/blog/tiktok-algorithm`,
  `crossglobemarketing.com/blogs/instagram-original-content-algorithm-2026`, `shapelessai.com/notes/*`,
  `vamp.com/insights/*`, `mashable.com/article/instagram-algorithm-original-content-creators`,
  `influenceflow.io/*`, `zoomsphere.com/*`, `blossai.com/*`, `creatorflow.so/*`, `xpert.so/*`,
  `www.volts.wtf/feed` (irrelevant hit), `posteverywhere.ai` beyond the one page loaded.
- **https://newsroom.tiktok.com/en-sg/more-ways-to-discover-new-content-and-creators-you-love-sg** and
  **https://newsroom.tiktok.com/more-ways-to-discover-new-content-and-creators-you-love?lang=en** (2025-06-03)
  — loaded and read: For You is "the heart of the TikTok experience", behaviours that shape it are "liking
  and favoriting videos, searching for topics you're curious about, or simply enjoying content", new Manage
  Topics and Smart Keyword Filters, "strict For You feed eligibility standards to restrict content that
  isn't appropriate for a general audience", interruptions of repeated exposure. Not cited because it names
  no ranking signal and adds nothing load-bearing the eight entries do not already source.

## Questions I could not answer with a real source

1. **Instagram's "sends per reach" / "share-worthy" ranking update.** Repeated by Buffer, Hootsuite, Later,
   Sprout and in Mosseri's own reels, but every official page I could load says "reshare a reel" / "shares"
   and never "sends per reach". No entry asserts the metric name.
2. **Instagram's official recommendation-eligibility categories** (help.instagram.com) — blocked, so the
   "three categories allowed but not recommended" claim is missing from the playbook entirely.
3. **X's official Help Center description of For You ranking and recommendation eligibility** — 403. X's
   statements in the playbook come from the open-sourced code and one x.com trending summary, which is
   Grok-generated.
4. **Whether any platform officially says what it does NOT measure.** Only partial: TikTok's newsroom puts
   follower count and previous high performers outside the direct factors, its 2020 tips say no single
   engagement metric dominates, and X's repo says some rules stay unpublished to avoid gaming. I found no
   official sentence denying "shadowbanning" as a practice — only practitioners saying TikTok does not
   acknowledge the term — so that stays folklore.
5. **TikTok's account-level distribution limits** (the "why is my account not being recommended" article) —
   unreadable here; the eligibility entries are per-video only.

## Cut for the 8-file limit

- Instagram's official "Reels over 3 minutes won't be recommended to new audiences" plus the 720p/30fps and
  first-3-seconds specs (read on creators.instagram.com/how-to-grow, source 6). That would be a clean
  `strong`, single-official-source `format` entry for whoever owns the format questions.
- The TikTok official "recommendations generally pull from videos posted within the last 90 days" is folded
  into the cadence entry rather than standing alone.
