# SwiftUI Best Practices

Derived from ***The SwiftUI Way*** by Natalia Panferova (Nil Coalescing, 2026), with an architectural stance on when models are warranted.

> **On sourcing.** Sections 2–13 follow the book directly; it is organized as paired recommended/harmful patterns, and the mechanisms cited throughout are its own. **Section 1 is an architectural position this document takes, not a claim about the book.** The book doesn't argue against MVVM — it uses view models where they earn their place (`BirdRegistryViewModel` to cache a sort, `AnimalDetailViewModel` for input-driven reloads). What it supplies is the machinery to judge when one is warranted. Section 1 makes that judgment into a default, and the rest of the document is the evidence for it: the anti-patterns the book catalogues are, in large part, what reflexive layering produces.

---

## 1. Don't fight the framework

The book's stated goal is to help you "focus less on fighting the system." That is the organizing idea, and nearly every anti-pattern in it is a case of imported habit — a reflex that made sense in another framework — colliding with how SwiftUI actually works.

### The view struct is not a view controller

This is the substitution that causes the most downstream damage. In UIKit, a view controller is a long-lived object. It is allocated once, it persists, and it needs somewhere to keep state, derived data, and lifecycle. MVVM answered a real problem there: the controller was the only available home, and it filled up.

A SwiftUI `View` is not that object. It is a short-lived value describing what the UI should look like right now. SwiftUI creates and discards these structs constantly — on every parent update, on every dependency change, on every keystroke into a nearby `TextField`. What persists is not your struct; it is the node SwiftUI keeps in its attribute graph, whose storage SwiftUI owns.

So SwiftUI already provides, natively, most of what a view model layer was invented to provide:

| Need | SwiftUI already gives you |
|---|---|
| Persistent state across recreations | `@State` (storage owned and kept alive by the framework) |
| Change tracking | The attribute graph — per-property with `@Observable` |
| Two-way access without ownership | `@Binding` |
| Dependency injection down a subtree | `@Environment` |
| Lifecycle tied to on-screen presence | `.task`, `.task(id:)`, `.onAppear` |
| Reacting to a specific value changing | `.onChange(of:)` |
| Update scheduling and coalescing | The framework's update cycle |

A view model added per view, by default, re-implements a subset of this in a parallel object graph that shadows the view tree — and then has to be kept in sync with it.

### The reflex is the problem, not the pattern

A view model is a tool. Reaching for one when a screen has real work to own is good engineering. Reaching for one because every view gets one is where it goes wrong — and the specific ways it goes wrong are exactly the anti-patterns catalogued in the rest of this document:

- **It pushes whole objects into leaf views.** Once `FooViewModel` exists, passing it down is the path of least resistance. Now a row that reads one `Bool` re-evaluates on every unrelated change to the model (§3).
- **It makes bindings awkward, which invites `Binding(get:set:)`.** Fresh closures allocated per body evaluation, uncomparable by SwiftUI, so children look changed when they aren't (§3).
- **It moves state ownership out of `@State`.** Which leads to `_model = State(initialValue: Model(id: input))` in `init` — a model that silently goes stale when the input changes, because SwiftUI honors an initial value exactly once (§4).
- **It invites work into `init`.** A "set up the view model" reflex becomes a side effect running on every keystroke into a sibling field (§6).
- **It fragments one screen's state across two trees** that then have to be reconciled — the reconciliation SwiftUI was going to do for you.
- **It is pure ceremony when the state is one `Bool`.** A file, a type, an initializer, and a lifetime question, to hold `isExpanded`.

None of this says "never write a model." It says the model must be justified by what it *owns*, not by its position in a diagram.

### When a model earns its place

Introduce an `@Observable` class when **at least one** of these is true:

