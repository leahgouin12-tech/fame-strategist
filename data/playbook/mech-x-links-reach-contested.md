---
id: mech-x-links-reach-contested
confidence: contested
as_of: 2026-11-12
applies_to: x
tags: format, failure-modes
does_not_claim: That links are proven reach-neutral; X publishes no ranking documentation for links, the trending summary is machine-generated with an error disclaimer, and the model weights that would settle it are not released.
sources:
  - https://x.com/i/trending/2082323264748105828 | X Confirms No More Penalties for Posts with Links | platform_official
  - https://postory.io/blog/x-algorithm-2026 | Twitter/X Algorithm 2026 - What xAI's Open-Sourced Code Shows | practitioner
  - https://www.heise.de/en/news/X-Releases-Timeline-Algorithm-Transparency-with-Gaps-11147699.html | X Releases Timeline Algorithm - Transparency with Gaps | secondhand
---
claim: The rule that bare links kill X reach is contested, since X's product lead and Musk said in July 2026 the penalty ended over a year ago and a code read finds no hard-coded link demotion, yet link posts still underperform in practice.
mechanism: The ranker sums weights times predicted probabilities for actions including link clicks, dwell and video continuation, so a post that ends the session with a click away still loses on predicted behaviour even with no explicit deboost, which argues for putting the substance in the post itself.
