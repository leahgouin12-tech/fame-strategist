# Playbook myths — research log

Researcher: web research agent. Date: 2026-11-12.
Scope: posting cadence, hashtags, search signals, best time to post, delete/repost, first-hour engagement, and enforcement.
Output: 10 files in `data/playbook/` prefixed `myth-`.

## Method note — read this before auditing

Three of the citation rules in the brief conflicted with how these sites actually behave, so I
want to be explicit about what I did rather than let it look like a clean WebFetch run.

1. **Instagram Help Center and X Help Center do not render to WebFetch.** `help.instagram.com`
   and `help.x.com` either return a CSS/JS shell or 403. I verified the URL was real by
   WebSearch, then retrieved the served HTML with `curl` and extracted the article text from
   the embedded payload (Instagram), or read the page through a Wayback Machine capture of the
   same canonical URL (X, and two TikTok policy pages). Every URL I cite is the **canonical
   platform URL**, and every quote in the entries was read from the bytes of that page as
   delivered on 2026-11-12. Where I used Wayback I fetched
   `web.archive.org/web/2026/<canonical>` and the capture rendered the live page text.
2. **One URL is a language variant.** The TikTok For Business cadence line was surfaced by
   WebSearch as `.../business/zh/blog/...`. I cited that exact URL and separately confirmed the
   `/en/` variant of the same article carries the identical sentence.
3. Nothing is cited that I did not read. Where I could not read it, it is in the REJECTED
   section below and it is not in any entry.

---

## LOADED AND KEPT

### TikTok — platform official

- **https://www.tiktok.com/community-guidelines** (read via 2026-06-25 Wayback capture)
  States that content falling under the "FYF Ineligible" standards "won't be recommended in the
  FYF", that TikTok does not allow "reposts of copyrighted or trademarked material without
  permission", and bans "the trade of services that artificially boost engagement or trick the
  recommendation system". Also documents AI-content labelling requirements.
  *Did not establish:* the detailed unoriginal-content and search-visibility sections were
  truncated; the overview page alone cannot carry the enforcement claim.
- **https://www.tiktok.com/safety/en/policies-and-engagement/integrity-authenticity** (read via
  2026-06-25 Wayback capture) — the load-bearing TikTok enforcement page. Says "Content is also
  ineligible for the FYF if it includes unoriginal or reused material without anything new";
  enforcement options include "Restrict your account, which could include limiting your ability
  to post new content, appear in top search results, or in the FYF"; "We strictly prohibit
  automation tools, scripts, or other tricks designed to bypass our systems"; inauthentic
  metrics get removed ("fake likes, followers, or other inflated signals").
  *Did not establish:* the amount of editing that converts reused footage into original
  material, and the duration of any restriction.
- **https://newsroom.tiktok.com/en-us/how-tiktok-recommends-videos-for-you**
  Names the ranking inputs: user interactions, and video information "like captions, sounds, and
  hashtags"; device and account settings carry lower weight. Says follower count and past
  high-performing videos are **not** direct factors in the recommendation system.
  *Did not establish:* anything about posting frequency (the word never appears), and nothing
  about on-screen text or spoken audio being indexed. Also a 2020 document, so its signal list
  may be behind the live system.
- **https://newsroom.tiktok.com/en-us/learn-why-a-video-is-recommended-for-you** (2022-12-20)
  TikTok's "Why this video" explainer: reasons given are user interactions (watch, like, share,
  comment, search), accounts followed or suggested, and recent/popular content in your region.
  *Did not establish:* watch time or completion as a named signal, and captions/hashtags are not
  mentioned at all — which weakens rather than strengthens the "TikTok reads your text" story.
- **https://newsroom.tiktok.com/more-ways-to-discover-new-content-and-creators-you-love?lang=en**
  (2025-06-03) Manage Topics, AI Smart Keyword Filters (keyword filter limit doubling to 200;
  200M+ words filtered from feeds), "strict For You feed eligibility standards".
  *Did not establish:* any statement about unoriginal or reposted content — I looked specifically
  for it and it is not in the post.
- **https://ads.tiktok.com/business/zh/blog/tiktok-creative-ultimate-guide** (TikTok For
  Business, published 2021-10-08, last modified 2023-04-06; `/en/` variant confirmed identical)
  The only platform-published per-day number I found anywhere: "Aim to post 1-4 times per day to
  test how different types of content are received."
  *Did not establish:* that this is a ranking insight. It is 2021 advertising-product creative
  guidance aimed at advertisers with media budgets, it carries no data, and it says "to test",
  not "to earn distribution".