1. **The state outlives or is shared beyond a single view subtree** — app-wide sources of truth, or state two sibling screens must agree on.
2. **There is derived data expensive enough to need caching across updates** — a sort, a filter, a join, an aggregation that would otherwise re-run on every body evaluation. This is the book's `BirdRegistryViewModel`: `sortedBirds` is cached precisely so that tapping a sighting button doesn't re-sort the collection.
3. **There is async loading or a lifecycle to own** — fetching, streaming, cancellation, retry, an in-flight/loaded/failed state machine.
4. **There is domain logic worth testing without a view** — rules, validation, transformations that deserve their own tests.
5. **You need a stable writable access path** — a labeled subscript giving SwiftUI something comparable to track, instead of freshly allocated binding closures (§3).
6. **The data is large enough that copying and comparing it as part of a view value is itself a cost** — a reference means SwiftUI compares a pointer instead of walking nested arrays and dictionaries for every row (§4).

If none of these hold, the state belongs in `@State` on the view that owns it, passed down as focused values and bindings.

### What to do instead, by default

- **Compose views, don't layer objects.** The unit of decomposition in SwiftUI is the view struct. Splitting a screen into focused subviews is what buys you both readability *and* update granularity (§2).
- **Own local state with `@State` on the view that owns it.** Group related local state into a plain nested struct if it's getting noisy — the book does exactly this with a `Recordings` struct holding a `Set` and a `String`. That's a model in the useful sense, with no object, no lifetime question, no ceremony.
- **Push state up only as far as it needs to go** — to the nearest common ancestor of the views that share it. Not to a per-view object, and not to a global store.
- **Use the environment for genuinely cross-cutting dependencies** — the app's real sources of truth, configuration, actions (§5).
- **Let the framework own lifecycle.** `.task(id:)` instead of `init`, and instead of a hand-rolled lifecycle on a model.

### Other habits worth dropping

- **`AnyView` as a return-type convenience.** It erases structure SwiftUI needs; in list rows it defeats lazy creation outright (§10).
- **`applyIf`-style conditional-modifier helpers.** Convenient-looking, and guaranteed to reset view identity every time the condition flips (§2).
- **A coordinator object for navigation, by default.** `NavigationStack` with a `path` binding is the framework's answer; introduce more only when deep-linking or restoration genuinely demands it.
- **Reaching for concurrency before there is a bottleneck.** The book is explicit: start on the main thread, add async where the API requires it, and introduce real concurrency only when the interface is measurably sluggish (§8).

The honest summary: SwiftUI's opinion is that the view tree *is* the architecture, and state should live at the level where it is actually shared. Architectures that predate it tend to assume otherwise. When the framework and the imported pattern disagree, the framework wins — it is the thing that decides what re-renders.

---

## 2. Composition

**Extract into standalone `View` structs, not `@ViewBuilder` properties.** A standalone struct is an independent node in the attribute graph. If its inputs are unchanged, SwiftUI skips its `body` entirely. A computed property is part of the parent's identity and re-runs whenever the parent does.

```swift
// ❌ habitat lookup re-runs on every watchlist toggle
struct AnimalDetailView: View {
    let animal: Animal
    @Environment(\.watchlist) private var watchlist

    @ViewBuilder
    private var habitatSection: some View {
        if let name = HabitatsProvider.habitatName(for: animal.habitatID) {
            AnimalInfoSection(header: "Habitat", info: name)
        }
    }
    // ...
}

// ✅ body skipped entirely while habitatID is unchanged
struct AnimalHabitatSection: View {
    let habitatID: Habitat.ID

    var body: some View {
        if let name = HabitatsProvider.habitatName(for: habitatID) {
            AnimalInfoSection(header: "Habitat", info: name)
        }
    }
}
```

Splitting is essentially free — views are lightweight value types, not heap-allocated objects, and SwiftUI collapses deep hierarchies into an efficient internal representation. "I inlined it to avoid overhead" inverts the actual tradeoff. A pure-layout `@ViewBuilder` property with no computation is fine.

**Put shared styling in `View` extensions; put stateful or environment-reading logic in a `ViewModifier`,** exposed through a `View` method so it reads like native API.

**Keep modifier chains structurally stable.** Conditions belong *inside* built-in modifiers, not in `if/else` branches around them:

```swift
// ✅ one stable chain; only attribute values change
extension View {
    func highlighted(_ on: Bool) -> some View {
        self.bold(on)
            .underline(on)
            .foregroundStyle(on ? .green : .primary)
    }
}

// ❌ two distinct hierarchies; toggling destroys and recreates everything wrapped
extension View {
    func themed(color: Color?) -> some View {
        if let color { self.tint(color) } else { self }
    }
}
```

