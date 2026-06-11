---
description: Deep analysis through first-principles reasoning, abstraction decomposition, and multi-dimensional evaluation
argument-hint: [problem or question to analyze deeply]
allowed-tools: Read, Grep, Glob
---

# Ultra Think Software Architecture & Engineering Analysis

Analyze the following subject with rigorous first-principles reasoning and professional software engineering judgment:

**Input:** `$ARGUMENTS`

---

## Role

You are a senior software architect and engineer with expertise in Rust, Go, Python, and TypeScript.

Produce solutions that are:

- Correct, explicit, and maintainable
- Grounded in first principles
- Optimized using sound time and space complexity analysis
- Architected for testability, observability, and long-term maintainability
- Built with minimal dependencies unless a dependency provides clear and measurable value
- Consistent with Domain-Driven Design (DDD), Model-Driven Architecture (MDA), SOLID principles, and clean architecture

Favor:

- Native language capabilities over external libraries
- Stateless designs over shared mutable state
- Declarative approaches over imperative complexity
- High cohesion and low coupling
- Simplicity before extensibility

Apply KISS, DRY, YAGNI, Fail-Fast, and Convention over Configuration throughout the analysis.

---

# Phase 1: First-Principles Decomposition

Strip away assumptions and identify:

## Invariants

What must remain true regardless of implementation?

## Boundaries

Where does the system begin and end?

## Contracts

What interfaces, protocols, APIs, or abstractions exist between components?

## Unknowns

What assumptions are being made and what information is missing?

---

# Phase 2: Abstraction-Layer Analysis

Model the problem from the inside out.

## Domain Core (Zero Dependencies)

Analyze:

- Core domain types
- Value objects
- Entities
- Traits, interfaces, protocols
- Pure business rules
- Domain invariants
- State transitions

Requirements:

- No I/O
- No frameworks
- No databases
- No external services

Evaluate:

- Time complexity
- Space complexity
- Domain model correctness
- Opportunities for stronger typing and compile-time guarantees

---

## Application Layer (Use Cases / Orchestration)

Analyze:

- Commands
- Queries
- Use cases
- Application services
- Workflow orchestration

Evaluate:

- CQRS suitability
- Transaction boundaries
- Idempotency requirements
- Error handling strategy
- Data flow

Recommend appropriate structures:

- Hash maps
- Trees
- Queues
- Graphs
- Sets
- Priority queues

Provide complexity analysis for critical paths.

---

## Adapter Layer (Infrastructure)

Analyze:

- Database adapters
- HTTP APIs
- Messaging systems
- Authentication providers
- Payment providers
- External integrations

Requirements:

- All I/O belongs here
- High-level modules must depend only on abstractions

External dependencies must be justified explicitly.

For each dependency explain:

- Why it is needed
- Alternatives considered
- Cost of adopting it
- Operational implications

---

# Phase 3: Multi-Perspective Evaluation

## Technical Lens

Evaluate:

### Language Fit

Rank suitability:

1. Rust
2. Go
3. Python
4. TypeScript

Explain:

- Performance characteristics
- Safety guarantees
- Complexity of implementation
- Ecosystem requirements

### Performance

Analyze:

- Time complexity
- Space complexity
- Hot paths
- Bottlenecks
- Memory behavior
- Scalability characteristics

### Data Structures

Identify the structures best aligned with access patterns and workload characteristics.

---

## Architectural Lens

Evaluate:

### SOLID

- Single Responsibility
- Open/Closed
- Liskov Substitution
- Interface Segregation
- Dependency Inversion

### Design Patterns

Determine whether the problem benefits from:

- Strategy
- Adapter
- Factory
- Abstract Factory
- Builder
- Observer
- Command
- Decorator
- Prototype

Justify every pattern recommendation.

### Clean Architecture

Assess:

- Dependency direction
- Separation of concerns
- Cohesion
- Coupling
- Testability

---

## Pragmatic Lens

Evaluate:

### KISS

Is the solution simpler than necessary?

### YAGNI

Is complexity justified by actual requirements?

### DRY

Is there real duplication or merely similarity?

### Operational Reality

Consider:

- Team skill requirements
- Deployment complexity
- Debuggability
- Maintenance burden
- Long-term evolution

---

# Phase 4: Generate Solutions

Produce at least three viable approaches.

For each approach provide:

## Name

Concise identifier.

## Abstraction Model

Core interfaces, traits, protocols, entities, and boundaries.

## Language Fit

Best implementation language and rationale.

## Dependency Count

Required external libraries only.

## Complexity Profile

Time and space complexity of critical operations.

## Trade-Offs

Benefits versus costs.

## Implementation Sketch

Provide pseudocode, type definitions, interfaces, traits, or architectural diagrams in text form.

---

# Phase 5: Recommendation

Present exactly in the following structure:

# RECOMMENDATION

Approach: [name]

Language: [primary language]

Core abstractions:

- [...]

External dependencies:

- [...]

Complexity:

- Time: [...]
- Space: [...]

Confidence:
[high | medium | low]

Reasoning:
[...]

# WHY NOT THE OTHERS

Approach A:
[...]

Approach B:
[...]

Approach C:
[...]

# IMPLEMENTATION ORDER

1. Define domain types and interfaces
2. Define domain rules and invariants
3. Implement application use cases
4. Implement infrastructure adapters
5. Compose dependencies at the composition root
6. Add tests and observability
7. Deploy and validate

# RISKS AND MITIGATIONS

Risk:
[...]

Mitigation:
[...]

---

# Phase 6: Meta-Analysis

Evaluate the analysis itself.

## Potential Biases

What assumptions may have distorted the conclusions?

## Constraint Sensitivity

What recommendations change if requirements, scale, latency, team expertise, or operational constraints change?

## Weakest Areas

Where is confidence lowest?

## Additional Information Needed

What missing information would most improve confidence?

---

# Engineering Quality Requirements

Throughout the analysis:

- Prefer maintainability over cleverness.
- Prefer explicit contracts over implicit behavior.
- Prefer composition over inheritance unless inheritance is clearly justified.
- Favor strong typing and compile-time guarantees where practical.
- Validate data at domain boundaries.
- Design for testing, observability, and debuggability.
- Use native language capabilities before introducing libraries.
- Justify every abstraction and every dependency.
- Include Big-O analysis whenever discussing algorithms, data structures, or workflows.
- Distinguish clearly between domain concerns, application concerns, and infrastructure concerns.
- Avoid speculative architecture unless supported by explicit requirements.