### Instagram — platform official

- **https://help.instagram.com/1800814370401535/** "About original content on Instagram". Read
  from the served HTML (WebFetch returned only the app shell; curl returned the full article).
  Says "We encourage people on Instagram to post original content to get the best reach and
  distribution"; "When you have a role in producing your own content ... you may see increased
  reach and distribution compared to content that may be flagged as unoriginal"; unoriginal =
  "re-shared without a material edit, or if the account that posted it had no role in creating
  it"; explicitly lists "Logos, watermarks, or simply providing attribution", "Video
  compilations without material edits", and "Content that the account did not film or produce;
  with minor or immaterial edits"; documents the "Original by" label.
  *Did not establish:* a stated penalty. The page frames this as a reach incentive and a credit
  mechanism, not as enforcement — the enforcement half comes from the Recommendations page below.
- **https://help.instagram.com/313829416281232/** "Recommendations on Instagram" (the
  Recommendation Guidelines). "Our Recommendations Guidelines are designed to maintain a higher
  standard than our Community Standards, because recommended content and connections are from
  accounts you haven't chosen to follow." Disqualifying categories quoted include "Unoriginal
  content that is largely repurposed from another source with only minor, immaterial edits",
  "Long captions unrelated to the underlying content and coordinated comment networks intended
  to artificially drive engagement and distribution", and accounts that "Repeatedly engaged in
  misleading practices to build followings, such as purchasing 'likes'".
  *Did not establish:* how much distribution is lost, and the page never uses the phrase
  "engagement pod".
- **https://help.instagram.com/351460621611097/** "Use hashtags on Instagram". Entirely
  mechanical: where you can put a hashtag, that a tagged post appears on the hashtag page, that
  numbers are allowed and spaces/special characters are not.
  *Did not establish:* **this is the important negative result.** The official page states no
  hashtag count limit, no recommended count, and makes no reach or discovery promise whatsoever.
  Every "Instagram recommends N hashtags" claim in circulation is not sourced from here.
- **https://about.instagram.com/blog/announcements/instagram-ranking-explained** Feed/Stories/
  Explore/Reels ranking. Explore signal text: "how many and how quickly other people are liking,
  commenting, sharing, and saving a post. These signals matter much more in Explore than they do
  in Feed or in Stories." Feed: "how popular a post is – think how many people have liked it and
  how quickly people are liking, commenting, sharing and saving a post." Reels: Instagram makes
  reels "less visible for other reasons, such as low-resolution or watermarked reels, reels that
  are muted or contain borders, reels that are majority text, or reels that have already been
  posted on Instagram." Account-level: "If an account repeatedly posts content that goes against
  our Recommendation Guidelines or Community Standards, none of their posts will be eligible for
  recommendation for a period of time." Account Status shows whether content is "eligible to
  appear in Search or as a suggested account". On shadowbanning, Instagram says unexplained
  suppression is "not our intention".
  *Did not establish:* there is **no Search section on this page** — no statement that captions,
  alt text or keywords are matched against queries; and no posting-frequency guidance at all.
- **https://about.instagram.com/blog/announcements/shedding-more-light-on-how-instagram-works**
  (2021, kept only for two sentences the 2023 post dropped) Instagram tries "to avoid showing too
  many posts from the same person in a row", and most people "look at less than half of their
  Feed" — the two official statements that cut directly against a high-volume cadence strategy.
  Also: watermarked, low-resolution, muted, bordered and text-heavy reels are not recommended.
  *Did not establish:* current-state ranking detail; the post itself points readers to the 2023
  version. No cadence numbers.
- **https://creators.instagram.com/blog/tips-for-improving-your-reach** Instagram's own creator
  guidance. "Get discovered via Search" with the instruction to "include relevant keywords in
  your content, your caption, your bio, and your hashtags". Defines engaging content as
  "content you created yourself or content that hasn't been posted on Instagram before", and
  warns Instagram is "less likely to recommend reposts of a reel that's already on Instagram".
  Also: "Keep your reels short. In order to be recommended, they must be 3 minutes or less."
  *Did not establish:* any posting frequency or consistency guidance — the page has none, which
  is why the consistency claim stays contested.
- **https://about.fb.com/news/2024/12/trial-reels-try-content-non-followers-first-see-what-perfoms-best/**
  Trial reels: "shown to non-followers first", not placed on your grid or Reels tab, ~24h of
  views/likes/comments/shares data, then one tap to "share with everyone", or auto-release if it
  performs well in the first 72 hours.
  *Did not establish:* whether deleting an existing post has any cost. Meta never addresses
  deletion here; it only ships a testing surface, which is the sanctioned alternative.

