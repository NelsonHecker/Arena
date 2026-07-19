# One semantic field change. Published per change on state/semantic_events.
builtin_interfaces/Time stamp   # sim time the change was observed
uint32 env_id                   # env index this change belongs to
string entity                   # env-prefixed instance name
string kind                     # semantic kind of the entity
uint8 STATE = 0                 # field is a state, discrete or continuous
uint8 PREDICATE = 1             # field is a boolean predicate
uint8 field_kind                # STATE or PREDICATE
string field                    # name of the changed state or predicate
string previous                 # prior value, stringified
string current                  # new value, stringified
