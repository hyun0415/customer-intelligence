# Coding agent guidance for this project

## Communication (Attention Span: Attention-kind)
- Answer the user's question first. Use short, plain-language paragraphs and keep essential caveats.
- Give status updates that are easy to scan. Expand when the user asks for detail.
- Keep this style in conversation; do not put chat formatting in code.

## Coding (Karpathy Guidelines)
- State meaningful assumptions when a request is ambiguous, and ask when the choice affects the result.
- Make the smallest change that solves the requested problem. Avoid speculative abstractions and unrelated cleanup.
- Match the existing code style and remove only unused code introduced by the current change.
- Define a checkable outcome for each task and keep working until it has been checked.

## Verification
- Before claiming a change works, run the relevant fresh check and report what it actually showed.
- For TypeScript or JavaScript changes in `frontend`, run `npm run lint:anti-slop` and the relevant typecheck or build check.
- The detailed local skills are in `.agents/skills/karpathy-guidelines` and `.agents/skills/verification-before-completion`.

Sources: https://github.com/alexgreensh/attention-span, https://github.com/multica-ai/andrej-karpathy-skills, https://github.com/obra/superpowers
