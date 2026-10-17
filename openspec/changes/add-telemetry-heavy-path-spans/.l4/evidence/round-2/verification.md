# Verification: openspec:add-telemetry-heavy-path-spans: NEEDS_HUMAN (round 2)

traceability: 21/21 criteria covered by a discriminating test

- Base: `d38532a845733aad8c23768872917f5cd999e8c8`
- Head: `a4c135a07b18dcd809ab1eae09d6761216e53487`
- Implementer profiles: deepseek, glm
- Judge: claude-judge (claude-sonnet-5-5), 2 call(s), prompt sha256 `0de15f415605e54d4ea60b6f39b66b09364f503818cc0260e56e52b7f7b46d54`
- Judge replies of claude-judge (this unit, all rounds): valid 0, repaired 0, retried 1, discarded 0; this round: retried
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared), glm zhipu (declared)
- Cost: $1.3362

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.7 | base staging@d38532a845 contained |
| 1 | integrity | ok | 0.8 | 7 sub-checks (+1 unfrozen by human answers); scope: 36 changed file(s), 1 held |
| 2 | build | ok | 0.8 |  |
| 3 | tests | ok | 64.4 |  |
| 4 | traceability | ok | 0.1 | 21/21 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other |
| 8 | s1 judge | ok | 1.7 | 21/21 criteria judged by jev |
| 9 | judge | ok | 34.3 | 2 call(s) |
| 10 | aggregation | ok | 0.0 | NEEDS_HUMAN |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --extra cochange --extra otel --extra postgres` | .l4-out/gates/r-20261017T1514Z-dc70/121-setup.log |
| lint | pass | `.venv/bin/ruff check --extend-exclude .l4 .` | .l4-out/gates/r-20261017T1514Z-dc70/122-lint.log |
| lint | pass | `.venv/bin/ruff format --check .` | .l4-out/gates/r-20261017T1514Z-dc70/123-lint.log |
| typecheck | pass | `.venv/bin/mypy packages` | .l4-out/gates/r-20261017T1514Z-dc70/124-typecheck.log |
| test | pass | `.venv/bin/pytest -q --junitxml=.l4-out/junit.xml` | .l4-out/gates/r-20261017T1514Z-dc70/125-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 12 test file(s) compared with the base |
| red-green freeze | ok | 9 task(s): red and green compared (+1 unfrozen by human answers) |
| test path freeze | ok | 10 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| suppressions | ok | 13 new suppression(s), 13 declared |
| tdd history | ok | 17 task(s); red tests passing at head: step 3 |

Declared suppressions:
- packages/cli/src/mintmory/cli/main.py:796 # noqa: S101 (declared: Pre-existing suppression, relocated only by reindenting the index-tree walk under mintmory.index_tree.scan; not newly ad)
- packages/cli/src/mintmory/cli/main.py:848 # noqa: S101 (declared: Pre-existing suppression, relocated only by reindenting the index-tree walk under mintmory.index_tree.scan; not newly ad)
- packages/core/src/mintmory/core/telemetry.py:836 # noqa: BLE001 (declared: an attribute write on a span must never raise into the search caller)
- packages/core/src/mintmory/core/telemetry.py:849 # noqa: BLE001 (declared: a metric record must never raise into the search caller)
- packages/core/src/mintmory/core/telemetry.py:893 # type: ignore[return-value] (declared: same wraps-based decorator pattern as traced(); the wrapper is Callable[..., Any])
- packages/core/src/mintmory/core/telemetry.py:927 # noqa: BLE001 (declared: attribute setting must never raise into the caller)
- packages/core/src/mintmory/core/telemetry.py:968 # type: ignore[return-value] (declared: decorator preserves F via functools.wraps but mypy cannot prove the generic return)
- packages/core/src/mintmory/core/telemetry.py:986 # noqa: BLE001 (declared: reading the record category for the metric must never break a memory write)
- packages/core/src/mintmory/core/telemetry.py:1004 # noqa: BLE001 (declared: A metric recording failure must never break the caller's embedding; swallowing it is the helper's contract.)
- packages/core/src/mintmory/core/telemetry.py:1009 # type: ignore[attr-defined] (declared: the __mintmory_counter__ marker is a dynamic attribute on the wrapper function)
- packages/core/src/mintmory/core/telemetry.py:1010 # type: ignore[return-value] (declared: wraps preserves the callable's signature at runtime but mypy cannot infer that the wrapped callable keeps type F.)
- packages/core/src/mintmory/core/telemetry.py:1017 # noqa: BLE001 (declared: Setting an attribute in the new file_span helper must never raise into the wrapped converter/captioner.)
- packages/core/src/mintmory/core/telemetry.py:1072 # type: ignore[return-value] (declared: wraps-based wrapper returned as _F in the new command_span, matching the other decorators in this module.)

## Tests unfrozen by human answers (allowed, L4-IMP-002)

- packages/cli/tests/test_telemetry_cli_heavy_paths.py (task 4.1, unfrozen by Q-001 (human))

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-844f12f2 | observability › Span kind, parent context and exception options › Options reach the span | covered | packages.core.tests.test_telemetry_span_options::test_span_context_sets_an_explicit_parent (passed, zero_value); packages.core.tests.test_telemetry_span_options::test_span_exception_options_reach_the_span (passed, zero_value); packages.core.tests.test_telemetry_span_options::test_span_kind_maps_know... | packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans (it traces 19 criteria (verifier.max_criteria_per_test=3)) | 0.93 |
| C-f4b27f0d | observability › Search phase spans and latency › A search shows its phases | covered | packages.core.tests.test_telemetry_search_paths::test_note_anchoring_records_no_search_phase (passed, red_assertion); packages.core.tests.test_telemetry_search_paths::test_search_records_the_four_phase_spans_and_latency (passed, red_assertion); packages.core.tests.test_telemetry_search_phase::test_s... | packages.core.tests.test_observability_docs::test_metrics_section_lists_the_new_metrics (it traces 7 criteria (verifier.max_criteria_per_test=3)); packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans (it traces 19 criteria (verifier.max_criteria_per_test=3)) | 0.90 |
| C-43d72c8b | observability › Search phase spans and latency › Search-around alone records only its graph point | covered | packages.core.tests.test_telemetry_search_paths::test_search_around_alone_records_only_its_graph_point (passed, red_assertion); packages.core.tests.test_telemetry_search_phase::test_timed_phase_records_only_the_phase_point (passed, zero_value) | packages.core.tests.test_observability_docs::test_metrics_section_lists_the_new_metrics (it traces 7 criteria (verifier.max_criteria_per_test=3)); packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans (it traces 19 criteria (verifier.max_criteria_per_test=3)) | 0.91 |
| C-c91ee0e7 | observability › Search phase spans and latency › The Postgres backend uses the shared path | covered | packages.core.tests.test_telemetry_search_paths::test_postgres_search_uses_the_shared_phase_path (passed, red_assertion) | packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans (it traces 19 criteria (verifier.max_criteria_per_test=3)) | 0.87 |
| C-c986421b | observability › Span helpers without work or with a failure › A stage with nothing to do | covered | packages.core.tests.test_telemetry_search_paths::test_stage_with_nothing_to_do_records_a_zero_count (passed, red_assertion); packages.core.tests.test_telemetry_search_phase::test_search_phase_records_zero_for_a_stage_with_nothing_to_do (passed, zero_value) | packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans (it traces 19 criteria (verifier.max_criteria_per_test=3)) | 0.90 |
| C-20646f63 | observability › Span helpers without work or with a failure › A failing stage | covered | packages.cli.tests.test_telemetry_cli_heavy_paths::test_caption_failure_span_is_failed (passed, zero_value); packages.cli.tests.test_telemetry_cli_heavy_paths::test_cochange_unavailable_is_an_outcome_not_an_error (passed, zero_value); packages.cli.tests.test_telemetry_cli_heavy_paths::test_conversio... | packages.core.tests.test_observability_docs::test_metrics_section_lists_the_new_metrics (it traces 7 criteria (verifier.max_criteria_per_test=3)); packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans (it traces 19 criteria (verifier.max_criteria_per_test=3)) | 0.68 |
| C-0d312d3f | observability › Span helpers without work or with a failure › A metric failure stays inside telemetry | covered | packages.core.tests.test_telemetry_search_paths::test_a_metric_failure_stays_inside_telemetry (passed, red_assertion); packages.core.tests.test_telemetry_search_phase::test_search_phase_swallows_a_metric_recording_failure (passed, zero_value) | packages.core.tests.test_observability_docs::test_metrics_section_lists_the_new_metrics (it traces 7 criteria (verifier.max_criteria_per_test=3)) | 0.90 |
| C-53f9b64c | observability › Embedding spans and latency › Hashing embedder is traced | covered | packages.core.tests.test_telemetry_embedder::test_a_failing_embed_batch_is_marked_and_re_raised (passed, red_assertion); packages.core.tests.test_telemetry_embedder::test_fake_embed_batch_that_calls_embed_records_once (passed, red_assertion); packages.core.tests.test_telemetry_embedder::test_fake_em... | packages.core.tests.test_observability_docs::test_metrics_section_lists_the_new_metrics (it traces 7 criteria (verifier.max_criteria_per_test=3)); packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans (it traces 19 criteria (verifier.max_criteria_per_test=3)) | 0.92 |
| C-755ec9f3 | observability › Embedding spans and latency › Network embedders name their model | covered | packages.core.tests.test_telemetry_embedder_network::test_local_embedder_methods_carry_the_shared_decorator (passed, pre_satisfied); packages.core.tests.test_telemetry_embedder_network::test_ollama_embed_names_provider_and_model (passed, pre_satisfied); packages.core.tests.test_telemetry_embedder_ne... | packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans (it traces 19 criteria (verifier.max_criteria_per_test=3)) | 0.89 |
| C-e9540797 | observability › CLI commands are traced end to end › Command spans and counts | covered | packages.cli.tests.test_telemetry_cli_heavy_paths::test_add_root_span_contains_the_add_memory_span (passed, zero_value); packages.cli.tests.test_telemetry_cli_heavy_paths::test_history_sync_exports_its_root_span (passed, zero_value); packages.cli.tests.test_telemetry_cli_heavy_paths::test_index_sear... | packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans (it traces 19 criteria (verifier.max_criteria_per_test=3)) | 0.88 |
| C-ebe047e9 | observability › CLI commands are traced end to end › A failing command is marked | covered | packages.cli.tests.test_telemetry_cli_heavy_paths::test_failing_ingest_command_is_marked (passed, zero_value) | packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans (it traces 19 criteria (verifier.max_criteria_per_test=3)) | 0.92 |
| C-64a88ce0 | observability › CLI commands are traced end to end › Exit code 0 is not an error | covered | packages.cli.tests.test_telemetry_cli_heavy_paths::test_caption_failure_span_is_failed (passed, zero_value); packages.cli.tests.test_telemetry_cli_heavy_paths::test_command_span_exit_code_zero_is_not_an_error (passed, zero_value); packages.cli.tests.test_telemetry_cli_heavy_paths::test_failing_inges... | packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans (it traces 19 criteria (verifier.max_criteria_per_test=3)) | 0.93 |
| C-3ce5b739 | observability › Indexing and conversion phases are traced › index-tree phases | covered | packages.cli.tests.test_telemetry_cli_heavy_paths::test_cochange_unavailable_is_an_outcome_not_an_error (passed, zero_value); packages.cli.tests.test_telemetry_cli_heavy_paths::test_index_tree_records_scan_prune_and_cochange_children (passed, zero_value) | packages.core.tests.test_observability_docs::test_metrics_section_lists_the_new_metrics (it traces 7 criteria (verifier.max_criteria_per_test=3)); packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans (it traces 19 criteria (verifier.max_criteria_per_test=3)) | 0.90 |
| C-a83f338b | observability › Indexing and conversion phases are traced › No co-change span without co-change work | covered | packages.cli.tests.test_telemetry_cli_heavy_paths::test_no_cochange_span_when_disabled (passed, zero_value); packages.cli.tests.test_telemetry_cli_heavy_paths::test_no_cochange_span_with_one_changed_file (passed, zero_value) | packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans (it traces 19 criteria (verifier.max_criteria_per_test=3)) | 0.92 |
| C-55bbc2f5 | observability › Indexing and conversion phases are traced › Conversion spans | covered | packages.cli.tests.test_telemetry_cli_heavy_paths::test_conversion_failure_span_is_failed (passed, zero_value); packages.cli.tests.test_telemetry_cli_heavy_paths::test_conversion_spans_for_ingest_and_index_tree (passed, zero_value) | packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans (it traces 19 criteria (verifier.max_criteria_per_test=3)) | 0.92 |
| C-193aef3b | observability › Indexing and conversion phases are traced › Inline caption span | covered | packages.cli.tests.test_telemetry_cli_heavy_paths::test_caption_failure_span_is_failed (passed, zero_value); packages.cli.tests.test_telemetry_cli_heavy_paths::test_inline_caption_span (passed, zero_value) | packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans (it traces 19 criteria (verifier.max_criteria_per_test=3)) | 0.69 |
| C-711e3d68 | observability › Worker threads keep the trace › Threads stay in the trace | covered | packages.core.tests.test_telemetry_span_options::test_run_in_context_keeps_the_trace_across_four_threads (passed, zero_value); packages.core.tests.test_telemetry_worker_threads::test_worker_threads_keep_the_caller_trace (passed, red_assertion) | packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans (it traces 19 criteria (verifier.max_criteria_per_test=3)) | 0.42 |
| C-910cf3ca | observability › Memory counters › Counter by category | covered | packages.core.tests.test_telemetry_memory_counter::test_both_backends_add_memory_carry_the_shared_decorator (passed, red_assertion); packages.core.tests.test_telemetry_memory_counter::test_sqlite_add_memory_counts_each_category (passed, red_assertion); packages.core.tests.test_telemetry_set_attribut... | packages.core.tests.test_observability_docs::test_metrics_section_lists_the_new_metrics (it traces 7 criteria (verifier.max_criteria_per_test=3)) | 0.91 |
| C-28481766 | observability › Telemetry carries no content › No content leaks into telemetry | covered | packages.core.tests.test_telemetry_privacy::test_no_content_leaks_into_telemetry (passed, pre_satisfied) | packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans (it traces 19 criteria (verifier.max_criteria_per_test=3)) | 0.89 |
| C-395d5e72 | observability › Telemetry carries no content › Notes, LLM calls, concept names, headers and indexed files leak nothing | covered | packages.cli.tests.test_telemetry_cli_privacy::test_notes_llm_concepts_headers_and_files_leak_nothing (passed, pre_satisfied) | packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans (it traces 19 criteria (verifier.max_criteria_per_test=3)) | 0.95 |
| C-72a88eb9 | observability › Telemetry carries no content › A failure does not leak its message | covered | packages.core.tests.test_telemetry_privacy::test_a_failure_does_not_leak_its_message (passed, pre_satisfied) | packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans (it traces 19 criteria (verifier.max_criteria_per_test=3)) | 0.90 |

## Evidence

### Needs attention

- out of scope: `packages/core/src/mintmory/core/history/ingest.py` (module `core`)
- diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `docs/OBSERVABILITY.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-heavy-path-spans-fix-1/.l4/fix.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-heavy-path-spans-fix-1/.openspec.yaml` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-heavy-path-spans-fix-1/proposal.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-heavy-path-spans-fix-1/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-heavy-path-spans/.l4/evidence/round-1/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-heavy-path-spans/.l4/evidence/round-1/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-heavy-path-spans/.l4/evidence/round-1/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-heavy-path-spans/.l4/ledger/r-20261017T1042Z-74d5.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-heavy-path-spans/.l4/ledger/r-20261017T1320Z-0e59.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-heavy-path-spans/.l4/ledger/r-20261017T1320Z-5212.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-heavy-path-spans/.l4/ledger/r-20261017T1514Z-dc70.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-heavy-path-spans/.l4/review-accepted.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-heavy-path-spans/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-heavy-path-spans/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-heavy-path-spans/verification.md` |  | none | exempt: harness, spec or documentation path |
| `packages/cli/src/mintmory/cli/main.py` | cli | relevant | named in the spec |
| `packages/cli/tests/test_telemetry_cli_heavy_paths.py` |  | relevant | new test file |
| `packages/cli/tests/test_telemetry_cli_privacy.py` |  | relevant | new test file |
| `packages/core/src/mintmory/core/dreaming.py` | core | relevant | named in the spec |
| `packages/core/src/mintmory/core/embedder.py` | core | relevant | named in the spec |
| `packages/core/src/mintmory/core/history/ingest.py` | core | out_of_scope | module `core` is not named in the spec |
| `packages/core/src/mintmory/core/hybrid_search.py` | core | relevant | named in the spec |
| `packages/core/src/mintmory/core/storage.py` | core | relevant | named in the spec |
| `packages/core/src/mintmory/core/storage_postgres.py` | core | relevant | named in the spec |
| `packages/core/src/mintmory/core/telemetry.py` | core | relevant | named in the spec |
| `packages/core/tests/test_observability_docs.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_embedder.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_embedder_network.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_memory_counter.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_privacy.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_search_paths.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_search_phase.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_set_attributes_counter.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_span_options.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_worker_threads.py` |  | relevant | new test file |

