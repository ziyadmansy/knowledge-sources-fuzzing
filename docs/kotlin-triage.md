# Kotlin divergence triage (step 4, design §6 "Bug reports")

Libraries at documented defaults (design §5.2): Gson 2.14.0, Moshi 1.15.2 codegen,
kotlinx.serialization 1.11.0, Jackson 2.22.3 + jackson-module-kotlin. Every row was
reproduced by hand through the harness with a minimal document (valid Record with one
thing changed). Pattern order: Gson, Moshi, kotlinx, Jackson. Checked 2026-09-27.

**Found by** says where the behaviour showed up: *runs* = refinement loop artifacts
(Kotlin arms, seeds 800–804), *probes* = probing-agent documents, *hand* = only in
this manual triage. Only *runs*/*probes* rows can be credited to the method.

| # | Input (one change) | Pattern | Behaviour | Status | Found by |
|---|---|---|---|---|---|
| 1 | `tags` missing / `null`; `status: null` | ARRR | Gson puts `null` in a non-null Kotlin property | Documented: Gson README says Kotlin non-null types are unsupported; known issue #1657 (answer key) | runs, probes |
| 2 | `id` missing or `null` | ARRA | Gson and Jackson decode `id = 0` | Gson: as #1. Jackson: documented caveat in jackson-module-kotlin README (null → primitive default; fix `FAIL_ON_NULL_FOR_PRIMITIVES`, issue #242) | runs |
| 3 | `status: "bogus"` / `"ACTIVE"` | ARRR | Gson decodes unknown enum constant to `null` | Gson's enum adapter behaviour + #1; not a new bug | runs, probes |
| 4 | `tags: [null]` | AARA | Gson, Moshi, Jackson accept a null element in `List<String>` | Jackson: documented, opt-in `KotlinFeature.StrictNullChecks`. Gson: #1. Moshi codegen: doc check pending | runs, probes |
| 5 | `amount: 1.5`, `tags: [1]`; `amount: true` | AARA; AARR... | Number (Gson/Moshi/Jackson) or boolean (Gson/Jackson) coerced to `String` | Documented leniency / scalar coercion defaults; kotlinx strict by default | runs, probes |
| 6 | extra unknown key | AARR | kotlinx and Jackson reject unknown keys | Documented defaults (`ignoreUnknownKeys = false`, `FAIL_ON_UNKNOWN_PROPERTIES = true`) | runs, probes |
| 7 | `name` missing | AARA | kotlinx rejects a missing nullable property with no default | Documented kotlinx behaviour (design §10 "documented default") | runs |
| 8 | `id: 1.9` | RRRA | Jackson truncates to 1 | Documented default `ACCEPT_FLOAT_AS_INT = true` | runs |
| 9 | `id: ""` | RRRA | Jackson decodes `id = 0` | Jackson empty-string coercion default (as #2) | runs |
| 10 | `id: "1.0"` (string) | AARR | Gson and Moshi accept a numeric string with a fraction as `Long` | Documented lenient number-from-string reading | runs |
| 11 | unquoted string, `NaN`, single quotes | ARRR | Gson lenient syntax by default | Documented: Gson default strictness is legacy/lenient; maintainer comment on gson #3119 | runs, probes |
| 12 | raw U+0000–U+001F inside a string | AAAR | Gson, Moshi **and kotlinx (non-lenient `Json`)** accept; only Jackson rejects. Dart `jsonDecode` rejects | RFC 8259 §7 violation. For kotlinx, previously reported only inside the generic benchmark issue #3273 (closed "not planned" without comment); Moshi likewise #2136–2138. **Reported: kotlinx.serialization #3276** (2026-09-28; reproducer in docs/upstream/kotlinx-control-chars/, standalone on 1.11.0 and 1.12.0-RC) | runs |
| 13 | `id: 9223372036854775808` (2^63) up to ~2^63+1024 | ARRR | Gson saturates to `Long.MAX_VALUE` | Known: gson #1727 (open since 2020), fix PR #1737 unmerged | hand |
| 14 | `id: 18446744073709551617` (2^64+1) | RRAR | kotlinx wraps modulo 2^64 and decodes `id = 1` | Known: kotlinx #3267 (open, 2026-09-09, labelled bug) | hand |

## Summary

- Nothing so far is both new and a bug. Rows 1–11 are documented defaults or known
  limitations; rows 13–14 are known open bugs that neither the fuzzer nor the probes hit.
- Row 12 is the only report candidate: a spec violation in kotlinx.serialization's
  *strict* mode, reported only generically before. It must not be called "new": the GLD
  benchmark's RFC 8259 suite covers the case. Filed as #3276.
- No value divergence was observed in any run: whenever all four libraries accepted a
  document, they decoded the same value.
- Side effect on the design: row 12 (and unquoted strings, `NaN`) also passed the
  harness's kotlinx-based "strict" gate; see design §10 (post-data gate entry).
