# HalluJudge artifact availability audit

Status: **official B1 dropped with justification** (artifact and labels not public)  
Audit date: 2026-08-19  
Paper: Tantithamthavorn et al., *HalluJudge: A Reference-Free Hallucination Detection for Context Misalignment in Code Review Automation*, https://arxiv.org/abs/2601.19072 (HTML v3 also checked)  
Gate B rule: HalluJudge artifact availability verified **or** baseline dropped with justification (`governance/venue_lock_fse_2027_2026-08-19.md`).

This audit does not attack HalluJudge. It records what can and cannot be reused for EviScope B1.

## What is publicly available

| Item | Available? | Notes |
|---|---|---|
| Paper PDF/HTML | yes | arXiv 2601.19072 |
| Direct-assessment prompt skeleton | partial | §3.3 system + user templates; scoring guide truncated with ellipses in HTML |
| Few-shot / multi-step / ToT skeletons | partial | same truncation; five-shot examples not published in full |
| Official code / Docker / weights | **no** | no GitHub, Zenodo, or ACM artifact link found in the paper or arXiv abstract |
| Human-annotated 143-comment set | **no** | Atlassian RovoDev, enterprise-internal by design (§4.2) |
| Developer-preference 557-comment set | **no** | production thumbs, proprietary |
| Official mapping from 0–4 scores to EviScope 三态 | **no** | different task |

Checked: arXiv abs/HTML v3, paper references, `site:github.com` for HalluJudge + this title. Absence of a repo is not proof it will never appear; it is the state on 2026-08-19.

## Task matrix (why official reuse would be the wrong object anyway)

| | HalluJudge | EviScope |
|---|---|---|
| Unit | review **comment** vs **diff** | atomic **claim** vs nested review-time package |
| Labels | context alignment score **0–4**; binary hallucination if any ungrounded claim | `SUPPORTED` / `CONTRADICTED` / `INSUFFICIENT` |
| Evidence universe | attached code diff | L0–L3 review-time artifacts; `INSUFFICIENT` is a first-class outcome |
| Primary metric | hallucination F1 vs human alignment labels | false rejection on beyond-diff gold `SUPPORTED`; false acceptance safety |
| Data | proprietary Atlassian | public-OSS Challenge set (48 comments, Python-only for this submission) |

## Registered B1 decision

Official HalluJudge **cannot be implemented**. The evaluation sets are proprietary Atlassian RovoDev data; code, weights, full prompts, and the 0–4→三态 mapping were not released. Reconstructing a “HalluJudge” from a truncated §3.3 skeleton would not be their system and must not be reported as B1.

- **Do not** claim we ran the authors’ HalluJudge or scored their 143/557 comments.
- **B0** is the runnable diff-only baseline: same local judge, frozen claims, L0 package.
- **Official B1 is dropped** for FSE 2027. Justification is this audit. HalluJudge remains related work and the construct contrast in the task matrix above.
- A later “diff-only 0–4 comment judge” would be a **new EviScope condition**, not HalluJudge. It is not required for Gate B and is not scheduled.

Do not use Atlassian data.
