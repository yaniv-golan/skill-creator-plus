# eval-scenarios: answer-quality A/B suite (not part of CI replay)

Q&A scenarios for `cowork-harness eval`, used to check that a restructure of skill-creator-plus does not
degrade the answers its guidance leads to. Every rubric claim must be true of BOTH arms' content, and
claims are about what the agent SAYS, never about tool calls (the judge sees no tool calls).

    npx cowork-harness@4.2.1 --dotenv <.env> eval harness/eval-scenarios/ \
      --arm before=git:<ref>:skill-creator-plus --arm after=./skill-creator-plus \
      --model <concrete id> --judge-model <concrete id> --skill skill-creator-plus \
      --holdout harness/eval-scenarios/setup-arguments.yaml --fail-on possible

Live runs only: scenarios x 2 arms x 5 reps. Lint locally (`cowork-harness lint --strict
harness/eval-scenarios/`); CI's harness lint does not descend into this directory.

`invoked/` holds copies of five scenarios whose prompt starts with "Use the skill-creator-plus skill to
answer this." In the 0.17.0 A/B, Sonnet answered those five questions from its own knowledge without
invoking the skill, so the plain versions compared nothing about the skill's text; the invoked
versions do. Keep both: the plain ones also show whether the skill gets triggered at all.