The second form applied to a `TabView` or `NavigationStack` wipes transient state, reloads data, and resets navigation. The generic version of the same mistake — `applyIf(_:transform:)` — is worse, because it hides the branch at the call site and spreads it across the codebase.

Platform (`#if os()`) and availability checks are the exception: they resolve at compile time or launch, never change during execution, and so don't destabilize identity. Move them into modifiers to keep bodies readable.

---

## 3. Dependency scoping

**Pass the minimum.** A specific ID, a primitive, or a focused `Binding` — not the enclosing model. A leaf view taking a whole `Animal` to read `habitatID` re-evaluates on every unrelated field change, and can't be reused for anything but `Animal`.

**Don't colocate high-frequency state with expensive work.** A `TextField` bound to `@State` in a view that also computes lookups in `body` means those lookups run on every keystroke. Move one or the other out.

**Avoid `Binding(get:set:)` in a body.** It allocates fresh closures per evaluation; SwiftUI can't compare closures, so every child appears to have changed. Moving it into a model helper doesn't fix it — the helper still returns new closures. Use a labeled subscript on an `@Observable` model, which gives SwiftUI a stable, trackable access path:

```swift
@Observable final class Watchlist {
    var animalIDs: Set<Animal.ID> = []

    subscript(isSaved id: Animal.ID) -> Bool {
        get { animalIDs.contains(id) }
        set {
            if newValue { animalIDs.insert(id) } else { animalIDs.remove(id) }
        }
    }
}

// call site
AnimalWatchlistRow(animal: animal, isSaved: $watchlist[isSaved: animal.id])
```

Narrow dependencies also buy reusability: a button that takes `@Binding var showPicker: Bool` knows nothing about the screen it's on.

---

## 4. State ownership and observation

**Value types** suit local UI state and small, infrequently-mutated models — no reference counting, no heap allocation, and every change is atomic. Group related local state into one nested struct held in `@State`.

**Reference types with `@Observable`** suit shared or complex state, because tracking is per-property: a view that reads only `showScientificNames` is not invalidated when `sortByConservationStatus` changes.

**Don't pass large structs into views.** Stored properties become part of the view value, and SwiftUI compares the whole thing on every parent update — a nested-array-and-dictionary comparison repeated per row across a list. Pass only what's rendered, or move the dataset into an `@Observable` class so the comparison is a pointer check.

**Prefer `@Observable` over `ObservableObject`.** Reading one `@Published` property subscribes the view to *all* of them, so unrelated changes re-run bodies.

**Give custom types in observable properties `Equatable` conformance** when they're assigned repeatedly — from an async sequence, a poll, a live service. Without it, re-assigning an identical value still invalidates dependents. Two caveats: the check applies to assignment only (in-place `append()` always registers a mutation), and comparing very large collections has a cost of its own.

**Store observable models in `@State`,** never a plain property, or they're re-initialized whenever the view struct is recreated.

**Never seed a model from a parent value in `init`:**

```swift
// ❌ goes stale — SwiftUI honors the initial value only on first insertion
init(habitatID: UUID) {
    _viewModel = State(initialValue: HabitatViewModel(id: habitatID))
}

// ✅ rebuild when the input actually changes
@State private var viewModel: HabitatViewModel?

.task(id: habitatID) {
    if viewModel?.id != habitatID {
        viewModel = HabitatViewModel(id: habitatID)
    }
}
```

Keep the explicit ID check: SwiftUI can re-run `.task(id:)` without an ID change — for instance when a `NavigationStack` destination reappears after a pushed view is dismissed.

**App-wide sources of truth belong in the `App` struct's `@State`,** injected with `.environment(...)`, so they survive across scenes.

**Isolate UI-facing models to the main actor** — implicit if the project defaults to Main Actor isolation, otherwise annotate `@MainActor`. A model deliberately designed to work off the main actor is a different case.

