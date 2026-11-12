# Research log - playbook formats, niche choice, 0-to-growth cases

Task: 10 `form-*` entries in `data/playbook/` for a fame-strategist app (one person, 0 followers,
TikTok + Instagram Reels + X, niche not yet chosen).

Date of research: 2026-11-12. All `as_of` values in the entries are 2026-11-12.

Method: every URL below came out of my own WebSearch results and was then loaded with WebFetch.
Nothing was pasted from memory. "Loaded" means the fetch returned 200 with article text I could
actually read; several pages returned 200 but only a script/CSS shell, and those are listed under
rejected with what came back.

## Sources used (loaded, read, cited in an entry)

1. https://newsroom.tiktok.com/tiktok-and-amplify-launch-new-creator-led-content-series-for-brands?lang=en-AU
   - Says: TikTok x Amplify "The Next Episode" (13/14 Sep 2026) funds brand-backed creator episodic series; TikTok ANZ GM says demand for "longer-form, episodic entertainment continues to grow"; formats named are micro-dramas, interviews, game shows, docuseries.
   - Fails to establish: any viewer-side number. Zero statistics on episodic watch-through or follower behaviour; the demand claim is a press-release adjective.
   - Used in: form-storytime-episodic (platform_official).

2. https://newsroom.tiktok.com/tiktok-and-made-by-us-studios-enter-partnership-to-co-produce-creator-led-micro-series?lang=en
   - Says: 14 Oct 2026 partnership for premium vertical micro-series; prior series *Screen Time* "has amassed nearly 580 million views globally" since April; lists starring creators with counts (Hannah Stocking 29.7M, Adam Rose 7M).
   - Fails to establish: that episodic content works for an unknown creator. The 580M-view example is studio-produced and cast with people who already had tens of millions of followers.
   - Used in: form-storytime-episodic (platform_official).

3. https://newsroom.tiktok.com/en-us/how-tiktok-recommends-videos-for-you
   - Says: ranking groups are user interactions, video information, device/account settings; strong interest signals like finishing a longer video outweigh weak ones; explicitly "neither follower count nor whether the account has had previous high-performing videos are direct factors".
   - Fails to establish: how much initial test audience a 0-follower account gets, or any per-format behaviour. It is a 2020-era explainer with no numbers.
   - Used in: form-zero-followers-not-equal-everywhere (platform_official).

4. https://newsroom.tiktok.com/en-us/introducing-the-new-creator-rewards-program
   - Says: 18 Mar 2024; eligibility 18+, 10K followers, 100K views in 30 days, personal account in good standing; rewards only "high-quality, original content that is over a minute long"; formula = originality, play duration (watch time and finish rate), search value, audience engagement, plus ad value; claims 50% of time on TikTok goes to videos over one minute.
   - Fails to establish: how much search value is worth, or that tutorials grow followers. Payment formula details are not published.
   - Used in: form-tutorial-search-value, form-react-repost-ceiling (platform_official).

5. https://about.fb.com/news/2017/12/news-feed-fyi-fighting-engagement-bait-on-facebook/
   - Says: Meta defines engagement bait as posts asking for likes/comments/shares/tags/votes to game reach; such posts get demoted, with "stricter demotions for Pages that systematically and repeatedly use engagement bait"; legitimate asks (missing child, fundraiser, asking for travel tips) are exempt.
   - Fails to establish: anything about "part 2" or serialised content specifically, and nothing current to 2026 Reels/TikTok. It is a 2017 Facebook News Feed post.
   - Used in: form-part-two-cliffhanger (platform_official).

6. https://business.google.com/en-all/think/search-and-video/short-and-long-form-videos/
   - Says: YouTube-commissioned Ipsos survey, 13 markets, ages 18-24, n=5,722, May 2022: 59% of Gen Z use short-form apps to find things they later watch in longer form; Shorts 1.5B MAU / 30B daily views; named creators (Cassey Ho, Dr. Dray, TheKoreanVegan "first one to two seconds are the most important").
   - Fails to establish: a short-to-long audience overlap measure, or that Shorts convert to subscribers. Overlap is inferred from a self-report survey and creator claims; data is 2022.
   - Used in: form-tutorial-search-value (study).

7. https://github.com/twitter/the-algorithm
   - Says: X's own open-source For You code; search index supplies in-network candidates and "~50% of posts come from this candidate source"; out-of-network candidates come via tweetmixer/UTEG; a neural heavy ranker scores candidates; visibility filters downrank.
   - Fails to establish: signal weights, spam/duplicate rules, or what happens to an account with no followers. The README is architecture-level only and points elsewhere for detail.
   - Used in: form-zero-followers-not-equal-everywhere (platform_official).

