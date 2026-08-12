# SwiftUI Review Plugin

Review SwiftUI code for adherence to the patterns and anti-patterns in ***The SwiftUI Way*** by Natalia Panferova (Nil Coalescing, 2026).

The book is organized as paired "✅ Recommended patterns" / "❌ Potentially harmful patterns" sections, which makes it unusually well suited as a review rubric. Its guidance draws on production SwiftUI use since the framework's first release and on work with Apple's core SwiftUI team — so it reflects what the framework's designers expect from the call site, not general style preference.

## Agent

### swiftui-reviewer
A read-only review agent (`Read`, `Grep`, `Glob`, `Bash`) carrying the full rubric. Claude selects it automatically when you ask for a SwiftUI review, or you can invoke it explicitly through the skill below.

## Skills

### swiftui-review
`/swiftui-review [path]` — resolves the review target, dispatches the agent, and relays the findings.

- **A path** reviews that file or directory.
- **No argument, in a git repo** reviews the working-tree diff.
- **No argument, outside a repo** reviews SwiftUI files under the current directory.

## What it checks

| Area | Examples of what gets flagged |
|---|---|
| **Composition** | UI extracted into `@ViewBuilder` properties instead of standalone view structs, so its work re-runs on every parent update |
| **Modifiers** | `if/else` on runtime state inside a `View` extension; `applyIf`-style generic conditional helpers that silently reset view identity |
| **Dependency scoping** | Leaf views taking a whole model to read one field; `Binding(get:set:)` allocated in `body`; high-frequency state colocated with expensive work |
| **Value vs. reference** | Large structs stored in view values, forcing deep comparison on every parent update — multiplied across list rows |
| **Observation** | `ObservableObject`/`@Published` over-invalidation; non-`Equatable` model properties under repeated assignment; `State(initialValue:)` in `init` producing stale models |
| **Environment** | Closures stored in `EnvironmentValues`; high-frequency values (scroll offsets, sensor data) forcing comparisons across every environment reader |
| **Update cost** | Side effects in view `init()`; sorting, filtering, or joins in `body` or in computed properties `body` reads |
| **Structural identity** | `if/else` swapping between two forms of the same view for styling; switching container types instead of using `AnyLayout` |
| **Loading & concurrency** | `onAppear { Task { } }` that is never cancelled; heavy work assumed to be off the main thread but inheriting `@MainActor`; missing `@concurrent`; missing cooperative cancellation |
| **Geometry** | Geometry-observer output used to constrain its own source view's layout |
| **Lists** | `ForEach(items, id: \.self)`; conditionals inside `ForEach` that vary the view count; `AnyView` row content — all of which defeat lazy row creation |
| **Animation** | Value-based animation on generic containers leaking into arbitrary child content; `withAnimation` around heavy hierarchies; needless `Animatable` conformances |
| **Platform & accessibility** | Icon-only buttons built with the label-closure initializer; hand-rolled controls replacing system ones; `Canvas` controls invisible to VoiceOver; hardcoded colors, fonts, and spacing where semantic styles or `@ScaledMetric` belong |

## How findings are reported

Ordered by severity, each with a `file:line` reference, the concrete trigger that makes the code go wrong, and a specific fix.

- **Critical** — state loss, identity destruction, uncancelled or duplicated work, main-thread blocking, controls invisible to assistive technologies
- **Important** — measurable redundant work: over-broad dependencies, expensive `body`/`init` work, defeated list laziness, over-invalidating observation
- **Minor** — adaptability and convention: hardcoded metrics, non-semantic styling, structural preferences with no current performance cost

Every finding must name a concrete failure trigger. The agent is instructed not to flag by keyword — `if/else` in a body is frequently correct, and `GeometryReader` is not banned — and not to manufacture findings when the code is clean.

## Prerequisites

None. Reviews are read-only; the agent has no write tools.