> **Xcode 27:** `@State` is now a macro with lazy initial-value evaluation, back-deployed to iOS 17 / macOS 14 / tvOS 17 / watchOS 10 / visionOS 1. The old "optional `@State` assigned in `.task`" trick is no longer needed *to avoid repeated allocation* — only for input-driven recreation, as above. Initializers should still stay lightweight.

---

## 5. Environment

Match the representation to the dependency:

- **Configuration** → a value via `@Entry`, wrapped in a `View` extension for a native-feeling call site.
- **A self-contained action** → a struct with `callAsFunction()`, which matches `DismissAction`/`OpenURLAction` syntax and stays swappable in previews.
- **Shared mutable state** → pass the `@Observable` model itself and call its methods, keeping state and the operations that mutate it under one owner.

**Never store closures in `EnvironmentValues`.** Closures have no dependable equality, so re-application can invalidate every reader — and the behavior can differ across compiler optimization levels.

**Never put high-frequency values there either** — scroll offsets, timers, sensor data. `EnvironmentValues` is one large struct, so every update forces a comparison for every view reading *any* environment key. Bodies don't re-run, but the comparisons alone can drop frames. Wrap the data in an `@Observable` class and pass the instance.

---

## 6. Update-cycle cost

The cycle: SwiftUI produces a new view value from the struct, resolves dynamic properties from the graph, compares against the previous value, and re-evaluates `body` only if they differ.

**Initializers must do nothing but assign.** Prefer the compiler-generated memberwise initializer. Never treat `init()` as a lifecycle hook — no starting tasks, timers, notification registration, or sync. A parent re-evaluating on each keystroke reconstructs the child and re-fires all of it, spawning competing duplicate work.

**Keep `body` a declarative mapping.** Sorting, filtering, joins, and formatting over collections re-run on every invalidation, including ones caused by unrelated state. Moving the work to a computed property on the view doesn't help — it's still inside the cycle. Cache it in an `@Observable` model recomputed from `.task(id:)` or `.onChange`, or push preparation into a less-frequently-updating parent. Small transformations over static data are fine; judge by update frequency.

---

## 7. Structural identity

Identity is how SwiftUI tells "this view updated" from "this view was replaced." Lose it and the framework tears down the subtree, destroying local state, cancelling in-flight tasks, and discarding loaded data.

```swift
// ❌ toggling destroys the photo view and any in-flight image load
if isStudyMode {
    BirdPhotoView(bird: bird).grayscale(1.0).contrast(1.2)
} else {
    BirdPhotoView(bird: bird)
}

// ✅ same node, different attribute values
BirdPhotoView(bird: bird)
    .grayscale(isStudyMode ? 1.0 : 0.0)
    .contrast(isStudyMode ? 1.2 : 1.0)
```

**For frequently toggled views whose state is expensive to load but cheap to retain,** prefer opacity in a `ZStack` over `if/else` — identity, running tasks, and loaded data all survive, and switching back is instant.

**For layout changes, use `AnyLayout`** rather than switching container types, so children keep identity and state across size-class and orientation changes:

```swift
private var layout: AnyLayout {
    horizontalSizeClass == .regular
        ? AnyLayout(HStackLayout())
        : AnyLayout(VStackLayout())
}
```

Conditional removal is correct when clearing the view *and its state* is the actual intent. That's a decision, not an accident.

---

## 8. Data loading and concurrency

**`.task(priority:)` for async work on appearance** — SwiftUI cancels it when the view leaves the hierarchy. **`.task(id:)` when the work must restart on an input change** — the in-flight task is cancelled automatically.

**Never `onAppear { Task { ... } }`.** That task isn't tied to the view's presence and is never cancelled; frequent appear/disappear leaves work piling up. `onAppear` is fine for lightweight synchronous setup that must land in the first frame, but it can fire more than once, so guard one-time work.

**Always provide a placeholder state.** A fast async task is never guaranteed to finish before first display.

**Keep `onChange(of:)` and `task(id:)` identifiers cheap.** SwiftUI compares them every update cycle; a large collection or an expensive `Equatable` is a per-cycle cost. Use an ID, a count, or a version.

**`Task {}` does not mean "background."** In a `@MainActor` context — a view, or a main-actor-isolated model — it inherits that isolation and runs on the main thread. Heavy custom work needs an explicit opt-out:

