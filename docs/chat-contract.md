# Assistant integration

The signed-in assistant stores turns in SQLite. Conversation routes live under
`/api/chat/conversations` and use the current session, owner scope, and CSRF
checks for mutations. Message requests carry a client-generated request UUID.
Inference failures leave the prompt available for retry in the composer.

The only operational chat tool reads assigned projects. Its results are
returned for the current request without persisting project names in history.
Draft specialized evaluators load AT-AI-001 through AT-AI-003 from docs/ai and
check response schemas and references. They are available for evaluation with
server-curated inputs and are pending domain approval and real-model tests.

Attachments are selected locally. Server uploads, mapping confirmation,
validation workflows, financial policy, reviewable batches, and approvals need
confirmed domain and permission contracts before they can be exposed. Draft
prompt evaluation has no authority to apply mappings or approve payments.
