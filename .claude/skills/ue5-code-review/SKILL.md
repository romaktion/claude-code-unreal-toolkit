---
name: ue5-code-review
description: Review a UE5 C++ change for reflection, UObject lifetime, modules, and gameplay regressions.
argument-hint: "[changed paths or revision range]"
---

Review scope: $ARGUMENTS

Use the requested diff, or the current working tree diff when no scope is given. Read the surrounding code for changed call sites. Review without editing.

- Check UHT visibility, generated include ordering, reflected types, and Blueprint/API compatibility when the diff changes reflected declarations.
- For ownership changes, check whether long-lived UObject references are visible to GC, whether delegates are removed, and whether async callbacks revalidate weak objects and return to the game thread before touching UObjects.
- For build changes, check public versus private module dependencies and exported symbols. For gameplay or network changes, check authority, replication, and when initialization runs.
- Report concrete findings with severity, file and line, a trigger, and the user-visible effect. If there are none, say so and list remaining verification gaps. Recommend a focused automation test when it can reproduce a plausible regression.