### X — platform official

- **https://help.x.com/en/rules-and-policies/authenticity** (read via Wayback capture) Prohibits
  "coordinating to exchange engagement in any X features, such as Likes, Polls, Replies,
  Reposts, Lists, Views, or Follows", "coordinating with and/or compensating others to conduct
  account metric inflation", "follow churn", "indiscriminate following", "Trading, buying,
  selling ... or soliciting access of X accounts", and mass-registered accounts; permits up to
  ten accounts for non-duplicative purposes. Enforcement menu explicitly includes **"Restricting
  Reach"**, defined as "excluding posts from search results, trends, and recommended
  notifications", removing posts from For You and Following timelines, limiting discoverability
  to the author's profile, restricting interactions, and downranking in replies; plus anti-spam
  challenges, temporary loss of features, and suspension (permanent at first detection for
  severe cases).
  *Did not establish:* numeric thresholds of any kind, and it never uses the term "engagement
  pod".
- **https://help.x.com/en/rules-and-policies/x-automation** (Wayback) "You may not follow or
  unfollow X accounts in a bulk, aggressive, or indiscriminate manner." "You may not post
  duplicative or substantially similar posts on one account or over multiple accounts you
  operate." Keyword-based auto-replies are not allowed; replies require opt-in, easy opt-out, at
  most one reply per interaction, and must respond to the user's original post; following is not
  sufficient opt-in; AI reply bots need prior written approval. "Use non-API-based forms of
  automation, such as scripting the X website" is prohibited and "can result in the permanent
  suspension of your account". Bulk/aggressive/spammy Reposting is a violation.
  *Did not establish:* a safe posting volume for a human-run account.
- **https://help.x.com/en/rules-and-policies/x-rules-and-best-practices** (Wayback; direct fetch
  403'd) "Automated proactive following and automated un-following are not allowed." Repeated
  duplicated unsolicited replies "is considered spam behavior"; "We may filter accounts from
  search if they're degrading the search experience".
  *Did not establish:* any engagement-pod rule beyond the account-behaviour framing.
- **https://help.x.com/en/using-x/x-follow-limit** (Wayback) Concrete numbers, the only ones in
  this whole research set: "Every X account can follow up to 5,000 accounts", "Every X account is
  able to follow up to 400 accounts per day", a dynamic follower:following ratio cap, and account
  lock/limitation "including due to aggressive follow behavior". Abusive following "may result in
  the suspension of your account".
  *Did not establish:* an unfollow-specific pace cap. X states no number for unfollowing.

### Studies (vendor-commissioned; vendor named every time)

- **https://buffer.com/resources/best-time-to-post-on-tiktok/** — Buffer, 2026, ~7.1M TikTok
  posts published through Buffer, metric is median engagement rate. Findings: Sunday 9 a.m. top
  slot, Saturday best day, 6–11 p.m. evening peak. Caveats quoted: "Timing isn't a magic bullet",
  "Timing can help, but it's rarely the main reason a video underperforms", and on cadence
  "Posting consistently matters more than posting every single day." Also the practitioner
  source for the first-hour belief ("especially within the first hour or so").
  *Did not establish:* account count or date range (neither is stated), and Buffer only observes
  Buffer-scheduled posts, which skews to brands and social managers.
- **https://buffer.com/resources/when-is-the-best-time-to-post-on-instagram/** — Buffer, 2026,
  9.6M Instagram posts from 200,000+ accounts across 10 platforms, Jan 2024–Dec 2025, median
  engagement rate normalised to local time. Thursday 9 a.m., Wednesday noon, Wednesday 6 p.m.
  Buffer's own caveat: "Content quality still matters most, but timing meaningfully shifts
  reach" and timing is "the cherry on top of your strategy, not the cake itself".
  *Did not establish:* an effect size. "Meaningfully shifts" is never quantified.
- **https://buffer.com/resources/instagram-algorithms/** — Buffer's ranking guide. Reports
  Mosseri's three signals (watch time, likes per reach, sends per reach) with his wording
  "slightly more important"; states "It's official: hashtags don't help reach"; says Instagram
  capped hashtags at five; and reports that "Dumping several posts in a row can cause Instagram
  to hide some of them to keep feeds balanced." Buffer's separate claim that consistent posters
  get ~5x more engagement is explicitly Buffer's own study, not Instagram's.
  *Did not establish:* a retrievable primary document for the Mosseri statements — they are
  Instagram Q&A reels/posts, which do not render outside login. I therefore used this page only
  as a practitioner source and never as the citation for an enforcement claim.