### Changed functions

Diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Tests

1855 of 1969 passed, 0 failed, 0 errored, 114 skipped.
51 of 51 new tests passed.
Skipped in files the unit did not touch: `packages.core.tests.conformance.test_backend::test_anchor_candidates_limit_honoured[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_returns_sorted_scored_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_side_effect_free[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_archived_notes_excluded[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_not_counted_in_total_found[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_populates_notes_on_results[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_stale_flags_not_penalises[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_useful_still_increments[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_increments_staleness[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_threshold_sets_is_stale[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_staleness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_useful_increments_score_and_count[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_usefulness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_active_match[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_none_for_miss[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_cap_zero_returns_empty[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_honours_cap[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_returns_description[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_flagged_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_high_staleness_useful_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_never_accessed_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_existing_relates_to_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_get_flagged_memories_returns_flagged[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_rehabilitable_rows[postgres]`, `packages.core.tests.conformance.test_backend::test_get_stale_archivable_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_link_add_get_basic[postgres]`, `packages.core.tests.conformance.test_backend::test_link_dedup_insert_or_ignore[postgres]`, `packages.core.tests.conformance.test_backend::test_link_filter_by_type[postgres]`, `packages.core.tests.conformance.test_backend::test_link_symmetric_both_ends_reachable[postgres]`, `packages.core.tests.conformance.test_backend::test_list_active_memory_ids_includes_only_active[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_excludes_kind_tagged[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_returns_ext_records[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_includes_archived_when_flag_set[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_includes_past_due[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_not_in_upcoming[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_returns_plain_note[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_delete_removes_path[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_paths_returns_tracked_set[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_get_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_add_get_round_trip_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_archive[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_defaults_after_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_entity_extraction_on_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_false_for_missing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_true_for_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_get_nonexistent_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supersede[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supplied_entities_preserved[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_content_reextracts_entities[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_partial_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_refreshes_updated_at[postgres]`, `packages.core.tests.conformance.test_backend::test_mixed_dimension_embedding_survival[postgres]`, `packages.core.tests.conformance.test_backend::test_ping_returns_true[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_1[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_2[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_directional_not_reversed[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_empty_anchors[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_link_type_filter[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_min_strength_filters[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_symmetric_reverse[postgres]`, `packages.core.tests.conformance.test_backend::test_search_basic_fts_finds_relevant[postgres]`, `packages.core.tests.conformance.test_backend::test_search_bumps_retrieval_count[postgres]`, `packages.core.tests.conformance.test_backend::test_search_creates_query_session[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_stale_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_prefix_matches_compound_word[postgres]`, `packages.core.tests.conformance.test_backend::test_search_respects_limit[postgres]`, `packages.core.tests.conformance.test_backend::test_search_space_split_compound_matches[postgres]`, `packages.core.tests.conformance.test_backend::test_session_create_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_session_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_session_mark_concluded[postgres]`, `packages.core.tests.conformance.test_backend::test_session_record_query_results[postgres]`, `packages.core.tests.conformance.test_backend::test_session_update_feedback_sets_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_stats_counts_correct[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_list_returns_all[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_finds_infix_substring[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_substring_match[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_available_returns_bool[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_memory_exists_with_content[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_returns_non_empty_results[postgres]`, `packages.core.tests.conformance.test_backend::test_write_on_one_handle_visible_on_second[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_corpus_all_memories_searchable[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_recall_at_k[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_total_found_consistent[postgres]`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_reports_src_counts`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_writes_nothing`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_no_row_duplication_after_force`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_with_force_succeeds`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_without_force_raises`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_embedding_vector_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_migration_report_all_ok`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_links`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_memory_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_session`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_summary`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_list_notes`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_manifest_get`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_search_returns_expected`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_superseded_by_round_trip`, `packages.core.tests.test_pg_soak::test_pg_apply_feedback_lost_update_invariant`, `packages.core.tests.test_pg_soak::test_pg_soak_concurrent`, `tests.integration.test_round_trip.TestM3Sessions::test_session_feedback_updates_scores`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-844f12f2 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-f4b27f0d | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-43d72c8b | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c91ee0e7 | ok | 0.870 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c986421b | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-20646f63 | ok | 0.680 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-0d312d3f | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-53f9b64c | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-755ec9f3 | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-e9540797 | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-ebe047e9 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-64a88ce0 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-3ce5b739 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-a83f338b | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-55bbc2f5 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-193aef3b | ok | 0.690 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-711e3d68 | ok | 0.420 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-910cf3ca | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-28481766 | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-395d5e72 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-72a88eb9 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-844f12f2 | observability › Span kind, parent context and exception options › Options reach the span | pass | pass | the judge passed it and a discriminating test passes |
| C-f4b27f0d | observability › Search phase spans and latency › A search shows its phases | pass | pass | the judge passed it and a discriminating test passes |
| C-43d72c8b | observability › Search phase spans and latency › Search-around alone records only its graph point | pass | pass | the judge passed it and a discriminating test passes |
| C-c91ee0e7 | observability › Search phase spans and latency › The Postgres backend uses the shared path | pass | pass | the judge passed it and a discriminating test passes |
| C-c986421b | observability › Span helpers without work or with a failure › A stage with nothing to do | pass | pass | the judge passed it and a discriminating test passes |
| C-20646f63 | observability › Span helpers without work or with a failure › A failing stage | pass | pass | the judge passed it and a discriminating test passes |
| C-0d312d3f | observability › Span helpers without work or with a failure › A metric failure stays inside telemetry | pass | pass | the judge passed it and a discriminating test passes |
| C-53f9b64c | observability › Embedding spans and latency › Hashing embedder is traced | pass | pass | the judge passed it and a discriminating test passes |
| C-755ec9f3 | observability › Embedding spans and latency › Network embedders name their model | pass | pass | the judge passed it and a discriminating test passes |
| C-e9540797 | observability › CLI commands are traced end to end › Command spans and counts | pass | pass | the judge passed it and a discriminating test passes |
| C-ebe047e9 | observability › CLI commands are traced end to end › A failing command is marked | pass | pass | the judge passed it and a discriminating test passes |
| C-64a88ce0 | observability › CLI commands are traced end to end › Exit code 0 is not an error | pass | pass | the judge passed it and a discriminating test passes |
| C-3ce5b739 | observability › Indexing and conversion phases are traced › index-tree phases | pass | pass | the judge passed it and a discriminating test passes |
| C-a83f338b | observability › Indexing and conversion phases are traced › No co-change span without co-change work | pass | pass | the judge passed it and a discriminating test passes |
| C-55bbc2f5 | observability › Indexing and conversion phases are traced › Conversion spans | pass | pass | the judge passed it and a discriminating test passes |
| C-193aef3b | observability › Indexing and conversion phases are traced › Inline caption span | pass | pass | the judge passed it and a discriminating test passes |
| C-711e3d68 | observability › Worker threads keep the trace › Threads stay in the trace | pass | pass | the judge passed it and a discriminating test passes |
| C-910cf3ca | observability › Memory counters › Counter by category | pass | pass | the judge passed it and a discriminating test passes |
| C-28481766 | observability › Telemetry carries no content › No content leaks into telemetry | pass | pass | the judge passed it and a discriminating test passes |
| C-395d5e72 | observability › Telemetry carries no content › Notes, LLM calls, concept names, headers and indexed files leak nothing | pass | pass | the judge passed it and a discriminating test passes |
| C-72a88eb9 | observability › Telemetry carries no content › A failure does not leak its message | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, deterministic] a test is ignored as evidence (criterion C-844f12f2): packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans: it traces 19 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-f4b27f0d): packages.core.tests.test_observability_docs::test_metrics_section_lists_the_new_metrics: it traces 7 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-f4b27f0d): packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans: it traces 19 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-43d72c8b): packages.core.tests.test_observability_docs::test_metrics_section_lists_the_new_metrics: it traces 7 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-43d72c8b): packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans: it traces 19 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-c91ee0e7): packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans: it traces 19 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-c986421b): packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans: it traces 19 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-20646f63): packages.core.tests.test_observability_docs::test_metrics_section_lists_the_new_metrics: it traces 7 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-20646f63): packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans: it traces 19 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-0d312d3f): packages.core.tests.test_observability_docs::test_metrics_section_lists_the_new_metrics: it traces 7 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-53f9b64c): packages.core.tests.test_observability_docs::test_metrics_section_lists_the_new_metrics: it traces 7 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-53f9b64c): packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans: it traces 19 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-755ec9f3): packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans: it traces 19 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-e9540797): packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans: it traces 19 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-ebe047e9): packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans: it traces 19 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-64a88ce0): packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans: it traces 19 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-3ce5b739): packages.core.tests.test_observability_docs::test_metrics_section_lists_the_new_metrics: it traces 7 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-3ce5b739): packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans: it traces 19 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-a83f338b): packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans: it traces 19 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-55bbc2f5): packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans: it traces 19 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-193aef3b): packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans: it traces 19 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-711e3d68): packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans: it traces 19 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-910cf3ca): packages.core.tests.test_observability_docs::test_metrics_section_lists_the_new_metrics: it traces 7 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-28481766): packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans: it traces 19 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-395d5e72): packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans: it traces 19 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-72a88eb9): packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans: it traces 19 criteria (verifier.max_criteria_per_test=3)

## Needs a human

- scope: `packages/core/src/mintmory/core/history/ingest.py` changes module `core`, which the spec does not name
- the diff is longer than 120000 characters: the judge saw only the start

## New tests (red then green, `task.red_ok` in the ledger)

- `packages.cli.tests.test_telemetry_cli_heavy_paths::test_add_root_span_contains_the_add_memory_span` (task 4.1): passed
- `packages.cli.tests.test_telemetry_cli_heavy_paths::test_caption_failure_span_is_failed` (task 4.1): passed
- `packages.cli.tests.test_telemetry_cli_heavy_paths::test_cochange_unavailable_is_an_outcome_not_an_error` (task 4.1): passed
- `packages.cli.tests.test_telemetry_cli_heavy_paths::test_command_span_exit_code_zero_is_not_an_error` (task 4.1): passed
- `packages.cli.tests.test_telemetry_cli_heavy_paths::test_conversion_failure_span_is_failed` (task 4.1): passed
- `packages.cli.tests.test_telemetry_cli_heavy_paths::test_conversion_spans_for_ingest_and_index_tree` (task 4.1): passed
- `packages.cli.tests.test_telemetry_cli_heavy_paths::test_failing_ingest_command_is_marked` (task 4.1): passed
- `packages.cli.tests.test_telemetry_cli_heavy_paths::test_history_sync_exports_its_root_span` (task 4.1): passed
- `packages.cli.tests.test_telemetry_cli_heavy_paths::test_index_search_and_dream_have_root_spans_and_counts` (task 4.1): passed
- `packages.cli.tests.test_telemetry_cli_heavy_paths::test_index_tree_counter_attributes_track_updated_and_unchanged` (task 4.1): passed
- `packages.cli.tests.test_telemetry_cli_heavy_paths::test_index_tree_records_scan_prune_and_cochange_children` (task 4.1): passed
- `packages.cli.tests.test_telemetry_cli_heavy_paths::test_inline_caption_span` (task 4.1): passed
- `packages.cli.tests.test_telemetry_cli_heavy_paths::test_no_cochange_span_when_disabled` (task 4.1): passed
- `packages.cli.tests.test_telemetry_cli_heavy_paths::test_no_cochange_span_with_one_changed_file` (task 4.1): passed
- `packages.cli.tests.test_telemetry_cli_privacy::test_notes_llm_concepts_headers_and_files_leak_nothing` (task 5.4): passed
- `packages.core.tests.test_observability_docs::test_metrics_section_lists_the_new_metrics` (task 6.1): passed
- `packages.core.tests.test_observability_docs::test_spans_section_lists_the_new_spans` (task 6.1): passed
- `packages.core.tests.test_telemetry_embedder::test_a_failing_embed_batch_is_marked_and_re_raised` (task 3.1): passed
- `packages.core.tests.test_telemetry_embedder::test_fake_embed_batch_that_calls_embed_records_once` (task 3.1): passed
- `packages.core.tests.test_telemetry_embedder::test_fake_embed_records_one_span_with_batch_size_one` (task 3.1): passed
- `packages.core.tests.test_telemetry_embedder::test_hashing_embed_batch_records_one_span_and_one_latency_point` (task 3.1): passed
- `packages.core.tests.test_telemetry_embedder::test_hashing_embed_records_one_span_with_batch_size_one` (task 3.1): passed
- `packages.core.tests.test_telemetry_embedder_network::test_local_embedder_methods_carry_the_shared_decorator` (task 3.2): passed
- `packages.core.tests.test_telemetry_embedder_network::test_ollama_embed_names_provider_and_model` (task 3.2): passed
- `packages.core.tests.test_telemetry_embedder_network::test_openai_embed_names_provider_and_model` (task 3.2): passed
- `packages.core.tests.test_telemetry_memory_counter::test_both_backends_add_memory_carry_the_shared_decorator` (task 5.3): passed
- `packages.core.tests.test_telemetry_memory_counter::test_sqlite_add_memory_counts_each_category` (task 5.3): passed
- `packages.core.tests.test_telemetry_privacy::test_a_failure_does_not_leak_its_message` (task 5.4): passed
- `packages.core.tests.test_telemetry_privacy::test_no_content_leaks_into_telemetry` (task 5.4): passed
- `packages.core.tests.test_telemetry_search_paths::test_a_metric_failure_stays_inside_telemetry` (task 2.1): passed
- `packages.core.tests.test_telemetry_search_paths::test_failing_stage_is_marked_and_still_timed` (task 2.1): passed
- `packages.core.tests.test_telemetry_search_paths::test_note_anchoring_records_no_search_phase` (task 2.1): passed
- `packages.core.tests.test_telemetry_search_paths::test_postgres_search_uses_the_shared_phase_path` (task 2.1): passed
- `packages.core.tests.test_telemetry_search_paths::test_search_around_alone_records_only_its_graph_point` (task 2.1): passed
- `packages.core.tests.test_telemetry_search_paths::test_search_records_the_four_phase_spans_and_latency` (task 2.1): passed
- `packages.core.tests.test_telemetry_search_paths::test_stage_with_nothing_to_do_records_a_zero_count` (task 2.1): passed
- `packages.core.tests.test_telemetry_search_phase::test_search_phase_marks_a_failing_stage_and_records_latency` (task 1.3): passed
- `packages.core.tests.test_telemetry_search_phase::test_search_phase_opens_a_span_and_records_a_latency_point` (task 1.3): passed
- `packages.core.tests.test_telemetry_search_phase::test_search_phase_records_zero_for_a_stage_with_nothing_to_do` (task 1.3): passed
- `packages.core.tests.test_telemetry_search_phase::test_search_phase_swallows_a_metric_recording_failure` (task 1.3): passed
- `packages.core.tests.test_telemetry_search_phase::test_search_phase_without_a_span_still_yields_a_count_setter` (task 1.3): passed
- `packages.core.tests.test_telemetry_search_phase::test_timed_phase_records_only_the_phase_point` (task 1.3): passed
- `packages.core.tests.test_telemetry_set_attributes_counter::test_counts_added_records_each_category_and_marks_the_wrapper` (task 1.5): passed
- `packages.core.tests.test_telemetry_set_attributes_counter::test_counts_added_works_with_telemetry_off` (task 1.5): passed
- `packages.core.tests.test_telemetry_set_attributes_counter::test_set_attributes_writes_on_the_current_span` (task 1.5): passed
- `packages.core.tests.test_telemetry_span_options::test_run_in_context_keeps_the_trace_across_four_threads` (task 1.1): passed
- `packages.core.tests.test_telemetry_span_options::test_span_context_sets_an_explicit_parent` (task 1.1): passed
- `packages.core.tests.test_telemetry_span_options::test_span_exception_options_reach_the_span` (task 1.1): passed
- `packages.core.tests.test_telemetry_span_options::test_span_kind_maps_known_values_and_falls_back_to_internal` (task 1.1): passed
- `packages.core.tests.test_telemetry_span_options::test_span_options_on_the_off_shim_are_a_noop_with_update_name` (task 1.1): passed

## Guard events

- guard.violation: packages/core/src/mintmory/core/telemetry.py
- guard.violation: packages/core/src/mintmory/core/telemetry.py
- guard.violation: packages/core/src/mintmory/core/telemetry.py