8. https://ar5iv.labs.arxiv.org/html/2301.04945
   - Says: Zannettou et al., data-donation study, 347 TikTok users, 9.2M recommended views (Jul 2020-Feb 2022): 45% of views watched to the end, median attention 82%, 40% skipped before halfway; videos from non-followed accounts completed more often (44-46% vs 38-42%) and were far more popular (median 755K vs 85K plays); only 10.3% of views came from pre-followed accounts.
   - Fails to establish: anything about creator follower counts or new accounts directly - it measures viewers, and the sample is small and non-representative (over half from Africa despite US-targeted recruitment).
   - Used in: form-zero-followers-not-equal-everywhere (study).

9. https://buffer.com/resources/how-often-should-you-post-on-tiktok/
   - Says: Buffer data scientist Julian Winternheimer, 11.4M TikTok posts from 150,000+ accounts, fixed-effects regressions and Z-scores: median views flat at ~500 at every cadence, while p90 climbs 3,722 -> 6,983 -> 10,092 -> 14,401; "posting more helps - but mostly because it increases your chances of getting lucky"; gains hold across account sizes.
   - Fails to establish: that posting more improves a typical post, and it gives no data-collection window; metadata on the page is inconsistent about year.
   - Used in: form-survivorship-of-success-patterns, form-part-two-cliffhanger (study).

10. https://metricool.com/press-release-tiktok-study-2026/
    - Says: 2,314,756 TikTok posts from 92,000+ accounts, Jan-Feb 2025 vs Jan-Feb 2026: views -31.30%, reach -28.73%, interactions -31.17%; For You Page drives 72.70% of views; 72.10% more videos and ~140% more image/carousel posts published YoY; videos give 5x reach and 6x interactions vs images; posts reach 96% of total reach within 10 days; questions get 26.19% more comments; 16.47% of accounts moved into a higher follower category.
    - Fails to establish: a small-account breakdown (no follower-size strata given) or whether niching helps; the press release also does not state how "higher follower category" transitions were sampled.
    - Used in: form-cold-open-hot-take, form-narrow-beats-broad-folklore, form-part-two-cliffhanger (study).

11. https://eden.so/blog/instagram-carousel-study/
    - Says: 655,385 Instagram carousels from 12,159 creators, Aug 2025-Aug 2026; breakout = >=2x the author's own median; breakout rate rises with deck length (3 slides 23.4%, 14 slides 32.1%, 20 slides 32.0%); under 10,000 followers: 18.0% for 2-4 slides vs 23.5% for 11-20; only 16.7% of carousels use 11+ slides; authors state results are "strong tendencies rather than causes" and that higher breakout rates with account size reflect "who the algorithm already favors, not a lever you can pull".
    - Fails to establish: a cause, and anything reliable below 1,000 followers (the authors say that band is small and least reliable because the index skews to active, growing accounts).
    - Used in: form-countdown-carousel-deck, form-survivorship-of-success-patterns (study).

12. https://digiday.com/marketing/how-every-major-platform-pays-creators/
    - Says: per-platform minimum audience thresholds as of Sep 2026 - TikTok Creator Rewards 10,000 followers; 1,000 for LIVE gifts/LIVE subscriptions/Shop Affiliate; 10,000 for TikTok One and Series; 100,000 for Pulse; YouTube 1,000 subs + 4,000 watch hours or 10M Shorts views; Instagram 500 followers for fan tips; X 500 verified followers plus 5M organic impressions in three months; TikTok Shop is 0 followers.
    - Fails to establish: official wording for each threshold (trade press summary, not the platform pages), and whether the gates changed since publication.
    - Used in: form-zero-followers-not-equal-everywhere (secondhand).

13. https://communicateonline.me/news/instagram-expands-crackdown-on-reposted-content-across-platform/
    - Says: 4 May 2026; Instagram extends its 2024 originality policy beyond Reels to photos, video and carousels; accounts that mostly repost without meaningful edits lose eligibility for recommendation surfaces; Meta says 75% of content recommended to US users is now classified as original; "We know how frustrating it can be to see aggregators benefit from your work."
    - Fails to establish: a named executive, the audited method behind the 75% figure, or per-country scope. It is trade-press coverage of a Meta statement.
    - Used in: form-react-repost-ceiling (secondhand).

