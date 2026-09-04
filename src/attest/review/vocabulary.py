"""Ordinary English, for D-134's narrowing of D-132 clause (c).

Clause (c) reads the prose a diff moved and asks whether it *names* a symbol the
same diff touched. It asked that with a word-boundary match, so a comment about
words -- "back to main", "the snapshot is taken lazily" -- counted as a statement
of intent about a function named ``main`` or ``snapshot``. D-132's own entry said
so and left it: over-drawering is the safe direction.

This module is the vocabulary half of the fix. A **bare** name is intent evidence
only when it is long enough that English rarely supplies it and it is not one of
the words below; a name that appears in a *recognisable* form -- inside backticks,
or dot-qualified -- is intent evidence whatever it is called, which is the escape
hatch that keeps a real changelog entry about ``snapshot`` working.

The list is curated, not a dictionary: every entry is an ordinary English word a
person writes in a comment or a release note without meaning any particular
function. Entries shorter than :data:`attest.review.intent.MIN_BARE_SYMBOL_CHARS`
are here only so that the plural of a longer one resolves; the length floor is an
independent gate.
"""

from __future__ import annotations

COMMON_ENGLISH_WORDS = frozenset(
    {
        # a
        "absolute", "abstract", "accepted", "according", "accuracy", "activity",
        "actually", "addition", "additional", "adjacent", "advanced", "agreement",
        "although", "analysis", "announced", "anything", "appeared", "approach",
        "argument", "assigned", "assumption", "attached", "attribute", "available",
        # b
        "backward", "balanced", "baseline", "behavior", "behaviour", "believed",
        "boundary", "breaking", "building", "business",
        # c
        "calendar", "capacity", "category", "centered", "changing", "checking",
        "children", "circular", "cleaning", "collapse", "collected", "combined",
        "comment", "compared", "complete", "computed", "concern", "concrete",
        "condition", "conflict", "constant", "consumer", "container", "contains",
        "content", "continue", "contract", "contrast", "control", "converted",
        "correct", "counting", "coverage", "creating", "creation", "critical",
        "currency", "current", "customer",
        # d
        "decision", "declared", "decrease", "dedicated", "default", "definite",
        "delivery", "describe", "designed", "detailed", "detected", "diagonal",
        "difference", "directly", "disabled", "discount", "discover", "distance",
        "division", "document", "dominant", "download", "dropping", "duration",
        # e
        "economic", "element", "eligible", "employee", "enabling", "encoding",
        "engineer", "entirely", "equality", "equation", "escaping", "estimate",
        "evaluate", "eventual", "everyone", "evidence", "exchange", "excluded",
        "executed", "exercise", "existing", "expanded", "expected", "explicit",
        "exported", "exposure", "extended", "external",
        # f
        "feature", "feedback", "filtered", "finished", "flexible", "floating",
        "focusing", "followed", "forecast", "formatted", "fraction", "frequency",
        "function",
        # g
        "generate", "governed", "gradient", "grouping", "guidance",
        # h
        "handling", "hardware", "headline", "historic", "holiday", "horizontal",
        "however",
        # i
        "identify", "identity", "ignoring", "imported", "improved", "included",
        "incoming", "increase", "indicate", "industry", "infinite", "informed",
        "inherits", "initial", "inserted", "instance", "integer", "intended",
        "interest", "interface", "internal", "interval", "invalid", "inverted",
        "involved", "isolated",
        # j-l
        "judgment", "keyword", "knowledge", "labelled", "language", "learning",
        "leverage", "lifetime", "limiting", "listener", "literal", "location",
        "magnitude", "maintain", "majority",
        # m
        "managing", "manifest", "material", "maximum", "meaning", "measure",
        "measured", "mechanism", "membership", "mentioned", "midnight", "minimize",
        "minimum", "missing", "modified", "momentum", "monitor", "multiple",
        # n-o
        "national", "negative", "network", "normally", "notation", "observed",
        "obtained", "occupied", "occurred", "offering", "official", "operator",
        "opposite", "optional", "ordering", "organize", "original", "otherwise",
        "overhead", "override", "overview",
        # p
        "package", "parallel", "parameter", "particle", "partner", "password",
        "pattern", "payment", "pipeline", "planning", "platform", "position",
        "positive", "possible", "potential", "practice", "precision", "prepared",
        "presence", "previous", "printing", "priority", "probably", "problem",
        "procedure", "produced", "product", "progress", "project", "promised",
        "property", "proposal", "protocol", "provided", "provider", "purchase",
        # q-r
        "quantity", "question", "ranking", "reaching", "reactive", "readable",
        "reading", "received", "receiver", "recorded", "recovery", "reducing",
        "referred", "regarding", "register", "regular", "rejected", "relation",
        "relative", "released", "relevant", "reliable", "remained", "reminder",
        "removing", "renaming", "repeated", "replaced", "reported", "required",
        "research", "reserved", "resource", "response", "restored", "restrict",
        "resulted", "retrieve", "returned", "revenue", "reversed", "revision",
        "rounding",
        # s
        "sampling", "scanning", "scenario", "schedule", "scrolling", "seasonal",
        "secondary", "security", "selected", "sensible", "sentence", "separate",
        "sequence", "service", "setting", "severity", "shipping", "shortcut",
        "shutdown", "sibling", "signal", "silently", "similar", "simplify",
        "situated", "snapshot", "software", "solution", "specific", "spelling",
        "splitting", "standard", "starting", "statement", "stopping", "storage",
        "straight", "strategy", "strength", "stricter", "structure", "subject",
        "suddenly", "suggests", "suitable", "supplied", "supports", "supposed",
        "surprise", "surround", "switched", "symmetry",
        # t
        "tailored", "targeted", "template", "temporal", "terminal", "terminate",
        "thinking", "thousand", "threshold", "throwing", "timeline", "together",
        "tolerant", "tomorrow", "tracking", "training", "transfer", "transform",
        "treating", "triangle", "trigger", "truncate",
        # u-z
        "ultimate", "unchanged", "underlying", "universal", "unlimited", "unmarked",
        "updating", "upgrade", "uploaded", "utility", "validate", "validity",
        "valuable", "variable", "variance", "vertical", "violated", "visible",
        "warning", "watching", "weakness", "whatever", "whenever", "wherever",
        "willing", "wrapping", "writing", "yielding",
    }
)


def is_common_english(word: str) -> bool:
    """Whether ``word`` is ordinary English rather than a name.

    Case-insensitive, and a trailing ``s`` is stripped once so that a plural
    resolves to the singular this list holds: ``readings`` is ``reading`` and
    ``snapshots`` is ``snapshot``.
    """
    lowered = word.lower()
    if lowered in COMMON_ENGLISH_WORDS:
        return True
    return lowered.endswith("s") and lowered[:-1] in COMMON_ENGLISH_WORDS
