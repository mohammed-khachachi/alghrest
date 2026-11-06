[graphify] MultiDiGraph edge-collapse diagnostic
input: <in-memory>
input_stage: provided JSON (normal graph.json is post-build)
effective_directed: <direct-call>
nodes: 5400
unverified_code_nodes: 0
raw_edges: 18352
valid_candidate_edges: 16669
missing_endpoint_edges: 0
dangling_endpoint_edges: 1617
external_reference_edges: 66
self_loop_edges: 5
exact_duplicate_edges: 0
directed_unique_endpoint_pairs: 15926
directed_same_endpoint_collapsed_edges: 743
undirected_unique_endpoint_pairs: 15920
undirected_same_endpoint_collapsed_edges: 749
same_endpoint_group_count: 718
relation_variant_groups: 612
source_file_variant_groups: 0
source_location_variant_groups: 54
context_variant_groups: 67
post_build_graph_type: Graph
post_build_edges: 17598
producer_suppression_sites: 12
producer_suppression_examples:
  - L1813 seen_ids arity=unknown
  - L2377 seen_ids arity=unknown
  - L2379 seen_doc_refs arity=unknown
  - L3046 seen_ids arity=unknown
  - L3193 seen_ids arity=unknown
  - L4222 seen_keys arity=unknown
  - L4408 seen_keys arity=unknown
  - L7689 seen_ids arity=unknown
examples:
  - src_core_accounting_performance_observe -> src_core_data_performance_performance edges=4 relations=['calls', 'references', 'uses'] locations=['L16', 'L17', 'L28'] contexts=['', 'call', 'parameter_type', 'return_type']
  - dashboard_src_i18n_index -> dashboard_src_i18n_core edges=3 relations=['imports_from', 're_exports'] locations=['L3', 'L4'] contexts=['export', 'import', 're-export']
  - dashboard_src_lib_tcp25personal -> dashboard_src_lib_userpolicy edges=3 relations=['imports_from', 're_exports'] locations=['L113', 'L114', 'L2'] contexts=['export', 'import', 're-export']
  - src_api_advisor_create_evaluation -> src_core_advisory_evaluation_evaluationprofile edges=3 relations=['references', 'uses'] locations=['L305'] contexts=['', 'parameter_type', 'return_type']
  - src_api_routes_advisory_briefings_workflow -> src_api_services_briefings_briefingworkflow edges=3 relations=['calls', 'references', 'uses'] locations=['L15', 'L16'] contexts=['', 'call', 'return_type']
note: normal graph.json is post-build; raw producer loss must be measured earlier.