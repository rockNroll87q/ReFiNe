
# ReFiNe workflow rules

For ReFiNe tasks:

- Do not read the whole repository unless explicitly asked.
- Read only the files needed for the current task.
- Prefer editing the minimum number of files.
- Work in small steps.
- Do not implement future features unless explicitly requested.
- Do not process all papers unless explicitly requested.
- Do not loop over the same files repeatedly.
- After each task, run one relevant command and stop.
- Report only:
  - files changed
  - command run
  - command output
  - whether the task succeeded
- If uncertain, ask before continuing.

Project context:

ReFiNe is a static website and local extraction pipeline for broad dataset-feature descriptors needed to attempt neuroimaging replications.

The website reads:

site/data/papers.json

The extraction pipeline should work locally and should not depend on GitHub, a backend, or Cline itself.