```swift
@concurrent private func decode(_ data: Data) async throws -> [NationalPark] {
    try Task.checkCancellation()
    // ... expensive decoding, off the main thread ...
}
```

System APIs like `URLSession` offload on their own. **Support cooperative cancellation** — Swift tasks aren't forcibly terminated, so check `Task.checkCancellation()` before expensive steps and inside loops.

And don't reach for concurrency you don't need. Main-thread and plain-async code are legitimate defaults; concurrency is for a measured bottleneck.

---

## 9. Geometry

Prefer **`onGeometryChange(for:of:action:)`** on the measured content over wrapping it in a `GeometryReader`. It observes without participating in layout, and its action fires only on actual change.

For high-frequency visual response — parallax, stretchy headers — prefer **`visualEffect(_:)`**, which reads geometry and applies render-level effects without touching the layout pass or triggering body re-evaluation.

**Never let a geometry observer's output constrain its own source view.** Measuring width into state and then applying `.frame(width:)` from that state on the same view is a layout loop: the state update triggers a pass that invalidates the measurement that produced it. Geometry output should drive distant nodes or independent parameters — presentation detents, for example.

---

## 10. Lists

Lists gather **all** element identifiers eagerly, then create row content lazily for visible rows plus a small buffer. Both halves need your cooperation.

**Use small, stable identifiers.** `ForEach(items, id: \.self)` on a model with synthesized `Hashable` makes identity include every stored property, so editing any field reads as remove + insert — disrupting row state and animations — and diffing hashes the whole value. Keep `Hashable` if it's useful elsewhere; just don't use it as list identity.

**Each element must resolve to a constant view count.** A conditional inside `ForEach` that varies the number of views returned forces SwiftUI to evaluate every closure upfront to count rows — brutal for large collections with images. Filter in the data layer:

```swift
// ❌ evaluates for every element upfront
ForEach(allWalks) { walk in
    if walk.durationInDays == 1 { WalkRow(walk: walk) }
}

// ✅ filtering done once, upstream
ForEach(viewModel.dayWalks) { walk in
    WalkRow(walk: walk)
}
```

**No `AnyView` in row content** — erased structure defeats lazy creation the same way.

---

## 11. Animation

**Prefer built-in animatable attributes.** They're highly optimized and often run off the main thread without calling into your code.

**Prefer `.animation(_:value:)` over `withAnimation`** when the change is local — `withAnimation` animates every view responding to that state, and around a heavy hierarchy it can force expensive layout recalculation.

**In generic containers, use `.animation(_:body:)`** so only the attributes inside the closure animate:

```swift
// ✅ only opacity animates, whatever the child content does
content
    .padding()
    .background(.secondary)
    .animation(.default) { $0.opacity(isUnlocked ? 1 : 0.4) }
```

The value-based form on a generic wrapper leaks into arbitrary child content: anything in `content` also reacting to `isUnlocked` gets animated too.

**Avoid custom `Animatable` conformances** unless a built-in effect genuinely can't do it — `Animatable` runs `body` every frame.

---

## 12. Platform conventions and accessibility

**Give controls their full semantics.** `Button("Edit", systemImage: "pencil")` plus `.labelStyle(.iconOnly)` — not `Button { } label: { Image(systemName: "pencil") }`. The first adapts to context and exposes an accessibility label; the second discards both.

**Don't hand-roll system controls.** `Image(...).onTapGesture { }` has no pressed-state feedback and no accessibility traits. A real `Button` renders correctly in a toolbar, a list row, and a swipe action with no extra code, because the structural containers define the environment that lets it resolve its role. Build the interface backbone from `NavigationStack`, `NavigationSplitView`, `TabView`, `List`, and `Form` for the same reason.

