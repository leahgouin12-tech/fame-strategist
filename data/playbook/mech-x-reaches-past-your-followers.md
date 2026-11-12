---
id: mech-x-reaches-past-your-followers
confidence: proven
as_of: 2026-11-12
applies_to: x
tags: algorithm, engagement
does_not_claim: That a small account is guaranteed reach; the code shows a boost toward a target position, the numeric weights are unpublished, and the 2023 share figure describes a different system than the 2026 release.
sources:
  - https://github.com/xai-org/x-algorithm | X For You Feed Algorithm | platform_official
  - https://github.com/twitter/the-algorithm | Source code for the X Recommendation Algorithm | platform_official
---
claim: X builds the For You feed from out-of-network retrieval as well as followed accounts and lifts authors with few impressions, so a post from a zero-follower account competes on its own predicted engagement.
mechanism: The published pipeline scores in-network candidates from Thunder together with machine-learned retrieval sources such as Phoenix and SimClusters, then applies a new-author boost and an author-diversity decay, and the earlier open-sourced system documented roughly half of For You posts arriving from the out-of-network search index.
