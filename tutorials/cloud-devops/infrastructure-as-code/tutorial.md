# Infrastructure as Code and Plan/Apply

Declarative configuration describes the shape you want the world to have; a script describes the moves you want to make. The difference only shows up on the second run, which is precisely when a script breaks and a declaration converges.

## Declared state, not steps

An imperative provisioning script carries an implicit assumption that the world is in the state the author imagined when it was written. Re-run it and it tries to create the bucket that already exists, or it quietly skips because of a hand-rolled existence check that has drifted from reality. A declarative tool recomputes what to do from the desired state each time, so running it twice is safe: the second run finds nothing to change. That property — converge to desired state from any starting point — is the whole point. Idempotence is not a nice-to-have; it is what makes an automated apply trustworthy enough to run unattended.

## The plan is a diff, not a script

`terraform plan` compares three things: the configuration in your files, the state file that records what the tool believes it created, and (via refresh) the attributes it can actually read from the provider. The output is a diff between two of them, and it is worth reading as one:

| Symbol | Action | Typical cause |
| ------ | ------ | ------------- |
| `+` | create | resource is declared but absent from state |
| `~` | update in place | a mutable attribute differs |
| `-/+` | replace | an attribute that cannot change in place differs |
| `-` | destroy | resource is in state but no longer declared |

Replacements are the ones that cause outages, and they are decided by the provider's schema, not by you. Changing a resource's `name`, its availability zone, or a VPC's CIDR forces a new resource — the provider cannot rename a live one. Attaching a new security group to an instance in place is fine; changing the instance's subnet is not. The plan states the reason, so scan for `forces replacement` before scanning anything else, and remember that a replacement means the old resource is destroyed *after* the new one is created only when create-before-destroy is configured; otherwise you get a gap.

Plans also drift between generation and application, so a run that reports a stored plan's changes must be applying that plan. Re-planning at apply time against a provider whose API changed under you is how "no changes" becomes an accidental deletion. Save the plan file and apply it.

## Order is derived, not declared

Dependencies come from references — an attribute that interpolates another resource's id — plus explicit `depends_on` for the cases where the relationship is real but invisible. The graph determines ordering, so a resource is never destroyed while something still references it, and a subnet is not created before its VPC. Two consequences follow.

First, nothing is created in the order you wrote it. Reading a plan top to bottom and inferring causality from line order is a mistake; read the graph.

Second, cycles are configuration bugs you must break manually by removing a reference, usually through an intermediate resource or a data source. `create_before_destroy` interacts badly with cycles because it asks the provider to produce a duplicate name while the old resource still holds it.

## State is the source of truth

The state file maps configuration addresses to real cloud resource ids. It is not a cache: delete it and the next apply creates a second copy of every resource, leaving the originals orphaned and still billing. It often contains secrets in plaintext. This dictates its handling:

- Store it remotely with locking enabled, so two applies cannot interleave and corrupt it. Providers implement locks as conditional writes, which means the store needs an object-versioning or compare-and-swap primitive. Without a lock, concurrent applies race and one may destroy the other's half-created resources.
- Never keep it on a laptop. A local state file is unshared, so a colleague's apply does not see your resources, and a lost laptop is a lost mapping from config to reality. State belongs in a bucket or a hosted backend with encryption and access control.
- Never hand-edit it. Surgical fixes go through `terraform state mv` or `import`, which keep the address mapping consistent.

Parallelism is bounded for the same reason locking exists: the graph is safe to walk concurrently only because independent nodes do not share state entries.

## Drift

The deployed world also changes outside the tool: someone resizes an instance in a console during an incident, a policy is attached by another team, an autoscaler replaces an instance the tool thinks it still owns. The next refresh makes that visible as a difference between state and reality. A plan against drifted infrastructure is not a no-op; it will propose reverting changes nobody declared.

That is both the feature and the operational trap: an emergency console edit buys you time and gets undone at the next apply, sometimes at the worst moment. The durable fixes are to notice drift early — an apply on a schedule with a stored plan validates that the configuration still converges — and to make declared changes fast enough that the console is not the quickest route. Adopt resources that were created outside the tool with `import` rather than deleting and recreating them, or the plan will look tidy while a production database disappears.

## Practice

[Terraform Plan Diff](../challenges/cloud-devops-terraform-plan-diff) gives you a desired configuration and an observed state and asks you to reconcile them: classify each resource as create, update, replace or delete, order the resulting operations so dependencies hold, and summarise the plan the way a reviewer needs to read it.
