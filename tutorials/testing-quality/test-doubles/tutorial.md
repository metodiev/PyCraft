# Test Doubles: Spies, Stubs and Mocks

Every test double replaces a real collaborator, but the doubles are not
interchangeable. The word you choose tells the reader what the test cares about:
a canned answer, a record of what happened, or a pre-programmed expectation that
fails the test when it is not met. Choosing wrongly is how a suite ends up green
while the feature is broken.

## Three doubles, three jobs

A **stub** returns canned answers and nothing else. It exists so the code under
test can make progress without a real dependency.

```python
class StubRates:
    def get(self, currency: str) -> float:
        return 0.85
```

The test asserting on the converted total does not care that `get` was called;
it cares that the number is right.

A **spy** records calls so the test can inspect them afterwards. Assertions are
made by the test, after the fact.

```python
class SpyMailer:
    def __init__(self):
        self.sent = []

    def send(self, to, subject):
        self.sent.append((to, subject))
```

A **mock** is pre-programmed with expectations and verifies them itself.
`unittest.mock.Mock` with `assert_called_once_with` behaves as a mock; the plain
object with defaults behaves as a stub. The distinction matters because mocks
assert on *interactions* — that a specific collaborator was called with specific
arguments — and interaction assertions are exactly what breaks when you refactor
internals without changing behaviour. Reach for a spy or a stub first; use
expectations only when the interaction is the contract, such as "publish exactly
one event per accepted order".

## Patch where the name is looked up

`patch` swaps an attribute for the duration of the block. The target must be the
place the code under test *reads* the name from, not where the object was
originally defined.

```python
# notifications.py
from myapp.email import send_email

def notify(user):
    send_email(user.email, "Welcome")
```

`notifications` holds its own reference to `send_email` after import, so patching
`myapp.email.send_email` changes nothing:

```python
def test_notify_uses_email_sender():
    with patch("notifications.send_email") as sender:
        notify(user)
    sender.assert_called_once_with(user.email, "Welcome")
```

The mental model is a lookup, not a link: `patch` edits the namespace that the
function body will consult at call time. A practical rule is to patch the
attribute on the module that imports it, which also means imports inside
functions need the patch applied to the module being wrapped, and that patching
a class attribute affects every instance created while the patch is active.

## `autospec` catches signature drift

A bare `Mock` accepts any call signature, so a test can keep passing while the
real function gains, loses or reorders parameters. `autospec=True` builds the
double from the real object's signature and rejects calls that would fail against
the original:

```python
with patch("notifications.send_email", autospec=True) as sender:
    notify(user)
```

`create_autospec` does the same for standalone objects. This is one of the few
places where a test double legitimately couples to a signature, and the coupling
is deliberate: it converts a production `TypeError` into a test failure. Pass
`spec=` for attributes and `autospec` for calls; a `Mock` without either is
effectively untyped.

## The over-mocking trap

The failure mode to watch for is a test that asserts the implementation. If a
test pins every internal call, it will fail on every refactor while a genuine
regression — the wrong total, the wrong user, the missing validation — sails
through. Two symptoms:

- Changing a private helper breaks ten tests that all still pass in production.
- The test names collaborators (`assert_called_with("SELECT ...")`) rather than outcomes.

The fix is to push the double to the outermost boundary you own, keep it to
interfaces you control, and assert on the observable result where possible. When
you do assert on a call, pick the interaction that is the requirement itself, not
one that merely happens to occur. Prefer fakes — small in-memory implementations
of your own interfaces — over mocks for repositories and queues; they cost a
little more to write and survive far more refactors.

## Practice

Work through [Spy and Stub](../challenges/testing-quality-spy-and-stub), then read
[Determinism: Why Tests Flake and How to Stop It](../tutorials/testing-quality-flaky-tests-and-determinism).
The [tutorials](../tutorials) index lists every track.

<details><summary>Hint: verifying a patch target</summary>

Import the module under test and print `module.send_email` before patching. If
the printed object is not the one you patched, the reference lives somewhere
else — patch the name that module actually reads.

</details>