- **https://sproutsocial.com/insights/how-often-to-post-on-social-media/** — Sprout Social,
  methodology stated on-page: "nearly 3 billion messages from 1 million public social profiles",
  window 2024-02-01 to 2025-01-31, plus a Cint survey of 4,400 consumers. Instagram 1-2/day,
  X ~2/day (down from 3-4 in 2022), and for TikTok Sprout explicitly says it "doesn't yet have
  our own posting frequency data" and defers to TikTok's 1-4/day line, citing RivalIQ's 2024
  finding that the average brand posts ~2 videos a week. Brands overall dropped from 11 to 9.5
  posts/day, which Sprout reads as "quality over quantity".
  *Did not establish:* a cadence-to-engagement curve. It reports what brands do, not what
  happens to reach when you post more. Brand accounts, not 0-follower creators.
- **https://sproutsocial.com/insights/best-times-to-post-on-social-media/** — Sprout, 2026,
  "nearly 2 billion engagements across roughly 307,000 social profiles" from 30,000+ Sprout
  customers, window 2025-11-27 to 2026-02-27. TikTok peaks Tuesday–Friday 2–6 p.m. and
  **Sunday is named the weakest day**.
  *Did not establish:* independent verification — Sprout commissions, analyses, and sells a tool
  (ViralPost) built on this exact conclusion. Kept specifically as the contradiction to Buffer.
- **https://metricool.com/press-release-instagram-study-2026/** — Metricool, 2026, "24,364,803
  Instagram posts from 375,118 accounts worldwide between January–February 2025 and
  January–February 2026". Findings used: posts using at least one hashtag saw "31.70% fewer views
  and 33.89% fewer interactions than the platform average"; brands published "24.04% more content
  YoY"; "most Instagram views happening in the first three days after posting"; Reels pull more
  than 4x the interactions of single images.
  *Did not establish:* causation. Metricool's own researchers are quoted elsewhere describing the
  hashtag result as correlation, and the press release does not control for account size — small
  accounts may be the ones using more hashtags.

### Practitioner (cited only as an example of the folklore, never as support)

- **https://www.hooked.so/blog/how-many-tiktoks-should-i-post-a-day** — Shows exactly how the
  cadence numbers mutate: repeats TikTok's "1 to 4 times per day" as "TikTok's own guidance",
  calls "2-4x per day" the sweet spot, claims top creators at 2-3/day see "roughly 45% higher
  engagement", and gives "3-5 times a day" for fashion/beauty niches.
  *Did not establish:* any source. It names no study and links none; the 45% figure is
  unverifiable. This page is the evidence that the folklore is unattributed, not evidence about
  posting.
- **https://revive.social/social-search-optimization/** — Asserts "TikTok transcribes and indexes
  what you *say*" and "Text overlays are indexed too".
  *Did not establish:* any primary TikTok documentation, patent or help page for those indexing
  claims — I checked and the article cites none. Kept in one entry precisely to mark the boundary
  between what TikTok documents (captions, sounds, hashtags) and what bloggers claim it does
  (spoken audio, on-screen text).

---

## TRIED AND REJECTED

- **https://support.tiktok.com/en/using-tiktok/exploring-videos/how-tiktok-recommends-content** —
  302 to `www.tiktok.com/support/faq_detail?id=7655285288050104852`, which serves a 1.5 KB JS
  shell plus CDN config with no article text, via WebFetch, via curl, and via redirect-following
  curl. The snippet claiming this page covers how search results are ranked could not be verified.
  Rejected; used the two newsroom posts instead.
- **https://support.tiktok.com/en/safety-hc/account-and-user-safety/why-is-my-account-not-being-recommended**
  — same JS-shell problem, and its Wayback capture is only a "HTTP 302 response at crawl time"
  stub with no content. Rejected despite being the ideal primary source for TikTok's
  "Ineligible for recommendation" notice.
- **https://www.instagram.com/reel/C6Y0tfRLyfa/** — Instagram's own post stating "when we find
  reposted content in recommendations, we will replace it with the original" and "we'll also add
  a label to the repost". Search surfaced the text, but the page will not render outside login
  (WebFetch returned only CSS variables). Rejected; the identical policy is documented on the
  fetchable help.instagram.com originality page, which I cite instead.