14. https://sproutsocial.com/insights/instagram-algorithm/
    - Says: 28 Jan 2026, Nader Nekvasil; per-surface ranking (Feed/Stories/Reels/Explore); Reels factors include sends per reach ("arguably the strongest signal"), views as "the primary currency", retention measured past the 3-second mark, and an "aggregator penalty" where Instagram "will often replace your post with the original creator's version in recommendations"; warns against watermarked reposts; 2.46% Reels engagement benchmark from Sprout's 2025 Content Benchmarks Report.
    - Fails to establish: Instagram's own dated statement for the Mosseri signals (cited to a Reel, not a transcript), and anything measured about small accounts, only a "5-3-1" engagement rule of thumb.
    - Used in: form-cold-open-hot-take, form-countdown-carousel-deck, form-react-repost-ceiling (practitioner).

15. https://sproutsocial.com/insights/social-media-content-series/
    - Says: Sprout Q2 2025 Pulse Survey, 2,000+ global users, 57% say "posting original content series" should be a brand priority for 2026; recommends predictable cadence and recurring characters; Coco Mocoe: "To transcend algorithms, you have to give your audience routine"; frames series as the answer to crowded feeds.
    - Fails to establish: that series grow an unknown creator's audience; it is brand-side survey opinion about priorities, not outcomes.
    - Used in: form-storytime-episodic, form-narrow-beats-broad-folklore (practitioner).

16. https://buffer.com/resources/how-to-find-your-niche/
    - Says: 23 Mar 2023 Buffer interviews creators on both sides of niching: Josh Ho (broad interests mean "no one would understand who I'm trying to speak to"), Amanda Natividad (write "almost exclusively about that thing for 3+ months"), Lloyd George (niche made growth "significantly easier"), against Toni Bravo ("I'll never have a niche") and Jason Levin (niching early is "very silly"); the only number is Tom Frank's ~1M monthly blog visitors.
    - Fails to establish: any test of narrow vs broad. Explicitly practitioner opinion, which is why the entry is marked folklore.
    - Used in: form-narrow-beats-broad-folklore (practitioner).

