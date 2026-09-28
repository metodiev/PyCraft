# Technical Strategy and Long-Lived Decisions

A technical strategy is a small set of decisions that constrain everything built afterwards. The job is not to have opinions; it is to know which of your opinions will still matter in three years, and to spend attention only on those.

## Some decisions are cheap to reverse

Sort decisions by the cost of undoing them, not by how interesting they are.

Cheap to reverse: a logging library, a queue implementation, an internal REST shape nobody outside the team calls. These should be made quickly, by whoever is closest to the work, and changed when they hurt. Reviewing them centrally adds latency and buys nothing, because the cost of being wrong is a week.

Expensive to reverse: the data model, public API contracts, service boundaries, the identifiers a customer stores on their side, and anything that has already been written to disk in a format other systems depend on. These are worth deliberation, a written record, and a second opinion — not because they are hard to design, but because changing them later means migrating data, coordinating with callers and breaking promises.

The asymmetry is what makes the position defensible. Saying "let the team decide" about a queue is not abdication, and intervening in a data model is not micromanagement — the two have different reversibility, and treating them alike is where architecture work goes wrong. An architect who reviews everything becomes a bottleneck; one who reviews nothing is not doing the job.

## Write down decisions so they can be revisited

A decision that lives only in a chat thread gets relitigated every quarter, usually by someone who was not there. Record the context, the choice, the options rejected and the conditions that would reopen it.

```text
Decision: customer-visible ids are opaque ULIDs; no sequential integers
          leave the service.

Context:  ids appear in URLs and webhooks; partners log them.
          Enumeration of another tenant's ids must not be possible, and
          ids must be sortable for pagination.

Rejected: (a) auto-increment — enumerable, and leaks order volume.
          (b) UUIDv4 — not sortable, index locality suffers.

Consequences: ids are 26 chars; UI truncation rules must be updated.

Revisit if: storage costs from index locality exceed 5% of the budget.
```

The rejected options carry the most weight. When someone proposes auto-increment in eighteen months, the record either reminds them why it failed or shows that the reason no longer holds. A decision with no revisit trigger is a fact, not a decision, and facts do not get updated when the world moves.

## A decision is not a preference

"Postgres over MySQL" is a preference without a context. "Postgres, because we need transactional DDL so migrations can be atomic and rolled back" is a decision: it names a requirement, and it can be re-examined when that requirement changes. The tell is whether you can state what evidence would change your mind. If nothing would, you have a preference wearing a decision's clothes, and the team will resist it correctly.

Preferences are still useful, but they should be labelled as such and held loosely. The cost of a preference presented as a standard is that teams follow it in cases where it does not apply and cannot tell that they were allowed to deviate.

## Communicate direction so teams can act without asking

A strategy is only real if other people can make decisions from it without a meeting. That means the same statement has to answer three things: what we are optimising for, what we are explicitly not doing, and how to resolve a conflict when the two collide.

The negative list is the part that carries the information. "We standardise on one relational store until we have a proven case for a second" tells a team to push back on the new key-value database, which is exactly the decision they otherwise bring to you. A strategy with no exclusions has no content, because it endorses everything.

Write it as a short document with one page per decision, publish it where it can be linked, and update the entries when they change. Every argument this saves is time you spend on the decisions that actually need you.

## Avoid becoming the bottleneck

The failure mode of a competent architect is that every decision routes through them and the queue grows until the org works around them, at which point their opinion carries less weight than before they centralised it.

Three habits prevent this. Delegate the reversible decisions explicitly, and say so — "you own the client retry policy, tell me only if it changes the contract". Give reviewers a rubric instead of a person: the written decisions above let anyone apply the standard, so review scales past one reviewer. And keep a small, visible queue of only the irreversible items open for consultation, with a target turnaround, so teams can plan around it instead of guessing.

The measure is whether the organisation can make a decision you would have made without calling you.

## Practice

[Canary Rollout](../challenges/principal-engineer-canary-rollout) exercises the communication half of this: a change must be released with a rule that any team member can apply without you in the room. Write the decision record and the rollback criterion before you write the code.