- **https://help.instagram.com/262333384912000** (Instagram Community Guidelines) — no Wayback
  snapshot available and direct fetch blocked. Rejected.
- **https://www.facebook.com/help/147542625391305** ("Why search engines might index public
  Instagram photos and videos") — facebook.com blocks non-JS fetches and there is no Wayback
  snapshot. This was my candidate for the Google-indexing question and I could not read it, so
  that question is reported as unanswered below.
- **https://help.instagram.com/151165638714232** — fetched successfully but it is a generic app
  shell (route manifests, no article body). Rejected.
- **https://www.fanpagekarma.com/insights/do-instagram-hashtags-work/** — search said "1.6 million
  Instagram posts ... posts with 5 hashtags achieve 2% more reach", but WebFetch returned only
  metadata and curl returned the Elementor JS bundle with no article body. Rejected outright: it
  would have been the counterweight to Metricool's negative hashtag finding, and without reading
  the methodology I cannot report the sample, the date range, or the metric. The hashtag entry is
  weaker for its loss and I have left it contested rather than calling it proven either way.
- **https://metricool.com/instagram-research-study/** — WebFetch got the header and the meta
  description sample size only; the findings body was truncated before any result. Rejected in
  favour of Metricool's press release for the same study.
- **https://kompozy.io/research/best-time-to-post-index** — "The 2026 Best-Time-to-Post Index"
  looked like exactly the cross-vendor meta-analysis needed, but the page returns only Tailwind
  CSS. Rejected.
- **https://x.com/en/rules** — returns a "JavaScript is not available" shell. Rejected;
  help.x.com policy pages used instead.
- **Direct WebFetch of help.x.com (both pages)** — 403 Forbidden on the live host and on `curl`
  with a browser UA. Rejected as a retrieval route; the canonical URLs are kept because their
  content was read in full from Wayback captures of those same URLs.
- **Direct WebFetch of help.instagram.com (three articles)** — CSS/JS shell only. Rejected as a
  retrieval route; content obtained from the served HTML via `curl`.
- **https://r.jina.ai/... reader proxy** — 401, "blocked from performing anonymous queries due to
  bad network reputation". Rejected; no third-party summariser used anywhere in this set.
- **TikTok official page on deleting or editing a published video** — searched four times with
  different phrasings; no `support.tiktok.com` or newsroom page surfaced at all, only third-party
  blogs and creator videos. Not fabricated; the question is reported as unanswered below.

---

## QUESTIONS I COULD NOT ANSWER FROM A REAL SOURCE

1. **TikTok indexing of on-screen text and spoken audio.** No platform page found. Every source
   making this claim is a blog, and the one I read cites nothing. TikTok officially documents
   only "captions, sounds, and hashtags" as video information, in a 2020 newsroom post.
2. **Instagram's official statement on how Instagram Search matches queries to caption or alt
   text.** The ranking blog has no Search section, the hashtag help article says nothing about
   discovery, and the one page that might have (`facebook.com/help/147542625391305`) would not
   load. The closest official statement is the creator-tip "include relevant keywords in your
   content, your caption, your bio, and your hashtags", which is advice, not documentation.
3. **TikTok on deleting an underperforming video, editing a published post, or re-uploading your
   own content.** Nothing official exists in what I could retrieve. The delete/repost entry is
   therefore built entirely on Instagram evidence and applies to TikTok only by extrapolation,
   which its `does_not_claim` says.
4. **A primary origin for "3-5 times a day".** The trail ends at unattributed blogs. The nearest
   traceable platform number is TikTok's 2021 For Business blog saying 1-4 per day **for
   testing**, and TikTok's own recommendation explainer never mentions frequency.
5. **Any measured effect size for posting time or for posting frequency.** No vendor publishes
   one. Buffer says "meaningfully shifts" without a number; Sprout and Metricool report medians
   without confidence intervals; nobody controls for a zero-follower account, which is the exact
   situation this app serves.
6. **The phrase "engagement pod" in any platform policy.** X, Instagram and TikTok each prohibit
   the behaviour in different words (coordinated engagement exchange; coordinated comment
   networks; trade of services that artificially boost engagement). No platform uses the term, so
   the safety gate should match on behaviour, not vocabulary.
7. **A published cadence or consistency signal.** No platform confirms that regularity itself is
   ranked. The strongest available evidence is Instagram's statements that it suppresses
   back-to-back posts from one account and that most users see less than half their Feed — both
   of which argue against volume rather than for streaks.