17. https://www.plannthat.com/instagram-90-second-reels/
    - Says: 8 Jun 2022; Instagram raised the Reels cap from 60 to 90 seconds globally after "months of trials and testing", alongside original audio upload and interactive stickers (Adam Mosseri's announcement); "Reels now make up more than 20% of the total time people spend on Instagram".
    - Fails to establish: that length affects reach; the article itself says no data links Reel length to engagement. I cited it only as background and did not build an entry on length.
    - Used in: nothing (read, kept as context, deliberately uncited).

18. https://youarenotsosmart.com/2013/05/23/survivorship-bias/
    - Says: David McRaney on survivorship bias, Abraham Wald and the B-17 bullet holes; "when failure becomes invisible, the difference between failure and success may also become invisible"; "the advice business is a monopoly run by survivors"; quotes Kahneman on grouping successes.
    - Fails to establish: anything about social platforms specifically - it is the general argument about the bias, used here as the citable origin for that argument.
    - Used in: form-survivorship-of-success-patterns (secondhand).

19. https://en.wikipedia.org/wiki/Jools_Lebron
    - Says: 17-second "How to be Demure at Work" uploaded 2 Aug 2024; by 20 Aug the two videos had 7,000,000 and 34,000,000 views; "By August 25, 2024, her following had grown to two million people"; table last updated 3 Nov 2026 shows 2.3M TikTok and 263K Instagram; years active 2023-present.
    - Fails to establish: her follower count immediately before August 2024 (no pre-viral baseline is given), so "from zero" is approximate; the Guardian long-read that would have supplied it was unreadable (below).
    - Used in: form-cold-open-hot-take, form-survivorship-of-success-patterns (secondhand).

20. https://blog.youtube/news-and-events/convert-viewers-into-subscribers-with/
    - Says: 18 Mar 2013 YouTube post: the channel trailer is "an ad for your channel", is shown to non-subscribers when the Browse Tab is on, should carry a clear subscribe CTA, should show rather than tell, and "There's no perfect length, but shorter is better".
    - Fails to establish: any measured effect on subscriber conversion; 13 years old and no numbers.
    - Used in: form-profile-as-landing-page (platform_official).

21. https://www.businessinsider.com/reference/what-does-pinned-mean-on-tiktok
    - Says: 20 Dec 2022; TikTok lets creators pin up to three videos to the top of the profile grid, marked with a red "pinned" label, so a visitor sees best work or a channel-thesis video first; the rest stays reverse-chronological.
    - Fails to establish: that pinning converts visitors to followers - no performance data.
    - Used in: form-profile-as-landing-page (secondhand).

22. https://www.businessinsider.com/instagram-lets-users-add-more-than-one-link-to-bios-2023-4
    - Says: 19 Apr 2023; Zuckerberg announced up to five profile links for all account types ("probably one of the most requested features"), Meta spokeperson confirms, creators split on it, Matt Navarra calls it a "body blow" to link-in-bio tools.
    - Fails to establish: reach consequences of links or any profile-conversion number; and it predates 2026 changes I could not verify.
    - Used in: form-profile-as-landing-page (secondhand).

23. https://buffer.com/resources/how-to-put-a-link-in-tiktok-bio/
    - Says: "You'll need 1,000 followers unless you switch to a business account"; a URL typed into the bio text is plain text only; clickable links appear in the Website field for eligible business accounts, business registration may need legal name/address/licence, and the field can only be edited in the mobile app; one website field, so a link-in-bio tool is the workaround.
    - Fails to establish: the official TikTok rule text - Buffer's reading of the app, with regional variation admitted.
    - Used in: form-profile-as-landing-page (practitioner).

## Tried and rejected

- https://support.tiktok.com/en/using-tiktok/exploring-videos/how-tiktok-recommends-content - 302 redirect to a `tiktok.com/support/faq_detail?id=7655285288050104852` shell that returned only CDN/SDK config, no article text. Dropped; used the newsroom version of the same explanation instead.
- https://www.tiktok.com/support/faq_detail?id=7655285288050104852 - same JS shell, no FAQ body.
- https://www.tiktok.com/support/faq_detail?id=7636670084748057108 ("Create and manage Series") - JS shell, could not read eligibility or episode rules, so no Series-specific entry.
- https://support.tiktok.com/en/live-gifts-wallet/tiktok-live/what-is-tiktok-live - 302 to id=7543604790438451768, which returned only the app config shell. The 1,000-follower LIVE gate therefore rests on Digiday, not on TikTok's own page.
- https://support.tiktok.com/en/business-and-creator/creator-rewards-program - not fetched; the same host pattern returned shells, so I used the newsroom announcement instead.
- https://www.tiktok.com/creator-academy/article/creator-rewards-program - 200 but body empty (`"articlePageQuery":{}`); nothing quotable.
- https://help.instagram.com/1800814370401535/ ("About original content on Instagram") - 200 but only CSS/JS config. Instagram's originality wording is therefore cited via trade press (item 13), which is the honest weak spot in form-react-repost-ceiling.
- https://transparency.meta.com/en-gb/features/approach-to-ranking/content-distribution-guidelines/engagement-bait - 200, truncated to head/CSS, no policy text.
- https://transparency.meta.com/enforcement/taking-action/repeatedly-posting-low-quality-content/ - same truncated shell.
- https://help.x.com/en/rules-and-policies/recommendations - 403 Forbidden.
- https://help.x.com/en/resources/recommender-systems/for-you-home-timeline-recommendations - 403 Forbidden. X's official recommendations documentation is unreachable from here, so the X side of form-zero-followers-not-equal-everywhere leans on the open-source repo plus Digiday.
- https://support.google.com/youtube/answer/3219384?hl=en ("Customize your YouTube channel layout") - 200, body truncated to CSS; the official YouTube help text on channel layout could not be read, so the profile entry uses the 2013 YouTube blog post instead.
- https://www.pewresearch.org/short-reads/2025/02/18/what-we-know-about-tiktok-content-creators/ - fetched twice; both times only schema metadata and CSS returned (headline, byline Regina Widjaya, 18 Feb 2025, "creator accounts make up about half of all accounts that U.S. users follow"). The follower-size distribution (10% over 1M etc.) appears only in the search snippet, which is not enough to quote, so no entry cites Pew.
- https://www.tiktok.com/support/faq_detail?id=7655285288050104852 (repeated redirect target) - as above.
- https://www.instagram.com/reel/DE-DISgytMe/ and https://www.instagram.com/p/DHkq-FTN-9N/ - Instagram post surfaces; not loadable as text, so the Reels length change is cited from Plannthat (item 17) and not presented as platform-official.
- https://www.instagram.com/reel/DXwUplrhe4j/ and https://www.instagram.com/p/DXxCZ6WDrVN/ - same, unreadable; the Mosseri originality statements are attributed to Sprout and Communicate instead.
- https://zeely.ai/blog/how-long-can-instagram-reels-be/ - appeared in search claiming a 20-minute cap with only 3 minutes recommended to new audiences; not loaded, so not cited (unverified claim contradicted by better sources).
- https://www.plannthat.com/instagram-90-second-reels/ - loaded (item 17) but deliberately not cited in any entry: it contains no length-to-reach evidence.
- https://papers.ssrn.com/sol3/Delivery.cfm/6425938.pdf?abstractid=6425938&mirid=1 ("TikTok-lead lessons without paid targeting") - 403 Forbidden. This was the one candidate academic source that appeared to discuss "asking 'part 2'" directly; without it the part-2 entry has no study of cliffhangers, and says so in its does_not_claim.
- https://help.x.com/... (all) - 403 as above.
- https://www.rollingstone.com/culture/culture-lists/top-social-media-influencers-creators-2026-1235605189/ - 200, body truncated to scripts/CSS; a snippet suggested a creator's rise in "six months" but I could not read the entry, so no case was taken from it.
- https://www.theguardian.com/society/2026/may/14/very-demure-very-mindful-how-jools-lebron-went-viral-and-her-life-fell-apart - 200, only standfirst and byline retrievable (Kirsty Major, 14 May 2026: "in days she had become a meme", "excitement, opportunity and a crushing pressure"). The follower numbers and the pre-viral baseline are in the unreadable part, so Wikipedia (item 19) carries the case.
- https://www.mailmetromedia.co.uk/news/metro-hits-one-million-tiktok-followers/ - 200 but body truncated; only the metadata claim (Metro's TikTok account passed one million followers, 10 Jan 2025, "fastest growing newsbrand") was readable, and it is a brand account not a person, so it was not used.
- https://www.lilachbullock.com/tiktok-series/ - 200, body truncated; only the meta description ("sell up to 80 premium videos behind a paywall") was readable, which is too thin to build the Series/eligibility claim on. Rejected; TikTok Series gating comes from Digiday instead.
- https://searchengineland.com/tiktok-creator-search-insights-content-opportunities-462520 - 403 Forbidden. This was my route to TikTok's official "content gap" Creator Search Insights wording, so the tutorial entry cites the Creator Rewards announcement's "search value" metric instead.
- https://supabird.io/articles/how-to-get-more-followers-on-x-twitter-in-2026 - 200 but only scripts/CSS; the "reply-first for 0-follower X accounts" practitioner claim could not be verified and is not in any entry.
- https://blckalpaca.at/en/knowledge-base/social-media/social-media-algorithms-distribution/reels-vs-carousel-instagram-formats - 200, body was Tailwind CSS only. Its Reels-vs-single-image decline numbers are therefore uncited.
- https://metricool.com/tiktok-news/ - 200, body truncated to title/author/date (Kata Szabo, 5 Nov 2026); no playlist/series/pin timeline could be read.
- https://www.businessinsider.com/growing-small-business-on-tiktok-how-i-get-my-followers-2022-7, https://www.businessinsider.com/how-yahoo-news-grew-to-1-million-tiktok-followers-strategy-2021-2, https://www.entrepreneur.com/science-technology/4-steps-to-grow-to-1-million-followers-on-tiktok/402276, https://www.theinformation.com/articles/the-million-follower-factory-tiktok-is-making-everyone-famous-but-few-creators-are-cashing-in - all outside the roughly-24-month window (2021-2022) or paywalled, so not loaded; they are noted so it is clear the case search was tried and mostly failed.
- https://www.hireawriter.us/social/how-to-make-a-series-on-tiktok, https://uruguayinfluencers.com/blog/tiktok-playlists-your-complete-guide-to-organization/, https://www.tiktok.com/@later.com/video/7544108645324213537 - surfaced in search for series advice; not loaded (a TikTok video page and two low-authority blogs cannot support the entry the newsroom sources already support).
- Various `facebook.com/...` and `linkedin.com/...` posts surfaced by search (Mosseri quotes, "engagement bait" commentary, TIME100 chatter) - not loaded; social feeds need auth and would not have given readable text.

## Questions I could not answer with a real source

- No platform statement about "follow for part 2" or promised future content as a CTA exists in anything I could load. The nearest documented rule is Meta's 2017 engagement-bait demotion (Facebook News Feed, not Reels, not 2026).
- No official Instagram originality page, no official X recommendations page, no official TikTok LIVE/Series support page could be read (all 403 or JS shells), so those entries label the tiers honestly as secondhand/practitioner.
- No press-verifiable named human who went from ~0 to a large following within the last 24 months: the Guardian, Rolling Stone, Metro, Business Insider and The Information candidates were either truncated, paywalled, outside the window, or brand accounts. The Jools Lebron case in Wikipedia is the closest real one (2 Aug 2024, 17-second video, 2M followers by 25 Aug 2024, 2.3M by 3 Nov 2026) and its pre-viral baseline is unstated.
- No study of POV, storytime, before/after or react formats as named archetypes exists in anything I could load. Those archetypes are covered where adjacent evidence reaches (cold-open spoken takes, carousel decks, episodic series, originality rules) and nowhere else; before/after has no entry at all rather than an unsourced one.