**When custom UI is genuinely required,** first check whether it can be a **style** on the semantically matching control — `ToggleStyle`, `ButtonStyle` — which inherits accessibility traits automatically. Where no style protocol exists (there's no custom `PickerStyle`), build the visuals and supply `.accessibilityRepresentation { }` mapping onto the equivalent system component.

**A `Canvas`-plus-gesture control is invisible to VoiceOver.** `Canvas` doesn't populate the accessibility tree, and drag-only interaction leaves AssistiveTouch users no increment/decrement path.

**Style semantically.** `.secondary`, `.headline` — not hardcoded colors and point sizes. Semantic styles resolve against Dark Mode, Dynamic Type, and increased contrast.

**Scale custom metrics.** Prefer system-default `.padding()`; when a specific value is needed, use `@ScaledMetric` (optionally `@ScaledMetric(relativeTo: .caption)`) so spacing grows with text instead of crowding at larger sizes.

Plan for Dynamic Type, Reduce Transparency, Reduce Motion, and Increased Contrast — and test against them.

---

## 13. Quick reference

| Anti-pattern | Why it hurts | Instead |
|---|---|---|
| A view model per view, by habit | Duplicates framework machinery; invites the rest of this table | `@State` + focused subviews; a model when it owns something (§1) |
| `@ViewBuilder` property holding real work | No independent dependency tracking; re-runs with the parent | Standalone `View` struct |
| `if/else` in a modifier or extension | Two hierarchies; identity and state destroyed on toggle | Conditions inside built-in modifiers |
| `applyIf(_:transform:)` | Same, but hidden at the call site | Ternaries; optional-aware modifiers |
| Whole model into a leaf view | Invalidated by every unrelated field change | Pass the ID, the value, or a `Binding` |
| `Binding(get:set:)` in a body | Fresh uncomparable closures each evaluation | Labeled subscript on an `@Observable` model |
| Large struct as a view property | Deep comparison per view value, per row | Small values, or a reference |
| `ObservableObject` / `@Published` | One read subscribes you to all properties | `@Observable` |
| Non-`Equatable` type reassigned often | Identical values still invalidate | Add `Equatable` |
| `State(initialValue:)` from a parent value | Honored once; silently goes stale | Optional `@State` + `.task(id:)` with an ID check |
| Closure in `EnvironmentValues` | No dependable equality; over-invalidates | Callable struct, or pass the model |
| High-frequency value in the environment | Comparison cost for every environment reader | `@Observable` class by reference |
| Work in `init()` | Re-runs on every struct recreation | `.task` / `.task(id:)` |
| Sorting or filtering in `body` | Re-runs on every invalidation | Cache in a model; recompute on real input change |
| `if/else` to restyle the same view | Teardown, state loss, cancelled tasks | Condition inside the modifier |
| Switching container types | Subtree replaced | `AnyLayout` |
| `onAppear { Task { } }` | Never cancelled; accumulates | `.task(priority:)` |
| Heavy work in `Task {}` on `@MainActor` | Inherits isolation; blocks the UI | `@concurrent` function |
| Large collection as `task(id:)` identifier | Compared every update cycle | ID, count, or version |
| Geometry output constraining its own view | Layout feedback loop | Drive distant nodes or independent parameters |
| `ForEach(items, id: \.self)` | Edits read as remove + insert; costly diffing | Small stable ID |
| Conditional inside `ForEach` | All rows built upfront | Filter upstream |
| `AnyView` row content | Defeats lazy creation | Concrete row view |
| `.animation(_:value:)` on a generic container | Leaks into arbitrary child content | `.animation(_:body:)` |
| Icon-only `Button` via label closure | No accessibility label; no context adaptation | `Button(_:systemImage:)` + `.labelStyle(.iconOnly)` |
| Hand-rolled control | No traits, no feedback, no context adaptation | System control + custom style |
| `Canvas` control with no a11y | Invisible to VoiceOver and AssistiveTouch | `.accessibilityRepresentation { }` |
| Hardcoded colors, fonts, spacing | Breaks under Dynamic Type, Dark Mode, contrast | Semantic styles; `@ScaledMetric` |

---

## The through-line

Almost every item above reduces to one question: **does SwiftUI have enough information to skip work, and does it have a stable enough view of your hierarchy to update instead of rebuild?**

Focused subviews, narrow dependencies, stable identity, cheap identifiers, and semantic components are all ways of answering yes. Reflexive layering, broad dependencies, structural branching, and hand-rolled substitutes are ways of answering no — usually while looking, at the call site, like ordinary good practice.
