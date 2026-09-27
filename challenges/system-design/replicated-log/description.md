# Project: Replicated Log with Quorum Replication

**This is a project, not a drill.** It is the core of a consensus system,
reduced to something you can hold in your head — and to something whose *safety
properties* a test suite can actually falsify.

You are not implementing Raft. You are implementing the four rules that make a
replicated log safe, and the tests are designed to catch each one being broken:

1. a write is committed only once a **majority** has it;
2. a **term** never goes backwards, and a stale leader cannot commit;
3. a log never **overwrites a committed entry**;
4. a **partitioned minority must not elect a leader**.

| File | Responsibility |
| ---- | -------------- |
| `log.py` | The replicated log itself: entries, terms, append, truncate-from |
| `node.py` | One replica: term state, vote granting, replication handling |
| `cluster.py` | Quorum arithmetic, leader election, partitions, convergence |

## Your task

### `log.py`

| Name | Contract |
| ---- | -------- |
| `Entry` | Frozen dataclass: `term`, `index` (1-based), `value` |
| `ReplicatedLog` | An ordered list of entries with a commit index |
| `.append(entry)` | Append; reject a non-contiguous index or a decreasing term |
| `.get(index)` | Return the entry, or raise `IndexError` |
| `.last_index` / `.last_term` | The tail, or `0` when empty |
| `.is_up_to_date(term, index)` | Whether a candidate's log is at least as current |
| `.truncate_from(index)` | Drop entries from `index` onward — **never a committed one** |
| `.commit(index)` | Advance the commit index; must be monotonic |
| `.committed` | Only the entries at or below the commit index |

`last_term` is `0` for an empty log. `is_up_to_date` compares **term first, then
index** — comparing only the index is the classic mistake that lets a stale
candidate win an election.

### `node.py`

`Node(node_id)`, with `term`, `voted_for`, `log` and `commit_index`.

| Method | Contract |
| ------ | -------- |
| `.grant_vote(candidate_id, term, last_index, last_term)` | Grant at most one vote per term, and only to a candidate whose log is up to date |
| `.handle_append(leader_term, prev_index, prev_term, entries)` | Accept only a non-stale leader with a matching prefix; truncate the conflicting suffix first |
| `.restart()` | Lose volatile state (term and vote), keep the log — this is what makes a vote safe to reuse after a crash |

A vote must be **refused** when the candidate's term is older, and when the
candidate's log is behind. Voting twice in one term is the bug that elects two
leaders.

### `cluster.py`

| Name | Contract |
| ---- | -------- |
| `Quorum` / `majority(size)` | `size // 2 + 1` |
| `Cluster(members)` | A cluster of nodes with a partition model |
| `.partition(*groups)` | Split the cluster into mutually unreachable groups |
| `.heal()` | Restore full connectivity |
| `.elect(candidate_id)` | Run an election; returns the node id that became leader, or `None` |
| `.append(value)` | Append through the current leader; returns the committed index, or `None` |
| `.committed_values()` | The agreed values the cluster has committed |
| `.leader` | The current leader id, or `None` |

`append` must return `None` and commit nothing when the leader cannot reach a
quorum. On `heal`, the leader must **repair** every follower so all logs
converge, without a committed entry ever changing.

## Examples

```pycon
>>> cluster = Cluster(["n1", "n2", "n3"])
>>> cluster.elect("n1")
'n1'
>>> cluster.append("first")
1
>>> cluster.committed_values()
['first']

>>> cluster.partition({"n1"}, {"n2", "n3"})
>>> cluster.append("lost")
>>> cluster.heal()
>>> cluster.committed_values()
['first']
```

## Constraints

- Standard library only.
- Deterministic: no clocks, no randomness, no threads. Elections are driven by
  explicit calls so a test can reproduce any interleaving.
- `log.py` must not import `node.py` or `cluster.py`.
- A write that does not reach a quorum must leave **no trace** — not even an
  uncommitted tail entry. `heal()` propagates the leader's tail to followers, so
  a surviving uncommitted entry would be committed by the back door.
- Committed entries are immutable — a test will try to overwrite one.

## Hints

<details>
<summary>Hint 1 — Term before index</summary>

A candidate with a *higher term* but a *shorter log* must still lose. That is
why `is_up_to_date` compares term first: the higher term proves it has seen more
of history, so its log is authoritative even if it is shorter.

</details>

<details>
<summary>Hint 2 — Truncate before appending</summary>

On `handle_append`, walk back from `prev_index` to find the first divergence,
drop everything from there, then append. Appending first and reconciling later
leaves a window where the log contains two different entries at one index.

</details>

<details>
<summary>Hint 3 — A minority cannot elect</summary>

Count only reachable nodes. If the candidate's own group does not hold a
majority of the whole cluster, the election must fail — even if every node in
that group votes for it unanimously.

</details>

<details>
<summary>Hint 4 — Committed means committed</summary>

Only advance the commit index to the highest index replicated on a majority
**in the leader's current term**. Advancing past that lets a new leader
overwrite an entry the cluster already acknowledged.
</details>
